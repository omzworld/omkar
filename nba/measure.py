"""Measurement: test versus control territories, and the return model (demo scene 6).

Test territories ran the engine; control territories ran today's plan. Territories were split at generation,
stratified by market and tier mix, and never changed. Everything below compares the two arms over the pilot
weeks run so far, in plain DuckDB SQL over the same tables the engine writes.

Brick lift (difference in differences): growth of brick sales in test territories minus growth in control
territories, comparing the completed pilot months with the same number of months just before the pilot.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from nba import data, spec

ARMS = ("test", "control")
RESPONSES = """
-- One row per touch in the pilot period, with whether the physician responded and what it cost.
create or replace temp view pilot_touches as
with t as (
    select c.account_id, c.call_date::date as d,
           case when c.call_type = 'remote' then 'remote_call' when u.role = 'kam' then 'kam_visit'
                else 'rep_visit' end as channel, c.next_step <> 'none' as responded
    from call2_vod c join user_vod u on u.id = c.user_id where c.status = 'submitted'
    union all
    select s.account_id, s.email_sent_date::date, 'rep_email',
           exists (select 1 from email_activity_vod e where e.sent_email_id = s.id and e.event_type = 'open')
    from sent_email_vod s where s.status = 'sent'
    union all
    select account_id, sent_datetime::date, 'marketing_email', opened from agency_email
    union all
    select account_id, event_date, 'webinar', attended from event_attendee_vod where event_type = 'webinar'
)
select t.*, tv.pilot_arm, a.account_type
from t join account_vod a on a.id = t.account_id join territory_vod tv on tv.id = a.territory_id
where t.d >= '{start}' and t.d < '{end}' and tv.pilot_arm in ('test', 'control')
"""


def _touches_view(con, start: pd.Timestamp, end: pd.Timestamp) -> None:
    # Views cannot take query parameters; the dates come from the code, never from user input.
    con.execute(RESPONSES.format(start=f"{start:%Y-%m-%d}", end=f"{end:%Y-%m-%d}"))


def _window(data_dir) -> tuple[pd.Timestamp, pd.Timestamp, int]:
    start = pd.Timestamp(spec.design()["clock"]["pilot_start"])
    p = (Path(data_dir) if data_dir else spec.data_dir()) / "runs" / "summary.parquet"
    weeks = int(pd.read_parquet(p).week.max()) if p.exists() else 0
    return start, start + pd.Timedelta(weeks=weeks), weeks


def brick_lift(con, start: pd.Timestamp) -> dict:
    """Movicol brick units: completed pilot months against the same number of months before."""
    months = con.execute("""select distinct month from iqvia_brick_sales where month >= date_trunc('month', $s::date)
                            order by 1""", {"s": start.date()}).df().month
    n = len(months)
    if n == 0:
        return {"months_measured": 0}
    first = pd.Timestamp(months.iloc[0])
    pre_start = first - pd.DateOffset(months=n)
    df = con.execute("""
        with arm as (select distinct a.brick_id, tv.pilot_arm from account_vod a
                     join territory_vod tv on tv.id = a.territory_id where a.brick_id is not null)
        select arm.pilot_arm, s.product, s.month >= $first as post, sum(s.units) as units, sum(s.value) as value
        from iqvia_brick_sales s join arm using (brick_id)
        where arm.pilot_arm in ('test', 'control') and s.month >= $pre
        group by all
    """, {"first": first.date(), "pre": pre_start.date()}).df()
    mov = df[df["product"] == "Movicol"].pivot_table(index="pilot_arm", columns="post", values="units")
    growth = (mov[True] / mov[False] - 1) * 100
    tv = df[df["product"] == "Movicol"].groupby(["pilot_arm", "post"])[["units", "value"]].sum()
    expected_test = mov.loc["test", False] * (1 + growth["control"] / 100)
    price = (tv.loc[("test", True), "value"] / tv.loc[("test", True), "units"])
    return {"months_measured": n, "first_month": f"{first:%b %Y}", "last_month": f"{pd.Timestamp(months.iloc[-1]):%b %Y}",
            "test_growth_pct": round(float(growth["test"]), 1), "control_growth_pct": round(float(growth["control"]), 1),
            "lift_pts": round(float(growth["test"] - growth["control"]), 1),
            "incremental_units": round(float(mov.loc["test", True] - expected_test), 0),
            "test_baseline_units": round(float(mov.loc["test", False]), 0),
            "test_baseline_value_eur": round(float(tv.loc[("test", False), "value"]), 0),
            "average_price_eur": round(float(price), 2)}


def monthly_index(con, start: pd.Timestamp) -> pd.DataFrame:
    """Movicol brick units per month and arm, indexed to the average of the 6 months before the pilot = 100."""
    df = con.execute("""
        with arm as (select distinct a.brick_id, tv.pilot_arm from account_vod a
                     join territory_vod tv on tv.id = a.territory_id where a.brick_id is not null)
        select s.month, arm.pilot_arm, sum(s.units) as units from iqvia_brick_sales s join arm using (brick_id)
        where s.product = 'Movicol' and arm.pilot_arm in ('test', 'control') and s.month >= $from
        group by all order by 1
    """, {"from": (start - pd.DateOffset(months=12)).date()}).df()
    wide = df.pivot(index="month", columns="pilot_arm", values="units")
    base = wide[wide.index < start - pd.DateOffset(days=8)].tail(6).mean()
    out = (100 * wide / base).round(1).reset_index()
    out["month"] = pd.to_datetime(out.month).dt.strftime("%Y-%m")
    out["pilot"] = pd.to_datetime(out.month) >= start.to_period("M").to_timestamp()
    return out


def arms(con, start, end) -> pd.DataFrame:
    """Per arm: physicians, reach, engagement, journey progress, cost, cost per engaged physician."""
    _touches_view(con, start, end)
    cost = spec.assumptions()["touch_cost"]
    con.register("touch_cost", pd.DataFrame({"channel": list(cost), "cost": list(cost.values())}))
    df = con.execute("""
        with hcps as (select a.id, tv.pilot_arm from account_vod a join territory_vod tv on tv.id = a.territory_id
                      join hcp_master_opendata m on m.onekey_id = a.onekey_id
                      where a.account_type = 'hcp' and a.status = 'active' and not m.no_promo_flag
                        and a.hcp_role <> 'medical_only_contact' and tv.pilot_arm in ('test', 'control')),
        touch as (select pilot_arm, count(*) as touches, sum(coalesce(c.cost, 0)) as cost_eur,
                         count(distinct account_id) filter (where account_type = 'hcp') as reached,
                         count(distinct account_id) filter (where responded and account_type = 'hcp') as engaged,
                         round(100 * avg(responded::int), 1) as response_pct
                  from pilot_touches left join touch_cost c using (channel) group by 1),
        stage as (select a.pilot_arm,
                    list_position(['curiosity','consideration','experience','loyalty','advocacy'], s.stage) as i,
                    s.account_id, s.week
                  from hcp_stage_weekly s join hcps a on a.id = s.account_id
                  where s.week in ((select max(week) from hcp_stage_weekly where week < $start),
                                   (select max(week) from hcp_stage_weekly where week < $end))),
        moved as (select pilot_arm, account_id,
                         max(i) filter (where week >= $start) - max(i) filter (where week < $start) as d
                  from stage group by all),
        mv as (select pilot_arm, round(100 * avg((d > 0)::int), 1) as moved_up_pct,
                      round(100 * avg((d < 0)::int), 1) as moved_back_pct from moved group by 1),
        counts as (select pilot_arm, count(*) as physicians from hcps group by 1)
        select c.pilot_arm, c.physicians, t.touches, round(t.cost_eur) as cost_eur, t.reached, t.engaged,
               t.response_pct,
               round(100 * t.reached / c.physicians, 1) as reach_pct,
               round(100 * t.engaged / c.physicians, 1) as engaged_pct,
               round(t.cost_eur / nullif(t.engaged, 0), 1) as cost_per_engaged_eur,
               round(t.touches / c.physicians, 2) as touches_per_physician,
               mv.moved_up_pct, mv.moved_back_pct
        from counts c join touch t using (pilot_arm) join mv using (pilot_arm) order by 1 desc
    """, {"start": start.date(), "end": end.date()}).df()
    return df


def weekly(con, start, end) -> pd.DataFrame:
    """Per pilot week and arm: touches and responses; for test, rep acceptance of suggestions."""
    _touches_view(con, start, end)
    w = con.execute("""
        select date_trunc('week', d) as week, pilot_arm, count(*) as touches, sum(responded::int) as responses
        from pilot_touches group by all order by 1
    """).df()
    wide = w.pivot(index="week", columns="pilot_arm", values=["touches", "responses"])
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    acc = con.execute("""
        select suggested_date as week, round(100 * avg((status = 'accepted')::int), 1) as acceptance_pct,
               count(*) as suggestions
        from suggestion_vod group by 1 order by 1
    """).df().set_index("week")
    out = wide.join(acc, how="left").reset_index()
    out["week"] = pd.to_datetime(out.week).dt.strftime("%d %b")
    return out.fillna(0)


def consent_growth(con, start, end, weeks: int) -> dict:
    """Email consent per arm: at the pilot start and now, and growth per month."""
    df = con.execute("""
        select tv.pilot_arm,
               count(*) filter (where c.status = 'granted' and c.captured_date < $start) as at_start,
               count(*) filter (where c.status = 'granted') as now
        from consent c join account_vod a on a.id = c.account_id join territory_vod tv on tv.id = a.territory_id
        where c.channel = 'marketing_email' and tv.pilot_arm in ('test', 'control') group by 1
    """, {"start": start.date()}).df().set_index("pilot_arm")
    months = max(weeks / 4.345, 1e-9)
    return {arm: {"at_start": int(r.at_start), "now": int(r.now),
                  "growth_pct_per_month": round(float(100 * (r.now / r.at_start - 1) / months), 2) if r.at_start else 0.0}
            for arm, r in df.iterrows()}


def return_model(lift: dict, arm_table: pd.DataFrame, weeks: int, fee_per_quarter: float | None = None,
                 margin_pct: float = 70.0, scale: float = 1.0, lift_override_pts: float | None = None,
                 count_touch_savings: bool = False, brand_sales_per_quarter_eur: float | None = None) -> dict:
    """What the measured lift and the touch savings are worth against the fee, per quarter, and the break-even.
    scale multiplies the test territories' baseline to the size of a roll-out (1 = the pilot as run)."""
    a = spec.assumptions()["run_cost"]
    fee = a["build_and_run_fee_per_quarter"] if fee_per_quarter is None else fee_per_quarter
    if not lift.get("months_measured"):
        return {}
    months = lift["months_measured"]
    lift_pts = lift["lift_pts"] if lift_override_pts is None else lift_override_pts
    # Brand sales the lift applies to: the client's real figure if given, else the synthetic test territories.
    baseline_value_qtr = brand_sales_per_quarter_eur if brand_sales_per_quarter_eur else \
        lift["test_baseline_value_eur"] / months * 3 * scale
    incremental_sales_qtr = baseline_value_qtr * lift_pts / 100
    incremental_margin_qtr = incremental_sales_qtr * margin_pct / 100
    t = arm_table.set_index("pilot_arm")
    quarters = max(weeks / 13, 1e-9)
    saving_qtr = ((t.loc["control", "cost_eur"] / t.loc["control", "physicians"]
                   - t.loc["test", "cost_eur"] / t.loc["test", "physicians"]) * t.loc["test", "physicians"]
                  / quarters * scale)
    counted_saving = saving_qtr if count_touch_savings else 0.0
    net_qtr = incremental_margin_qtr + counted_saving - fee
    break_even = max(0.0, (fee - counted_saving) / (baseline_value_qtr * margin_pct / 100) * 100) \
        if baseline_value_qtr else None
    gate = spec.assumptions()["pilot_gates"]["quarterly"]["brick_lift_vs_control_min_pct"]
    at_risk = a["share_of_fee_at_risk_on_lift"] * fee if lift_pts < gate else 0.0
    return {"fee_per_quarter_eur": round(fee), "margin_pct": margin_pct, "scale": scale, "lift_pts_used": float(lift_pts),
            "baseline_sales_per_quarter_eur": round(baseline_value_qtr),
            "baseline_is_synthetic": not brand_sales_per_quarter_eur,
            "incremental_sales_per_quarter_eur": round(incremental_sales_qtr),
            "incremental_margin_per_quarter_eur": round(incremental_margin_qtr),
            "touch_cost_saving_per_quarter_eur": round(saving_qtr), "count_touch_savings": count_touch_savings,
            "net_benefit_per_quarter_eur": round(net_qtr),
            "return_on_fee": round(float((incremental_margin_qtr + counted_saving) / fee), 2) if fee else None,
            "break_even_lift_pts": round(break_even, 2) if break_even is not None else None,
            "fee_at_risk_eur": round(at_risk)}


