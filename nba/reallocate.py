"""Weekly reallocation inside the baseline plan: same touches, same budget, moved to where they are needed now.

The week starts from the reps' plan: every touch due this week (nba.plan.due) is a candidate with origin 'plan'.
Trigger rules (risk and opportunity) add candidates with origin 'rule'. Both have been through the constraints
engine and the optimiser's scoring. Then, per rep and channel (or per market for marketing email):

1. Planned touches go ahead. A hard block (consent, opt-out, eligibility) drops the touch for the cycle and its
   slot goes to the best eligible trigger candidate of the same rep and channel, so the total holds. Cadence
   delays do not apply to the plan, which is already evenly spaced; they apply to the engine's own additions.
2. Trigger candidates, best expected return first, may take the slot of a planned touch (a swap): the planned
   touch with the lowest expected return in the same rep's same channel moves to the trigger's physician, if the
   trigger beats it by at least `swap_margin_eur` and the planned touch is not protected. A moved touch is not
   rescheduled: that physician gets one fewer this cycle, so the rep's total stays on plan.
   Protected: a physician who already gave up a planned touch on this channel this cycle; a high-potential
   physician at their visit floor; a physician in a segment running below its plan by more than `segment_band`.
   Swaps stop when the rep has moved `reallocation_cap` of their planned touches this cycle (accruing week by
   week, so the allowance is spread through the quarter). Swaps are like for
   like: a visit for a visit, an email for an email.
3. A physician gets at most one touch per channel a week. Everything else leaves with a reason.
Total touches per rep and channel never exceed the plan, so spend stays as planned.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from nba import plan
from nba.optimiser import _resource

LABEL = {"rep_visit": "visit", "remote_call": "remote call", "rep_email": "rep email", "marketing_email": "email"}


def select(c: pd.DataFrame, state: pd.DataFrame, week: int, dial: float = 1.0) -> pd.DataFrame:
    """Decide the week inside the plan. Returns `c` with status, final_channel, final_return, not_sent_reason,
    reallocated, replaces (the planned candidate a swap displaced, with its physician, asset and brand) and resource.
    dial: 0 follows the plan exactly (no reallocation); 1 reallocates up to the cap; in between, a share of it."""
    cfg = plan.cfg()
    channels = set(cfg["channels"])
    c = c.copy()
    c["status"], c["final_channel"], c["final_return"], c["not_sent_reason"] = "not_sent", c.channel, np.nan, None
    c["reallocated"], c["replaces"] = False, None
    c["replaces_hcp"], c["replaces_asset"], c["replaces_brand"] = None, None, None
    c["resource"] = _resource(c.channel, c) if len(c) else pd.Series(dtype=object)
    er = c.expected_return.astype(float)
    is_plan = c.origin == "plan"
    allowed = c.verdict == "allowed"

    # 1. The plan: allowed planned touches go ahead; held ones are postponed and free their slot.
    # The plan is already evenly spaced, so cadence delays (written for engine suggestions) do not hold a planned
    # touch; hard blocks (consent, opt-out, asset rules) do.
    go = is_plan & c.verdict.isin(["allowed", "delayed"])
    c.loc[go, "status"] = "sent"
    c.loc[go, "final_return"] = er[go]
    held = is_plan & ~go
    c.loc[held, "status"] = "blocked"
    c.loc[held, "not_sent_reason"] = [f"Blocked: {str(r).removeprefix('Blocked: ')}; the slot goes to the next best physician"
                                      for r in c.loc[held, "constraint_reason"].fillna("held")]
    free = c[held].groupby(c.loc[held, "resource"].astype(str)).candidate_id.apply(list).to_dict()

    # Guardrails: each rep's swap budget for the cycle, and segments running below their band.
    st = state.copy()
    owner_plan = st[st.user_id.notna()].groupby("user_id").planned.sum()
    # Swaps already used this cycle: each planned touch counts how often it was moved (nba.plan.record).
    used = st[st.user_id.notna()].groupby("user_id").swaps_out.sum().to_dict()
    # The allowance accrues through the cycle: by week k a rep may have moved cap x k / cycle_weeks of the plan.
    k = plan.week_in_cycle(week)
    cap = cfg["reallocation_cap"] * max(min(dial, 1.0), 0.0) * k / cfg["cycle_weeks"]
    swaps_left = {u: max(int(math.floor(cap * n)) - int(used.get(u, 0)), 0) for u, n in owner_plan.items()}
    mkt = st[st.channel == "marketing_email"]
    for m, g in mkt.groupby(mkt.account_id.str[:2]):                                     # market from the id
        swaps_left[m] = max(int(math.floor(cap * g.planned.sum())) - int(g.swaps_out.sum()), 0)
    seg = st.groupby("segment")[["planned", "delivered"]].sum()
    pro_rata = seg.planned * (k - 1) / cfg["cycle_weeks"]
    behind = set(seg.index[seg.delivered < pro_rata * (1 - cfg["segment_band"])]) if k > 1 else set()
    rows = st.set_index(["account_id", "channel"])
    moved_before, planned_n = rows.swaps_out, rows.planned
    seg_of = st.drop_duplicates("account_id").set_index("account_id").segment
    floor = cfg["floor_high_potential_visits"]

    def protected(a, chn):
        if moved_before.get((a, chn), 0) > 0 or seg_of.get(a) in behind:
            return True
        return chn == "rep_visit" and str(seg_of.get(a, "")).startswith("High") and planned_n.get((a, chn), 0) <= floor

    # 2. Trigger candidates, best first.
    trig = c[~is_plan & allowed & (er > 0) & c.channel.isin(channels)].sort_values(
        ["expected_return", "candidate_id"], ascending=[False, True])
    taken = set(zip(c.loc[c.status == "sent", "hcp_id"], c.loc[c.status == "sent", "channel"]))
    for i in trig.index:
        h, ch, key = c.at[i, "hcp_id"], c.at[i, "channel"], c.at[i, "resource"]
        owner = key[1]
        if (h, ch) in taken:
            c.at[i, "not_sent_reason"] = f"Covered: this physician already has a {LABEL.get(ch, ch)} this week"
            continue
        skey = str(key)
        if free.get(skey):                               # a blocked planned touch's slot: use it, no swap needed
            gone = free[skey].pop(0)
            c.at[i, "replaces"] = gone
            c.at[i, "status"], c.at[i, "final_return"], c.at[i, "reallocated"] = "sent", er[i], True
            taken.add((h, ch))
            continue
        if swaps_left.get(owner, 0) <= 0:
            c.at[i, "not_sent_reason"] = ("Not sent: following the plan (dial at 0)" if dial <= 0 else
                                          "Not sent: this rep's share of planned touches to move this quarter is used up")
            continue
        pool = c[(c.status == "sent") & (c.origin == "plan") & (c.resource.astype(str) == skey)]
        if len(pool):
            pool = pool[~np.array([protected(a, chn) for a, chn in zip(pool.hcp_id, pool.channel)], dtype=bool)]
        if pool.empty:
            c.at[i, "not_sent_reason"] = "Not sent: every planned touch this week is protected"
            continue
        j = pool.sort_values(["expected_return", "candidate_id"]).index[0]
        if er[i] < er[j] + cfg["swap_margin_eur"]:
            c.at[i, "not_sent_reason"] = (f"Not sent: the planned {LABEL.get(ch, ch)} it would replace is worth as much "
                                          f"(EUR {er[j]:.0f} against {er[i]:.0f})")
            continue
        c.at[j, "status"] = "moved"
        c.at[j, "not_sent_reason"] = (f"Moved to {h} this week ({c.at[i, 'reason'][:90]}); one fewer planned "
                                      f"{LABEL.get(ch, ch)} for this physician this quarter, so the total stays on plan")
        c.at[i, "replaces"] = c.at[j, "candidate_id"]
        c.at[i, "replaces_hcp"], c.at[i, "replaces_brand"] = c.at[j, "hcp_id"], c.at[j, "brand"]
        c.at[i, "replaces_asset"] = c.at[j, "asset_id"] if pd.notna(c.at[j, "asset_id"]) else None
        taken.discard((c.at[j, "hcp_id"], c.at[j, "channel"]))
        swaps_left[owner] = swaps_left.get(owner, 0) - 1
        c.at[i, "status"], c.at[i, "final_return"], c.at[i, "reallocated"] = "sent", er[i], True
        taken.add((h, ch))
    # Slots freed by blocked planned touches that no worthwhile trigger took: the budget is already committed, so
    # they go to the best remaining eligible candidate of the same rep and channel, whatever its expected return.
    for skey, gone in free.items():
        while gone:
            pool = c[~is_plan & allowed & (c.status == "not_sent") & (c.resource.astype(str) == skey)
                     & c.channel.isin(channels)]
            pool = pool[[(h, chn) not in taken for h, chn in zip(pool.hcp_id, pool.channel)]]
            if pool.empty:
                break
            i = pool.sort_values(["expected_return", "candidate_id"], ascending=[False, True]).index[0]
            c.at[i, "replaces"] = gone.pop(0)
            c.at[i, "status"], c.at[i, "final_return"], c.at[i, "reallocated"] = "sent", er[i], True
            c.at[i, "not_sent_reason"] = None
            taken.add((c.at[i, "hcp_id"], c.at[i, "channel"]))
    rest = ~is_plan & (c.status == "not_sent") & c.not_sent_reason.isna()
    c.loc[rest & ~allowed, "not_sent_reason"] = c.loc[rest & ~allowed, "constraint_reason"]
    c.loc[rest & allowed & (er <= 0), "not_sent_reason"] = "Not sent: expected return is not positive"
    c.loc[rest & allowed & ~c.channel.isin(channels), "not_sent_reason"] = \
        "Not sent: key account managers keep their own plan in this pilot"
    c.loc[c.status == "not_sent", "not_sent_reason"] = c.loc[c.status == "not_sent", "not_sent_reason"].fillna(
        "Not sent: a better action for this physician")
    sent = c.status == "sent"
    c.loc[sent, "rank"] = c[sent].groupby(c.loc[sent, "resource"].astype(str)).final_return.rank(ascending=False, method="first")
    return c


def swaps_by_owner(c: pd.DataFrame) -> dict:
    """How many swaps each rep (or market, for marketing email) used this week."""
    s = c[(c.status == "sent") & c.reallocated]
    return s.resource.map(lambda k: k[1]).value_counts().to_dict()
