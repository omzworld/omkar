"""Data readiness report: the checks listed in synthetic_design.yaml (readiness_report).

Each check is a plain DuckDB SQL query over the Parquet tables, so it reads like the SQL you
would run against a client's data warehouse during a data audit. The report is printed for the
command line and saved as data/readiness.json for the web screen (demo scene 1).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from nba import data, schema, spec

ENGINE_TABLES = {"suggestion_vod", "rule_draft", "ml_candidate", "rep_brief", "proposed_rule", "feature_snapshot"}

SQL_HEADLINE = """
select a.market,
       count(*) filter (where a.account_type = 'hcp')                    as healthcare_professionals,
       count(*) filter (where a.account_type <> 'hcp')                   as organisations,
       (select count(*) from territory_vod t where t.market = a.market and t.pilot_arm = 'test')    as test_territories,
       (select count(*) from territory_vod t where t.market = a.market and t.pilot_arm = 'control') as control_territories
from account_vod a group by a.market order by a.market
"""

SQL_CONSENT = """
select market,
       round(100 * avg(case when channel = 'marketing_email' and status = 'granted' then 1 else 0 end)
             filter (where channel = 'marketing_email'), 1)                                   as email_pct,
       round(100 * avg(case when status = 'granted' and consent_type = 'double_opt_in' then 1 else 0 end)
             filter (where channel = 'marketing_email'), 1)                                   as email_double_opt_in_pct,
       round(100 * avg(case when status = 'granted' then 1 else 0 end) filter (where channel = 'remote_call'), 1)
                                                                                              as remote_call_pct,
       round(100 * avg(case when status = 'granted' then 1 else 0 end) filter (where channel = 'paid_media'), 1)
                                                                                              as tracked_digital_pct,
       count(*) filter (where channel = 'marketing_email' and status = 'withdrawn')           as email_withdrawn
from consent group by market order by market
"""

SQL_RESPONSE = """
with hcp as (select id, specialty_1_vod as specialty from account_vod where account_type = 'hcp'),
touches as (
    select h.specialty, case when c.call_type = 'remote' then 'remote_call' else 'rep_visit' end as channel,
           (c.next_step <> 'none')::int as responded
    from call2_vod c join hcp h on h.id = c.account_id where c.status = 'submitted'
    union all
    select h.specialty, 'rep_email', (exists (select 1 from email_activity_vod e
                                       where e.sent_email_id = s.id and e.event_type = 'open'))::int
    from sent_email_vod s join hcp h on h.id = s.account_id where s.status = 'sent'
    union all
    select h.specialty, 'marketing_email', a.opened::int from agency_email a join hcp h on h.id = a.account_id
    union all
    select h.specialty, 'webinar', ev.attended::int
    from event_attendee_vod ev join hcp h on h.id = ev.account_id where ev.event_type = 'webinar'
)
select specialty, channel, count(*) as touches, round(100 * avg(responded), 1) as response_pct
from touches group by all order by specialty, channel
"""

SQL_BRICKS = """
with m as (select market, brick_id, month, units from iqvia_brick_sales where product = 'Movicol'),
r as (
    select market, brick_id, month,
           sum(units) over (partition by brick_id order by month rows between 2 preceding and current row) as r3,
           sum(units) over (partition by brick_id order by month rows between 5 preceding and 3 preceding) as p3,
           count(*) over (partition by brick_id order by month) as n
    from m
),
readings as (
    select market, brick_id, r3, 100 * (r3 / nullif(p3, 0) - 1) as pct,
           row_number() over (partition by brick_id order by month desc) as k
    from r where n >= 6
),
b as (
    select market, brick_id, max(pct) filter (where k = 1) as pct, max(r3) filter (where k = 1) as r3,
           count(*) filter (where k <= 3 and pct < 0) as down, count(*) filter (where k <= 3 and pct > 0) as up
    from readings group by all
)
select market, count(*) as bricks,
       round(median(pct), 1)                                                         as median_change_pct,
       count(*) filter (where pct <= -8 and down >= 2 and r3 >= 100)                 as bricks_down_8pct_or_more,
       count(*) filter (where pct >= 10 and up >= 2 and r3 >= 100)                   as bricks_up_10pct_or_more
from b group by market order by market
"""

SQL_MONTHLY = """
select market, strftime(month, '%Y-%m') as month, round(sum(units)) as movicol_units,
       round(100 * sum(units) / sum(units + competitor_units), 1) as norgine_share_pct
from iqvia_brick_sales where product = 'Movicol' group by all order by market, month
"""

SQL_STAGES = """
with ends as (select min(week) as first_week, max(week) as last_week from hcp_stage_weekly)
select a.market, s.stage,
       count(*) filter (where s.week = e.first_week) as start_count,
       count(*) filter (where s.week = e.last_week)  as end_count
