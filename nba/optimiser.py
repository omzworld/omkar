"""The optimiser: score allowed candidates by expected return and decide what is sent this week.

expected return = chance of response x value of response x decay - cost of touch

Chance comes in three tiers (rules R051-R053): the physician's own response rate on that channel if they have
at least 10 touches; else the segment's (market x specialty x channel) if it has at least 50; else the IQVIA
channel preference benchmark. Value is the yearly value of moving the physician one journey stage
(return_assumptions.yaml), over the value horizon, weighted by their potential. Cost is the touch cost.

Selection, in the order of spec/examples/optimiser_example.md:
1. drop candidates with a negative expected return;
2 and 3. walk candidates from the highest return down and give each physician the first action whose rep, key
   account manager or agency still has a slot (so a physician whose best channel is full gets their next best);
4. a physician left without any action gets a cheaper substitute for their top choice (visit -> rep email), if it
   has a positive return and capacity;
5. drop anything whose return is not positive.
Every candidate leaves with a status (sent, substituted, not_sent) and a reason.

The rules-to-score dial: 1.0 ranks purely by expected return (the optimiser decides); 0.0 ranks purely by rule
priority and keeps negative returns (the rules decide, as a rules-only engine would). In between, a blend.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nba import data, spec
from nba.segments import specialty_weight

STAGES = ["curiosity", "consideration", "experience", "loyalty", "advocacy"]
# Where a channel has no history of its own, borrow the closest one for the chance of response.
CHANCE_PROXY = {"kam_visit": "rep_visit", "kam_brief": "rep_visit"}
RESOURCE = {"rep_visit": ("rep_visit", "rep_user_id"), "remote_call": ("remote_call", "rep_user_id"),
            "rep_email": ("rep_email", "rep_user_id"), "kam_visit": ("kam_visit", "kam_user_id"),
            "kam_brief": ("kam_brief", "kam_user_id"), "marketing_email": ("marketing_email", "market"),
            "webinar": ("webinar", "market")}


# ---------------------------------------------------------------------------------------------- scoring

def chance(c: pd.DataFrame, data_dir=None) -> pd.DataFrame:
    """Chance of response and which tier it came from."""
    a = spec.assumptions()["chance_tiers"]
    bench = data.read_table("iqvia_channel_preference", data_dir)
    proxy = c.channel.map(lambda ch: CHANCE_PROXY.get(ch, ch))
    b = c[["market", "specialty"]].assign(channel=proxy).merge(bench, on=["market", "specialty", "channel"], how="left")
    market_avg = bench.groupby(["market", "channel"]).response_benchmark.mean()
    fallback = pd.Series([market_avg.get((m, ch), 0.1) for m, ch in zip(c.market, proxy)], index=c.index)
    benchmark = pd.Series(b.response_benchmark.to_numpy(), index=c.index).fillna(fallback)
    own = c.hcp_touch_count_channel >= a["tier1_min_touches"]
    seg = ~own & (c.segment_touch_count_channel >= a["tier2_min_segment_touches"])
    c = c.copy()
    c["chance_tier"] = np.select([own, seg], ["own_history", "segment"], "benchmark")
    c["probability_of_response"] = np.select(
        [own, seg], [c.hcp_response_rate_channel, c.segment_response_rate_channel], benchmark).astype(float).round(3)
    return c


def _stage_value(brand: str, market: str, stage: str | None, step: int) -> float:
    """Yearly value of a stage move: step=+1 the next move, step=0 the move into the current stage."""
    table = spec.assumptions()["stage_move_value"].get(brand, {})
    moves = table.get(market, {})
    if not moves:
        return np.nan
    i = STAGES.index(stage) if stage in STAGES else 1
    i = i if step == 1 else i - 1
    if i < 0:
        return 0.0
    if i >= len(STAGES) - 1:                         # an advocate cannot move up: maintenance value
        return 0.5 * moves.get("loyalty_to_advocacy", min(moves.values()))
    key = f"{STAGES[i]}_to_{STAGES[i + 1]}"
    return moves.get(key, 0.5 * min(moves.values()))


def value(c: pd.DataFrame) -> pd.Series:
    """Value of a response in EUR."""
    a = spec.assumptions()
    horizon = a.get("value_horizon_years", 1)
    w = specialty_weight()
    hcp = c.account_type == "hcp"
    # Potential: specialty weight x brick potential x practice size relative to similar practices (same market and
    # practice type), capped so one physician is worth between a quarter and four times the average.
    size = np.log1p(c.practice_size.astype(float).fillna(1))
    peers = [c.market, c.practice_type.fillna("none")]
    size_rel = (size / size.groupby(peers).transform("mean")).fillna(1)
    potential = np.where(hcp, (c.specialty.map(w).fillna(0.6).astype(float)
                               * c.brick_potential_index.astype(float).fillna(100) / 100 * size_rel).clip(0.25, 4), 1.0)
    step = np.where(c.trigger_type == "risk", 0, 1)
    stage_value = np.array([_stage_value(b, m, s, k) for b, m, s, k in zip(c.brand, c.market, c.stage, step)])
    # Plenvu/Moviprep is valued on endoscopy procedures: EUR per point of share gained in the physician's unit.
    plenvu = a["stage_move_value"]["Plenvu_Moviprep"]["value_per_procedure_point"]
    unit_value = plenvu * 4 * c.unit_colonoscopies_qtr.astype(float).fillna(1000) / 100
    unit_value = np.where(hcp, 0.5 * unit_value, unit_value)
    v = np.where(c.brand == "Plenvu_Moviprep", unit_value, np.nan_to_num(stage_value) * potential)
    # A unit losing share to a competitor puts that share at risk.
    comp = a["risk_value"]["competitor_share_point"] * c.unit_competitor_share_change.astype(float).clip(lower=0).fillna(0)
    v = v + np.where(c.trigger_type == "risk", comp.to_numpy(), 0)
    return pd.Series(np.round(v * horizon, 2), index=c.index)


def expected_return(probability, value_eur, cost_eur, decay=1.0):
    """Chance of response x value of response x decay - cost of touch."""
    return (probability * value_eur * decay - cost_eur).round(2) if hasattr(probability, "round") \
        else round(probability * value_eur * decay - cost_eur, 2)


def score(c: pd.DataFrame, feats, data_dir=None) -> pd.DataFrame:
    """Add chance, value, cost, decay and expected return, for the candidate and for its substitute channel."""
    from nba.candidates import _history
    a = spec.assumptions()
    cost = a["touch_cost"]
    c = chance(c, data_dir)
    c["value_of_response"] = value(c)
    c["cost_of_touch"] = c.channel.map(cost).astype(float)
    c["decay_factor"] = (1 - a["decay_per_week_waiting"]) ** c.weeks_waiting.astype(float)
    c["expected_return"] = expected_return(c.probability_of_response, c.value_of_response, c.cost_of_touch,
                                           c.decay_factor)
    # The substitute (e.g. a rep email instead of a visit): same value, its own chance and cost.
    c["substitute_probability"] = np.nan
    has = c.substitute_channel.notna()
    if has.any():
        sub = c[has].assign(channel=c.loc[has, "substitute_channel"])
        sub = chance(_history(sub, feats), data_dir)
        c.loc[has, "substitute_probability"] = sub.probability_of_response.to_numpy()
    sub_cost = c.substitute_channel.map(cost).astype(float)
    c["substitute_return"] = expected_return(c.substitute_probability, c.value_of_response, sub_cost, c.decay_factor)
    return c


# ---------------------------------------------------------------------------------------------- selection

def capacity(feats_as_of: pd.Timestamp, data_dir=None) -> dict:
    """Slots this week per (resource, owner)."""
    cap = spec.constraint_table("capacity").set_index("unit").default_per_week
    rc = data.read_table("rep_capacity", data_dir)
    rc = rc[pd.to_datetime(rc.week) == feats_as_of]
    users = data.read_table("user_vod", data_dir).set_index("id").role
    slots = {}
    for _, r in rc.iterrows():
        if users.get(r.user_id) == "rep":
            slots[("rep_visit", r.user_id)] = int(r.visit_slots_open)
            slots[("rep_email", r.user_id)] = int(r.email_slots_open)
            slots[("remote_call", r.user_id)] = 0 if r.on_leave else int(cap["remote_call"])
        elif users.get(r.user_id) == "kam":
            slots[("kam_visit", r.user_id)] = int(r.visit_slots_open)
            slots[("kam_brief", r.user_id)] = 0 if r.on_leave else int(cap["kam_brief"])
    for m in spec.design()["markets"]:
        slots[("marketing_email", m)] = int(cap["marketing_email"]) * 2   # two send windows a week
        slots[("webinar", m)] = int(cap["webinar"])
    return slots


def _resource(channel: pd.Series, c: pd.DataFrame) -> pd.Series:
    owners = []
    for ch, (_, row) in zip(channel, c.iterrows()):
        res, owner_col = RESOURCE.get(ch, (ch, "market"))
        owners.append((res, row.get(owner_col)))
    return pd.Series(owners, index=c.index, dtype=object)


def select(c: pd.DataFrame, slots: dict, dial: float = 1.0) -> pd.DataFrame:
    """Decide what is sent. `c` needs: candidate_id, hcp_id, channel, priority, expected_return, verdict, the owner
    columns (rep_user_id, kam_user_id, market), substitute_channel and substitute_return."""
    c = c.copy()
    c["status"], c["final_channel"], c["final_return"], c["not_sent_reason"] = "held", c.channel, np.nan, None
    pool = c.verdict == "allowed"
    c.loc[~pool, "status"] = "not_sent"
    c.loc[~pool, "not_sent_reason"] = c.loc[~pool, "constraint_reason"]

    er = c.expected_return.astype(float)
    scale = max(er[pool].abs().max(), 1e-9) if pool.any() else 1.0
    c["rank_score"] = (1 - dial) * c.priority.astype(float) / 100 + dial * er / scale

    if dial > 0:                                                            # 1. negative return
        neg = pool & (er < 0)
        c.loc[neg, ["status", "not_sent_reason"]] = ["not_sent", None]
        c.loc[neg, "not_sent_reason"] = [f"Not sent: expected return {v:.0f} is not positive" for v in er[neg]]
        pool &= ~neg

    # 2 + 3. Best action per physician that still has capacity: walk all candidates from the highest rank down;
    # a physician gets the first one whose rep, KAM or agency still has a slot.
    order = c[pool].sort_values(["rank_score", "candidate_id"], ascending=[False, True])
    left = dict(slots)
    c["resource"] = None
    if len(order):
        c.loc[order.index, "resource"] = _resource(order.channel, order)
    assigned, first_failed, failed = set(), {}, []
    for i in order.index:
        h = c.at[i, "hcp_id"]
        if h in assigned:
            c.at[i, "status"] = "not_sent"
            c.at[i, "not_sent_reason"] = "Not sent: another action for this physician has a higher return"
            continue
        key = c.at[i, "resource"]
        if left.get(key, 0) > 0:
            left[key] -= 1
            c.at[i, "status"], c.at[i, "final_return"] = "sent", er[i]
            assigned.add(h)
        else:
            failed.append(i)
            first_failed.setdefault(h, i)

    def no_slot(i):
        res, owner = c.at[i, "resource"]
        c.at[i, "status"] = "not_sent"
        c.at[i, "not_sent_reason"] = (f"Not sent: no {res.replace('_', ' ')} slots left for {owner}"
                                      if not pd.isna(owner) else
                                      f"Not sent: no one to deliver a {res.replace('_', ' ')} (vacant territory)")

    # 4. Physicians still without an action: substitute a cheaper channel for their top choice.
    tops = [i for h, i in first_failed.items() if h not in assigned]
    tops.sort(key=lambda i: -(c.at[i, "substitute_return"] if pd.notna(c.at[i, "substitute_return"]) else -np.inf))
    for i in tops:
        sub_ch, sub_er = c.at[i, "substitute_channel"], c.at[i, "substitute_return"]
        sub_ok = c.at[i, "substitute_allowed"] if "substitute_allowed" in c else True
        key = _resource(pd.Series([sub_ch]), c.loc[[i]]).iloc[0] if pd.notna(sub_ch) else None
        if pd.notna(sub_ch) and sub_ok and pd.notna(sub_er) and sub_er > 0 and left.get(key, 0) > 0:
            left[key] -= 1
            c.at[i, "status"], c.at[i, "final_channel"], c.at[i, "final_return"] = "substituted", sub_ch, sub_er
            c.at[i, "resource"] = key
            c.at[i, "not_sent_reason"] = (f"Capacity full for {c.at[i, 'channel'].replace('_', ' ')}: "
                                          f"sent as {sub_ch.replace('_', ' ')} instead")
            assigned.add(c.at[i, "hcp_id"])
        else:
            no_slot(i)
    for i in failed:
        if c.at[i, "status"] == "held":
            no_slot(i)

    if dial > 0:                                                            # 5. not positive
        flat = c.status.isin(["sent", "substituted"]) & (c.final_return <= 0)
        c.loc[flat, "status"] = "not_sent"
        c.loc[flat, "not_sent_reason"] = "Not sent: expected return is not positive"
    sent = c.status.isin(["sent", "substituted"])
    c.loc[sent, "rank"] = c[sent].groupby(c.loc[sent, "resource"].astype(str)).final_return \
        .rank(ascending=False, method="first")
    return c