def gates(arm_table: pd.DataFrame, lift: dict, consent: dict, weekly_df: pd.DataFrame) -> list[dict]:
    g = spec.assumptions()["pilot_gates"]
    t = arm_table.set_index("pilot_arm")
    recent = weekly_df[weekly_df.suggestions > 0].tail(4)
    acceptance = float((recent.acceptance_pct * recent.suggestions).sum() / max(recent.suggestions.sum(), 1)) / 100
    checks = [
        ("Weekly", "Reps accept suggestions (last 4 weeks)", acceptance * 100, g["weekly"]["suggestion_acceptance_min"] * 100,
         ">=", "%"),
        ("Weekly", "Email consent growth in test territories, per month", consent.get("test", {}).get("growth_pct_per_month", 0),
         g["weekly"]["consent_growth_min_pct_per_month"], ">=", "%"),
        ("Weekly", "Physicians reached in test territories", float(t.loc["test", "reach_pct"]), g["weekly"]["reach_min_pct"],
         ">=", "%"),
        ("Quarterly", "Brick sales lift, test vs control", lift.get("lift_pts", 0.0),
         g["quarterly"]["brick_lift_vs_control_min_pct"], ">=", " pts"),
        ("Quarterly", "Cost per engaged physician in test territories", float(t.loc["test", "cost_per_engaged_eur"]),
         g["quarterly"]["cost_per_engaged_hcp_max"], "<=", " EUR"),
    ]
    return [{"cadence": c, "gate": name, "value": round(float(v), 1), "target": target, "rule": op, "unit": unit,
             "passed": bool(v >= target if op == ">=" else v <= target)} for c, name, v, target, op, unit in checks]


