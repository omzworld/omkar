"""Market signals (brick sales, endoscopy unit procedures) and consent, as DuckDB SQL.

Quarter-on-quarter changes compare the last complete quarter before the run date with the quarter before it.
"""
from __future__ import annotations

import duckdb
import pandas as pd

BRICKS = """
with m as (
    select brick_id, market, month, units, competitor_units from iqvia_brick_sales
    where product = 'Movicol' and month < date_trunc('month', $as_of::timestamp)
),
q as (
    select brick_id, market, date_trunc('quarter', month) as quarter, sum(units) as units,
           sum(competitor_units) as comp
    from m where month < date_trunc('quarter', $as_of::timestamp) group by all
),
qq as (
    select brick_id, market,
           arg_max(units, quarter) as units_q1, arg_max(comp, quarter) as comp_q1,
           max(quarter) as q1
    from q group by all
),
prev as (
    select q.brick_id, q.units as units_q0, q.comp as comp_q0
    from q join qq on qq.brick_id = q.brick_id and q.quarter = qq.q1 - interval 3 month
),
months as (
    select brick_id,
           arg_max(units, month) as units_m1,
           max(month) as m1
    from m group by 1
),
m_prev as (
    select m.brick_id,
           max(m.units) filter (where m.month = months.m1 - interval 1 month) as units_m0,
           sum(m.units) filter (where m.month > months.m1 - interval 3 month) as units_last3,
           sum(m.units) filter (where m.month <= months.m1 - interval 3 month
                                and m.month > months.m1 - interval 6 month) as units_prev3
    from m join months using (brick_id) group by 1
),
potential as (
    select brick_id, market, sum(units + competitor_units) as market_units
    from m where month >= date_trunc('month', $as_of::timestamp) - interval 12 month group by all
)
select qq.brick_id,
    round(100 * (qq.units_q1 / nullif(p.units_q0, 0) - 1), 1)                                  as brick_volume_qoq_pct,
    round(100 * (qq.comp_q1 / nullif(qq.units_q1 + qq.comp_q1, 0)
               - p.comp_q0 / nullif(p.units_q0 + p.comp_q0, 0)), 1)                            as brick_competitor_share_change,
    round(100 * (mp.units_last3 / nullif(mp.units_prev3, 0) - 1), 1)                         as pharmacy_dispensing_qoq_pct,
    round(100 * (months.units_m1 / nullif(mp.units_m0, 0) - 1), 1)                             as brick_volume_delta_4w,
    round(100 * pot.market_units / avg(pot.market_units) over (partition by pot.market), 1)     as brick_potential_index
from qq
join prev p using (brick_id)
join months using (brick_id)
join m_prev mp using (brick_id)
join potential pot using (brick_id)
"""

# Brick potential at earlier dates, to spot physicians newly in a target tier.
POTENTIAL_AT = """
with b as (
    select brick_id, market, sum(units + competitor_units) as market_units
    from iqvia_brick_sales
    where product = 'Movicol' and month < date_trunc('month', $d::timestamp)
      and month >= date_trunc('month', $d::timestamp) - interval 12 month
    group by all
)
select brick_id, market, 100 * market_units / avg(market_units) over (partition by market) as potential from b
"""

UNITS = """
with q as (
    select hco_id, quarter, colonoscopies, norgine_prep_share, inadequate_prep_rate,
           row_number() over (partition by hco_id order by quarter desc) as r
    from procedure_volume
    where quarter < strftime($as_of::timestamp, '%Y') || '-Q' || quarter($as_of::timestamp)
)
select a.hco_id as unit_id,
       round(100 * (a.colonoscopies / nullif(b.colonoscopies, 0) - 1), 1)            as unit_procedure_volume_qoq_pct,
       round(100 * (b.norgine_prep_share - a.norgine_prep_share), 1)                 as unit_competitor_share_change,
       round(100 * a.inadequate_prep_rate, 1)                                         as inadequate_prep_rate_reported,
       a.colonoscopies                                                                as unit_colonoscopies_qtr
from q a join q b on a.hco_id = b.hco_id and a.r = 1 and b.r = 2
"""

CONSENT = """
select account_id,
    bool_or(channel = 'marketing_email' and status = 'granted' and captured_date < $as_of)      as consent_email,
    bool_or(channel = 'marketing_email' and status = 'granted' and captured_date < $as_of
            and consent_type = 'double_opt_in')                                                as consent_double_opt_in,
    bool_or(channel = 'remote_call' and status = 'granted' and captured_date < $as_of)          as consent_remote,
    bool_or(channel = 'paid_media' and status = 'granted' and captured_date < $as_of)           as consent_digital_tracking,
    bool_or(status = 'withdrawn') and not bool_or(status = 'granted')                          as opt_out_any,
    count(*) filter (where channel = 'marketing_email' and status = 'granted'
                     and captured_date >= $as_of - interval 28 day and captured_date < $as_of) as consent_gained_4w
from consent group by 1
"""

UNSUBSCRIBES_4W = """
select account_id, count(*) as unsubscribes_4w from (
    select s.account_id from email_activity_vod e join sent_email_vod s on s.id = e.sent_email_id
    where e.event_type = 'unsubscribe' and e.event_datetime >= $as_of - interval 28 day and e.event_datetime < $as_of
    union all
    select account_id from agency_email
    where unsubscribed and sent_datetime >= $as_of - interval 28 day and sent_datetime < $as_of
) group by 1
"""

FEEDBACK = """
select account_id,
    count(*) filter (where status = 'dismissed' and suggested_date >= $as_of - interval 30 day)        as dismissals_30d,
    arg_max(dismiss_reason, suggested_date) filter (where status = 'dismissed')                          as last_dismiss_reason,
    date_diff('day', max(suggested_date) filter (where status = 'dismissed'), $as_of)                    as days_since_dismiss,
    round(avg((status = 'accepted')::int) filter (where status in ('accepted', 'dismissed')
                                                  and suggested_date >= $as_of - interval 90 day), 3)    as suggestion_accept_rate_90d
from suggestion_vod where suggested_date < $as_of group by 1
"""


def build(con: duckdb.DuckDBPyConnection, as_of: pd.Timestamp) -> dict[str, pd.DataFrame]:
    p = {"as_of": as_of.date()}
    out = {name: con.execute(sql, p).df() for name, sql in
           [("bricks", BRICKS), ("units", UNITS), ("consent", CONSENT), ("unsubs", UNSUBSCRIBES_4W),
            ("feedback", FEEDBACK)]}
    for days in (30, 60, 90):
        out[f"potential_{days}d_ago"] = con.execute(POTENTIAL_AT, {"d": (as_of - pd.Timedelta(days=days)).date()}).df()
    return out
