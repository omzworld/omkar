"""What the Segment & plan screen shows: the segmentation, the recommended allocation, the reps' adjustments and,
once the pilot runs, how the plan is being delivered and what the engine moved."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from nba import data, plan, runner, spec

BAND_ORDER = ["high", "medium", "low"]
ADOPT_ORDER = ["early", "building", "established"]


def _cycle_tables(cycle: int, data_dir=None):
    """The cycle's tables as written by the runner, or built on the spot if the pilot has not reached it."""
    seg, cp, bud = (data.read_table(n, data_dir) for n in ("hcp_segment", "call_plan", "segment_budget"))
    if len(seg) and (seg.cycle == cycle).any():
        return seg[seg.cycle == cycle], cp[cp.cycle == cycle], bud[bud.cycle == cycle], True
    s, p, b = plan.build_cycle(cycle, data_dir)
    return s, p, b, False


def summary(cycle: int | None = None, data_dir=None) -> dict:
    done = runner.completed_weeks(data_dir)
    current = plan.cycle_of(max(done, 1))
    cycle = cycle or current
    seg, cp, bud, saved = _cycle_tables(cycle, data_dir)
    cost = spec.assumptions()["touch_cost"]
    c = plan.cfg()
    terr = data.read_table("territory_vod", data_dir).set_index("id").pilot_arm
    arm = data.read_table("account_vod", data_dir).set_index("id").territory_id.map(terr)

    grid = seg.groupby(["potential_band", "adoption_band"]).agg(
        physicians=("account_id", "size"), responsiveness=("responsiveness_score", "mean")).reset_index()
    grid["responsiveness"] = grid.responsiveness.round(0)
    tiers = pd.crosstab(seg.current_tier, seg.potential_band).reindex(columns=BAND_ORDER, fill_value=0)
    movers = seg[seg.moved].copy()
    names = data.read_table("account_vod", data_dir).set_index("id").name
    movers["name"] = movers.account_id.map(names)
    best = seg.best_channel.value_counts().to_dict()

    by_channel = bud.groupby("channel")[["last_year_touches", "recommended_touches", "cost_last_year_eur",
                                          "cost_recommended_eur"]].sum().reset_index()
    final = cp.groupby("channel").final_touches.sum()
    by_channel["final_touches"] = by_channel.channel.map(final).fillna(0).astype(int)
    by_channel["cost_final_eur"] = by_channel.final_touches * by_channel.channel.map(cost)
    seg_view = bud.groupby(["segment", "channel"])[["physicians", "last_year_touches", "recommended_touches"]].sum().reset_index()
    seg_view["change_pct"] = (100 * (seg_view.recommended_touches / seg_view.last_year_touches.replace(0, pd.NA) - 1)).astype(float).round(1)

    inputs = data.read_table("rep_plan_input", data_dir)
    inputs = inputs[pd.to_datetime(inputs.cycle_start) == plan.cycle_start(cycle)].copy()
    inputs["name"] = inputs.account_id.map(names)
    adj = cp[cp.rep_adjusted]
    effect = adj.assign(delta=adj.final_touches - adj.recommended_touches).groupby("channel").delta.sum().to_dict()

    progress = None
    root = Path(data_dir) if data_dir else spec.data_dir()
    st_path = root / "runs" / "plan_state.parquet"
    if done and st_path.exists() and plan.cycle_of(done) == cycle:
        st = pd.read_parquet(st_path)
        st = st[st.account_id.map(arm) == "test"]
        weeks_in = plan.week_in_cycle(done)
        g = st.groupby("segment")[["planned", "delivered", "swaps_out", "pending"]].sum().reset_index()
        g["pro_rata"] = (g.planned * weeks_in / c["cycle_weeks"]).round(0)
        progress = {"weeks_in": weeks_in, "by_segment": g.to_dict("records"),
                    "planned": int(st.planned.sum()), "delivered": int(st.delivered.sum()),
                    "moved": int(st.swaps_out.sum()), "pending": int(st.pending.sum())}

    return {
        "cycle": cycle, "current_cycle": current, "cycles_available": sorted({1, current, cycle}),
        "cycle_start": f"{plan.cycle_start(cycle):%d %b %Y}", "saved": saved, "weeks_run": done,
        "settings": c, "physicians": int(len(seg)),
        "grid": grid.to_dict("records"), "tiers_vs_bands": tiers.reset_index().to_dict("records"),
        "moved": int(seg.moved.sum()), "movers": movers.sort_values("potential_score", ascending=False)[
            ["account_id", "name", "market", "current_tier", "potential_band", "adoption_band", "potential_score",
             "responsiveness_score", "move_reason"]].head(80).to_dict("records"),
        "best_channel": best,
        "by_channel": by_channel.to_dict("records"), "by_segment": seg_view.to_dict("records"),
        "budget_rows": bud.to_dict("records"),
        "rep_inputs": inputs[["account_id", "name", "user_id", "adjustment", "reason"]].to_dict("records"),
        "rep_input_counts": inputs.adjustment.value_counts().to_dict(), "rep_input_effect": effect,
        "progress": progress,
    }


def physicians(cycle: int, segment: str | None = None, data_dir=None, limit: int = 200) -> list[dict]:
    """The physicians in a segment with their scores and planned touches."""
    seg, cp, _, _ = _cycle_tables(cycle, data_dir)
    if segment:
        seg = seg[seg.segment == segment]
    wide = cp.pivot_table(index="account_id", columns="channel", values="final_touches", aggfunc="sum", fill_value=0)
    names = data.read_table("account_vod", data_dir).set_index("id").name
    out = seg.assign(name=seg.account_id.map(names)).join(wide, on="account_id").fillna(0)
    return out.sort_values("potential_score", ascending=False).head(limit).to_dict("records")