def spend(con, start, end, arm_table: pd.DataFrame) -> dict:
    """The budget-neutral check: touches and cost per physician in test against control, overall and by channel."""
    _touches_view(con, start, end)
    cost = spec.assumptions()["touch_cost"]
    t = arm_table.set_index("pilot_arm")
    # Touches to the same physicians the per-physician figures divide by (active, promotable, not medical-only),
    # so neither arm is credited or charged for contacts outside that population.
    ch = con.execute("""select t.pilot_arm, t.channel, count(*) as touches from pilot_touches t
                        join account_vod a on a.id = t.account_id join hcp_master_opendata m on m.onekey_id = a.onekey_id
                        where a.account_type = 'hcp' and a.status = 'active' and not m.no_promo_flag
                          and a.hcp_role <> 'medical_only_contact' group by all""").df()
    ch = ch.pivot(index="channel", columns="pilot_arm", values="touches").fillna(0)
    rows = []
    for c, r in ch.iterrows():
        tp, cp = r.get("test", 0) / t.loc["test", "physicians"], r.get("control", 0) / t.loc["control", "physicians"]
        rows.append({"channel": c, "test_per_physician": round(float(tp), 2), "control_per_physician": round(float(cp), 2),
                     "cost_per_touch_eur": cost.get(c)})
    per = {a: {"touches": float(sum(ch.loc[c, a] for c in ch.index if a in ch.columns) / t.loc[a, "physicians"]),
               "cost": float(sum(ch.loc[c, a] * cost.get(c, 0) for c in ch.index if a in ch.columns) / t.loc[a, "physicians"])}
           for a in ("test", "control")}
    diff = lambda k: round(100 * (per["test"][k] / per["control"][k] - 1), 1) if per["control"][k] else None  # noqa: E731
    out = {"test_touches_per_physician": round(per["test"]["touches"], 2),
           "control_touches_per_physician": round(per["control"]["touches"], 2),
           "test_cost_per_physician_eur": round(per["test"]["cost"], 1),
           "control_cost_per_physician_eur": round(per["control"]["cost"], 1),
           "touches_diff_pct": diff("touches"), "cost_diff_pct": diff("cost"), "by_channel": rows,
           "tolerance_pct": 5.0}
    # Budget neutral means the money: spend per physician within the tolerance (touch counts differ with the mix).
    out["equal"] = out["cost_diff_pct"] is not None and abs(out["cost_diff_pct"]) <= out["tolerance_pct"]
    # Against the plan: what the test territories were budgeted (last year's touches, pro rata for the weeks run)
    # and what they spent on the planned channels.
    cp = data.read_table("call_plan", None)
    if len(cp):
        arm = con.execute("select a.id, tv.pilot_arm from account_vod a join territory_vod tv on tv.id = a.territory_id").df()
        cp = cp.merge(arm, left_on="account_id", right_on="id")
        cp = cp[cp.pilot_arm == "test"]
        weeks = (end - start).days / 7
        cyc = spec.assumptions()["planning"]["cycle_weeks"]
        per_cycle = cp.groupby("cycle").apply(lambda g: (g.last_year_touches * g.channel.map(cost)).sum(), include_groups=False)
        budget = sum(per_cycle.get(i + 1, per_cycle.iloc[-1]) * min(max(weeks - i * cyc, 0), cyc) / cyc
                     for i in range(int(-(-weeks // cyc))))
        planned_ch = spec.assumptions()["planning"]["channels"]
        spent = float(sum(r["test_per_physician"] * t.loc["test", "physicians"] * (r["cost_per_touch_eur"] or 0)
                          for r in rows if r["channel"] in planned_ch))
        out.update(plan_budget_eur=round(float(budget)), plan_spent_eur=round(spent),
                   vs_plan_pct=round(100 * (spent / budget - 1), 1) if budget else None)
    return out


def reallocation(data_dir: Path | None = None) -> dict:
    """What the engine moved: planned touches due, moved, and from which segments to which."""
    root = Path(data_dir) if data_dir else spec.data_dir()
    frames = [pd.read_parquet(f, columns=["hcp_id", "channel", "origin", "status"]).assign(week=int(f.parent.name[-2:]))
              for f in sorted((root / "runs").glob("week_*/decisions.parquet"))]
    if not frames:
        return {}
    d = pd.concat(frames, ignore_index=True)
    seg = data.read_table("hcp_segment", data_dir)
    seg_of = seg.sort_values("cycle").drop_duplicates("account_id", keep="last").set_index("account_id").segment \
        if len(seg) else pd.Series(dtype=object)
    planned = d[d.origin == "plan"]
    added = d[(d.origin != "plan") & (d.status == "sent")]
    moved = planned[planned.status == "moved"]
    flow = pd.DataFrame({"segment": list(seg_of.reindex(moved.hcp_id).fillna("other")) + list(seg_of.reindex(added.hcp_id).fillna("other")),
                         "direction": ["out"] * len(moved) + ["in"] * len(added)})
    net = flow.groupby(["segment", "direction"]).size().unstack(fill_value=0).reindex(columns=["out", "in"], fill_value=0)
    net["net"] = net["in"] - net["out"]
    return {"planned_due": int(len(planned)), "delivered_as_planned": int((planned.status == "sent").sum()),
            "moved": int(len(moved)), "blocked": int((planned.status == "blocked").sum()),
            "moved_pct": round(100 * len(moved) / max(len(planned), 1), 1),
            "by_segment": net.reset_index().sort_values("net").to_dict("records"),
            "by_week": d[d.origin == "plan"].groupby("week").status.value_counts().unstack(fill_value=0).reset_index().to_dict("records")}


def report(data_dir: Path | None = None, **return_inputs) -> dict:
    start, end, weeks = _window(data_dir)
    if weeks == 0:
        return {"weeks": 0}
    con = data.connect(data_dir)
    lift = brick_lift(con, start)
    arm_table = arms(con, start, end)
    w = weekly(con, start, end)
    consent = consent_growth(con, start, end, weeks)
    return {"weeks": weeks, "from": f"{start:%d %b %Y}", "to": f"{end - pd.Timedelta(days=1):%d %b %Y}",
            "lift": lift, "arms": arm_table, "monthly_index": monthly_index(con, start), "weekly": w,
            "consent": consent, "gates": gates(arm_table, lift, consent, w),
            "spend": spend(con, start, end, arm_table), "reallocation": reallocation(data_dir),
            "return_model": return_model(lift, arm_table, weeks, **return_inputs)}