from hcp_stage_weekly s join account_vod a on a.id = s.account_id, ends e
where s.week in (e.first_week, e.last_week)
group by all
"""

STAGE_ORDER = ["curiosity", "consideration", "experience", "loyalty", "advocacy"]


def expected_email_consent() -> float:
    """Design rate: share of each behaviour cluster times its email consent rate."""
    cl = spec.design()["clusters"]
    return 100 * sum(c["share"] * c["consent_email_rate"] for c in cl.values()) / sum(c["share"] for c in cl.values())


def _null_rates(con) -> pd.DataFrame:
    rows = []
    for t in data.tables():
        if t in ENGINE_TABLES:
            continue
        total = con.execute(f"select count(*) from {t}").fetchone()[0]
        cols = schema.fields(t)
        if not total or not cols:
            continue
        exprs = ", ".join(f'count(*) - count("{c}") as "{c}"' for c in cols)
        nulls = con.execute(f"select {exprs} from {t}").df().iloc[0]
        for c, k in nulls.items():
            if k:
                rows.append(dict(table=t, column=c, null_pct=round(100 * k / total, 1)))
    return pd.DataFrame(rows, columns=["table", "column", "null_pct"])


def build(data_dir: Path | None = None) -> dict:
    con = data.connect(data_dir)
    counts = pd.DataFrame([(t, con.execute(f"select count(*) from {t}").fetchone()[0]) for t in data.tables(data_dir)],
                          columns=["table", "rows"])
    weeks = con.execute("select count(distinct week) from hcp_stage_weekly").fetchone()[0]
    consent = con.execute(SQL_CONSENT).df()
    expected = expected_email_consent()
    consent["expected_email_pct"] = round(expected, 1)
    consent["gap_points"] = (consent.email_pct - expected).round(1)
    consent["within_5_points"] = consent.gap_points.abs() <= 5
    stages = con.execute(SQL_STAGES).df()
    stages["stage"] = pd.Categorical(stages.stage, STAGE_ORDER, ordered=True)
    stages = stages.sort_values(["market", "stage"])
    for col in ["start_count", "end_count"]:
        stages[col.replace("count", "pct")] = (100 * stages[col] / stages.groupby("market")[col].transform("sum")).round(1)
    response = con.execute(SQL_RESPONSE).df()
    return {
        "headline": con.execute(SQL_HEADLINE).df(), "history_weeks": int(weeks), "row_counts": counts,
        "null_rates": _null_rates(con), "consent": consent,
        "response_by_channel": response.groupby("channel").apply(
            lambda g: round((g.touches * g.response_pct).sum() / g.touches.sum(), 1), include_groups=False
        ).rename("response_pct").reset_index(),
        "response": response.pivot(index="specialty", columns="channel", values="response_pct").reset_index(),
        "bricks": con.execute(SQL_BRICKS).df(), "monthly_sales": con.execute(SQL_MONTHLY).df(),
        "stages": stages[["market", "stage", "start_pct", "end_pct"]],
    }


def passed(report: dict) -> bool:
    return bool(report["consent"].within_5_points.all())


def save(report: dict, data_dir: Path | None = None) -> Path:
    path = (Path(data_dir) if data_dir else spec.data_dir()) / "readiness.json"
    out = {k: (v.astype(object).where(v.notna(), None).to_dict(orient="records") if isinstance(v, pd.DataFrame) else v)
           for k, v in report.items()}
    path.write_text(json.dumps(out, indent=1, default=str))
    return path


def render(report: dict) -> str:
    def table(df: pd.DataFrame) -> str:
        return df.to_string(index=False)
    h = report["headline"]
    lines = ["DATA READINESS REPORT (synthetic data)", "=" * 40, "",
             f"Markets: {', '.join(h.market)}.  Healthcare professionals: {int(h.healthcare_professionals.sum()):,}.  "
             f"History: {report['history_weeks']} weeks (~{report['history_weeks'] // 4.33:.0f} months).", "",
             "1. Who is in the data, and how the pilot is split", table(h), "",
             "2. Row counts per table (engine tables are empty until the engine runs)", table(report["row_counts"]), "",
             "3. Missing values (columns with any blanks; blanks on organisation rows for physician-only",
             "   fields are expected)", table(report["null_rates"]), "",
             "4. Consent coverage by market (% of healthcare professionals who have given consent)",
             table(report["consent"]), ""]
    ok = passed(report)
    lines += [f"   Email consent vs the design rate of {report['consent'].expected_email_pct.iloc[0]}%: "
              f"{'PASS, within 5 points in every market' if ok else 'FAIL, more than 5 points away'}", "",
              "5. Response rates (% of touches that got a response: visit with a next step, email opened,",
              "   webinar attended), overall and by specialty",
              table(report["response_by_channel"]), "", table(report["response"]), "",
              "6. Brick sales trend (Movicol units, last complete quarter vs the quarter before)",
              table(report["bricks"]), "",
              "   Movicol units and Norgine share of the brick market, last 6 months",
              table(report["monthly_sales"].groupby("market").tail(6)), "",
              "7. Journey stage distribution (% of healthcare professionals, start vs end of history)",
              table(report["stages"])]
    return "\n".join(lines)
