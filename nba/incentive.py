"""A simulated rep incentive tracker for the quarter (spec/assumptions/return_assumptions.yaml, `incentive`).

Illustrative only: Norgine's real scheme is not modelled. Three measures, each turned into an achievement %:
- plan: planned contacts (visits, remote calls, rep emails) done so far against the plan's share to date;
- sales: Movicol units in the rep's bricks over the last 3 completed months against the same months a year before,
  against the growth target (each point over target adds `sales_points_per_pct`);
- follow-through: suggestions acted on, of those the rep answered this quarter, against the target.
The weighted achievement maps to a payout % of the target bonus: nothing below the threshold, then linear up to 100%
at 100% achievement, then linear to the cap.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from nba import data, features, plan, runner, spec

REP_CHANNELS = ["rep_visit", "remote_call", "rep_email"]


def _cfg() -> dict:
    return spec.assumptions()["incentive"]


def payout(achievement: float) -> float:
    c = _cfg()
    t, pt, cap, pc = c["threshold_pct"], c["payout_at_threshold_pct"], c["cap_pct"], c["payout_at_cap_pct"]
    if achievement < t:
        return 0.0
    if achievement <= 100:
        return pt + (100 - pt) * (achievement - t) / (100 - t)
    return min(pc, 100 + (pc - 100) * (achievement - 100) / (cap - 100))


def _scores(planned_to_date: float, done: float, growth: float | None, acted: int, answered: int) -> dict:
    c = _cfg()
    plan_ach = 100.0 if planned_to_date <= 0 else 100 * done / planned_to_date
    sales_ach = 100.0 if growth is None else 100 + c["sales_points_per_pct"] * (growth - c["sales_growth_target_pct"])
    ft = 100 * acted / answered if answered else None
    ft_ach = 100.0 if ft is None else 100 * ft / c["follow_through_target_pct"]
    parts = {"plan": max(0.0, min(plan_ach, 150)), "sales": max(0.0, min(sales_ach, 150)),
             "follow_through": max(0.0, min(ft_ach, 150))}
    overall = sum(c["weights"][k] * v for k, v in parts.items())
    return {"parts": parts, "achievement": overall, "payout_pct": payout(overall), "follow_through_pct": ft}


def _all_reps(week: int, data_dir) -> pd.DataFrame:
    """The inputs for every test rep: plan to date, done, sales growth, suggestions answered and acted on."""
    root = Path(data_dir) if data_dir else spec.data_dir()
    terr = data.read_table("territory_vod", data_dir)
    terr = terr[(terr.pilot_arm == "test") & terr.rep_user_id.notna()]
    acc = data.read_table("account_vod", data_dir)[["id", "territory_id", "brick_id"]]
    wk = plan.week_in_cycle(week)
    weeks_q = spec.assumptions()["planning"]["cycle_weeks"]
    st = pd.read_parquet(root / "runs" / f"week_{week:02d}" / "plan_state_before.parquet")
    st = st[st.channel.isin(REP_CHANNELS)].merge(acc, left_on="account_id", right_on="id")
    pl = st.groupby("territory_id").agg(planned=("planned", "sum"), done=("delivered", "sum"))
    pl["planned_to_date"] = pl.planned * (wk - 1) / weeks_q
    as_of = features.as_of(week)
    sales = data.read_table("iqvia_brick_sales", data_dir)
    sales = sales[(sales["product"] == "Movicol") & (pd.to_datetime(sales.month) < as_of.to_period("M").to_timestamp())]
    sales["month"] = pd.to_datetime(sales.month)
    last = sorted(sales.month.unique())[-3:]
    prior = [m - pd.DateOffset(years=1) for m in last]
    bricks = acc.dropna(subset=["brick_id"]).drop_duplicates(["territory_id", "brick_id"])
    s = sales.merge(bricks, on="brick_id")
    now = s[s.month.isin(last)].groupby("territory_id").units.sum()
    before = s[s.month.isin(prior)].groupby("territory_id").units.sum()
    growth = (100 * (now / before - 1)).round(1)
    sug = data.read_table("suggestion_vod", data_dir)
    start = plan.cycle_start(plan.cycle_of(week))
    sug = sug[(pd.to_datetime(sug.suggested_date) >= start) & (pd.to_datetime(sug.suggested_date) < as_of)]
    ans = sug[sug.status.isin(["accepted", "dismissed"])].groupby("user_id").status.agg(
        answered="size", acted=lambda x: int((x == "accepted").sum()))
    rows = []
    for t in terr.itertuples():
        p = pl.loc[t.id] if t.id in pl.index else None
        a = ans.loc[t.rep_user_id] if t.rep_user_id in ans.index else None
        rows.append({"rep": t.rep_user_id, "territory": t.id, "name": t.name, "market": t.market,
                     "planned_quarter": int(p.planned) if p is not None else 0,
                     "planned_to_date": float(p.planned_to_date) if p is not None else 0.0,
                     "done": int(p.done) if p is not None else 0,
                     "growth": None if t.id not in growth.index or pd.isna(growth[t.id]) else float(growth[t.id]),
                     "acted": int(a.acted) if a is not None else 0, "answered": int(a.answered) if a is not None else 0})
    df = pd.DataFrame(rows)
    sc = [_scores(r.planned_to_date, r.done, r.growth, r.acted, r.answered) for r in df.itertuples()]
    df["achievement"] = [x["achievement"] for x in sc]
    df["payout_pct"] = [x["payout_pct"] for x in sc]
    return df


def tracker(user: str, week: int | None = None, data_dir=None) -> dict:
    done_weeks = runner.completed_weeks(data_dir)
    if not done_weeks:
        return {"weeks_run": 0}
    week = min(max(int(week or done_weeks), 1), done_weeks)
    c = _cfg()
    df = _all_reps(week, data_dir)
    if user not in set(df.rep):
        raise KeyError(f"No test rep {user}")
    me = df[df.rep == user].iloc[0]
    s = _scores(me.planned_to_date, me.done, me.growth, me.acted, me.answered)
    peers = df[df.market == me.market].sort_values(["achievement", "rep"], ascending=[False, True]).reset_index(drop=True)
    rank = int(peers.index[peers.rep == user][0]) + 1
    bonus = c["target_bonus_per_quarter_eur"]
    # What would move the payout: the contacts the rep is behind on, and acting on the next three suggestions.
    hints = []
    short = int(round(me.planned_to_date - me.done))
    if short > 0:
        up = _scores(me.planned_to_date, me.done + short, me.growth, me.acted, me.answered)["payout_pct"] - s["payout_pct"]
        hints.append(f"Catch up the {short} planned contacts you are behind on: +{up:.0f}% of target bonus (about €{bonus * up / 100:,.0f})")
    up3 = _scores(me.planned_to_date, me.done, me.growth, me.acted + 3, me.answered + 3)["payout_pct"] - s["payout_pct"]
    if up3 > 0.5:
        hints.append(f"Act on your next three suggestions: +{up3:.0f}% (about €{bonus * up3 / 100:,.0f})")
    if me.growth is not None and me.growth < c["sales_growth_target_pct"]:
        hints.append(f"Brick sales are {me.growth:+.1f}% against a {c['sales_growth_target_pct']:+.1f}% target: "
                     "the defend-the-brick suggestions are where this is won back")
    wk = plan.week_in_cycle(week)
    return {
        "weeks_run": done_weeks, "week": week, "rep": user, "territory": me.territory, "market": me.market,
        "quarter": plan.cycle_of(week), "week_in_quarter": wk, "quarter_weeks": spec.assumptions()["planning"]["cycle_weeks"],
        "measures": [
            {"key": "plan", "label": "Planned contacts done", "weight": c["weights"]["plan"],
             "actual": f"{int(me.done)} of {me.planned_to_date:.0f} due so far ({int(me.planned_quarter)} in the quarter)",
             "achievement": round(s["parts"]["plan"])},
            {"key": "sales", "label": "Movicol sales in your bricks", "weight": c["weights"]["sales"],
             "actual": "no sales data yet" if me.growth is None else f"{me.growth:+.1f}% against a year before (target {c['sales_growth_target_pct']:+.1f}%)",
             "achievement": round(s["parts"]["sales"])},
            {"key": "follow_through", "label": "Suggestions acted on", "weight": c["weights"]["follow_through"],
             "actual": "none answered yet" if not me.answered else f"{int(me.acted)} of {int(me.answered)} answered (target {c['follow_through_target_pct']}%)",
             "achievement": round(s["parts"]["follow_through"])}],
        "achievement": round(s["achievement"]), "payout_pct": round(s["payout_pct"]),
        "payout_eur": round(bonus * s["payout_pct"] / 100), "target_bonus_eur": bonus,
        "curve": {k: c[k] for k in ("threshold_pct", "payout_at_threshold_pct", "cap_pct", "payout_at_cap_pct")},
        "rank": rank, "of": len(peers), "hints": hints,
        "note": "Simulated for the demo. Weights, targets and the payout curve are set in return_assumptions.yaml.",
    }
