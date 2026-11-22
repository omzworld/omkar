"""The baseline cycle plan: segmentation, last year's touches, the recommended allocation and the weekly schedule.

Once per planning cycle (a quarter, `planning.cycle_weeks` in return_assumptions.yaml):
1. Segment every physician on three scores: potential (specialty, brick potential, practice size), adoption
   (journey stage) and responsiveness (their own response rate over the last 12 months, shrunk towards their
   market's average). Segment = potential band x adoption band. A physician only changes potential band when the
   evidence is clear (a margin past the boundary), so segments stay stable from one cycle to the next.
2. Take last year's touches per physician and channel (one quarter's worth) as the starting point.
3. Recommend the touches per segment: same total per channel and market as last year (same budget), shifted
   towards segments where one more touch is worth most, each segment within +/-20% of last year.
4. Spread each segment's touches over its physicians (last year's pattern blended with value), with a floor for
   high-potential physicians, then apply the reps' adjustments from the CRM.
5. Schedule each physician's touches evenly through the cycle. Each week the due touches are the reps' plan;
   the engine may move part of them (nba.reallocate). A postponed touch stays due later in the same cycle.
"""
from __future__ import annotations

import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from nba import data, features, spec
from nba.segments import potential

ADOPTION = {"curiosity": "early", "consideration": "early", "experience": "building", "loyalty": "established",
            "advocacy": "established"}
STAGE_N = {"curiosity": 0, "consideration": 1, "experience": 2, "loyalty": 3, "advocacy": 4}
TIER_BAND = {"A": "high", "B": "medium", "C": "low"}
BANDS = ["low", "medium", "high"]
HYSTERESIS = 5.0           # points past a band boundary before a physician changes potential band
SHRINK = 10                # touches' worth of the market average in each physician's response rate
MAX_PER_CYCLE = 13         # at most one touch a week per channel
LIST_CHANNELS = {"marketing_email", "rep_email"}   # volume follows the consented list, not a fixed count
LABEL = {"rep_visit": "visit", "remote_call": "remote call", "rep_email": "rep email", "marketing_email": "marketing email"}

LAST_YEAR = """
with calls as (
    select c.account_id, case when c.call_type = 'remote' then 'remote_call' else 'rep_visit' end as channel,
           count(*) as touches, count(*) filter (where c.next_step <> 'none') as responses
    from call2_vod c join user_vod u on u.id = c.user_id
    where c.status = 'submitted' and u.role = 'rep' and c.call_date >= $start and c.call_date < $end group by all),
rep_e as (
    select s.account_id, 'rep_email' as channel, count(*) as touches,
           count(*) filter (where exists (select 1 from email_activity_vod a
                                          where a.sent_email_id = s.id and a.event_type = 'open')) as responses
    from sent_email_vod s where s.status = 'sent' and s.email_sent_date >= $start and s.email_sent_date < $end
    group by all),
mkt as (
    select account_id, 'marketing_email' as channel, count(*) as touches, count(*) filter (where opened) as responses
    from agency_email where sent_datetime >= $start and sent_datetime < $end group by all)
select * from calls union all select * from rep_e union all select * from mkt
"""


def cfg() -> dict:
    return spec.assumptions()["planning"]


def cycle_of(week: int) -> int:
    return (week - 1) // cfg()["cycle_weeks"] + 1


def week_in_cycle(week: int) -> int:
    return (week - 1) % cfg()["cycle_weeks"] + 1


def cycle_start(cycle: int) -> pd.Timestamp:
    return features.as_of((cycle - 1) * cfg()["cycle_weeks"] + 1)


def last_year(as_of: pd.Timestamp, data_dir=None, weeks: int = 52) -> pd.DataFrame:
    """Touches and responses per physician and channel in the `weeks` before `as_of` (default: last year)."""
    con = data.connect(data_dir)
    return con.execute(LAST_YEAR, {"start": (as_of - pd.Timedelta(weeks=weeks)).date(), "end": as_of.date()}).df()


# ------------------------------------------------------------------------------------------- segmentation

def _nth(x: float) -> str:
    n = int(round(x))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _cuts() -> tuple[float, float]:
    """Band boundaries on the 0-100 potential score, using the same shares as today's tiers (A, B, C), so a
    physician who changes band does so because their potential reads differently, not because the cut moved."""
    t = spec.design()["tiers"]
    return 100 * (1 - t["A"] - t["B"]), 100 * (1 - t["A"])


def _band(score: pd.Series, current: pd.Series) -> pd.Series:
    """Potential band from the score, moving away from the current band only past a margin."""
    low_med, med_high = _cuts()
    raw = pd.cut(score, [-1, low_med, med_high, 101], labels=BANDS).astype(str)
    lo = {"low": -1, "medium": low_med, "high": med_high}
    hi = {"low": low_med, "medium": med_high, "high": 101}
    up = raw.map(BANDS.index) > current.map(BANDS.index)
    clear_up = score >= raw.map(lo) + HYSTERESIS
    clear_down = score <= raw.map(hi) - HYSTERESIS
    keep = (up & ~clear_up) | (~up & (raw != current) & ~clear_down)
    return raw.where(~keep, current)


def segment(t: pd.DataFrame, hist: pd.DataFrame, cycle: int, start: pd.Timestamp,
            previous: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per active physician: three scores, the segment, and whether (and why) they moved."""
    t = t[(t.account_type == "hcp") & (t.hcp_status.fillna("active") == "active")].copy()
    pot = potential(t)
    pct = lambda s: s.groupby(t.market).rank(pct=True) * 100                    # noqa: E731
    t["potential_score"] = pct(pot).round(1)
    t["adoption_score"] = (t.stage.map(STAGE_N).fillna(1) / 4 * 100).round(1)
    h = hist.groupby("account_id")[["touches", "responses"]].sum()
    h = h.join(t.set_index("hcp_id").market, how="right").fillna({"touches": 0, "responses": 0})
    m_rate = h.groupby("market").responses.sum() / h.groupby("market").touches.sum().clip(lower=1)
    rate = (h.responses + SHRINK * h.market.map(m_rate)) / (h.touches + SHRINK)
    t["responsiveness_score"] = (rate.reindex(t.hcp_id).groupby(t.market.to_numpy()).rank(pct=True) * 100).round(1).to_numpy()
    # Best channel: the highest shrunk response rate among channels with at least 3 touches last year.
    ch = hist.merge(t[["hcp_id", "market"]], left_on="account_id", right_on="hcp_id")
    cm = ch.groupby(["market", "channel"]).responses.sum() / ch.groupby(["market", "channel"]).touches.sum().clip(lower=1)
    prior = np.array([cm.get((m, c), 0.1) for m, c in zip(ch.market, ch.channel)])
    ch["rate"] = (ch.responses + SHRINK * prior) / (ch.touches + SHRINK)
    best = ch[ch.touches >= 3].sort_values(["rate", "channel"], ascending=[False, True]).drop_duplicates("account_id")
    default = pd.Series(np.where(t.tier.isin(["A", "B"]), "rep_visit", "marketing_email"), index=t.index)
    t["best_channel"] = t.hcp_id.map(best.set_index("account_id").channel).fillna(default)
    current = t.tier.map(TIER_BAND)
    if previous is not None and len(previous):
        current = t.hcp_id.map(previous.set_index("account_id").potential_band).fillna(current)
    t["potential_band"] = _band(t.potential_score, current)
    t["adoption_band"] = t.stage.map(ADOPTION).fillna("early")
    t["segment"] = t.potential_band.str.capitalize() + " potential · " + t.adoption_band
    t["moved"] = t.potential_band != current
    # Why: the component of potential that most explains the move, as a percentile within the market.
    size = np.log1p(t.practice_size.astype(float).fillna(1))
    drivers = {"brick potential": pct(t.brick_potential_index.astype(float).fillna(100)),
               "practice size": pct(size), "specialty weighting": pct(pot / pot.groupby(t.market).transform("mean"))}
    d = pd.DataFrame(drivers)
    up = t.potential_band.map(BANDS.index) > current.map(BANDS.index)
    top, bottom = d.idxmax(axis=1), d.idxmin(axis=1)
    t["move_reason"] = np.where(~t.moved, None, np.where(
        up, [f"{k.capitalize()} is high for the market ({_nth(d.at[i, k])} percentile)" for i, k in top.items()],
        [f"{k.capitalize()} is low for the market ({_nth(d.at[i, k])} percentile)" for i, k in bottom.items()]))
    return pd.DataFrame({
        "account_id": t.hcp_id, "cycle": cycle, "cycle_start": start.date(), "market": t.market,
        "potential_score": t.potential_score, "adoption_score": t.adoption_score,
        "responsiveness_score": t.responsiveness_score, "potential_band": t.potential_band,
        "adoption_band": t.adoption_band, "segment": t.segment, "current_tier": t.tier,
        "best_channel": t.best_channel, "moved": t.moved, "move_reason": t.move_reason}).reset_index(drop=True)


# ------------------------------------------------------------------------------------------- allocation

def _equalise(ly: pd.Series, n_phys: pd.Series, val: pd.Series, cap: float, decay: float) -> pd.Series:
    """Move touches between segments, keeping the total, towards equal value of the next touch."""
    n = ly.astype(float).copy()
    lo, hi, total = ly * (1 - cap), ly * (1 + cap), ly.sum()
    if total <= 0 or len(n) < 2:
        return n
    step = total * 0.0025
    for _ in range(800):
        marg = val * decay ** (n / n_phys.clip(lower=1))
        can_give, can_take = (n - step) >= lo, (n + step) <= hi
        if not can_give.any() or not can_take.any():
            break
        donor, taker = marg[can_give].idxmin(), marg[can_take].idxmax()
        if donor == taker or marg[taker] <= marg[donor] * 1.001:
            break
        n[donor] -= step
        n[taker] += step
    return n


def _allowed(f: pd.DataFrame, channel: str) -> pd.Series:
    """Whether a channel may be planned for each physician: email needs consent (double opt-in in Germany), remote
    calls need remote consent, promotional visits in the UK go to prescribers only, medical-only contacts and anyone
    who opted out or has a no-promotion flag get none. The plan's touches go to physicians they are allowed for."""
    flag = lambda col: f[col].fillna(False).astype(bool)                                  # noqa: E731
    # Medical-only contacts get no commercial touch (R014); no one who opted out or has a no-promotion flag.
    base = ~flag("opt_out_any") & ~flag("no_promo_flag") & (f.hcp_role != "medical_only_contact")
    double_ok = (f.market != "DE") | flag("consent_double_opt_in")                      # Germany: double opt-in
    if channel in ("marketing_email", "rep_email"):
        return base & flag("consent_email") & double_ok
    if channel == "remote_call":
        return base & flag("consent_remote") & ~((f.market == "UK") & ~flag("hcp_prescriber"))
    # Promotional visits only to prescribers in the UK (R011).
    return base & ~((f.market == "UK") & ~flag("hcp_prescriber"))


def _integerise(target: pd.Series, total: int) -> pd.Series:
    base = np.floor(target).astype(int)
    short = int(total - base.sum())
    if short > 0:
        order = (target - base).sort_values(ascending=False, kind="stable").index[:short]
        base[order] += 1
    return base


def allocate(seg: pd.DataFrame, hist: pd.DataFrame, t: pd.DataFrame, inputs: pd.DataFrame,
             cycle: int, start: pd.Timestamp, data_dir=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The recommended touches per physician and channel for the cycle, and the segment budget behind them.
    Last year's touches (one quarter's worth) are the starting point; each market, channel and pilot arm keeps
    its total, and the split across segments moves towards value within the change cap."""
    from nba.optimiser import value
    c = cfg()
    cost = spec.assumptions()["touch_cost"]
    q = c["cycle_weeks"] / 52
    feats = t.set_index("hcp_id")
    hv = feats.loc[seg.account_id].reset_index().assign(trigger_type="opportunity")
    seg = seg.assign(value=value(hv).to_numpy())
    terr = feats.territory_id
    rows, budget = [], []
    hist = hist[hist.channel.isin(c["channels"])]
    m_rate = hist.merge(seg[["account_id", "market"]], on="account_id").groupby(["market", "channel"])[["responses", "touches"]].sum()
    seg = seg.assign(arm=seg.account_id.map(feats.pilot_arm).fillna("none").to_numpy())
    # Each pilot arm keeps its own total (the plan only runs in test territories, so test must not lend budget
    # to control physicians or borrow from them); in a roll-out there is a single arm.
    groups = [(m, ch, a) for (m, ch) in m_rate.index for a in sorted(seg.arm.unique())]
    for market, channel, arm in groups:
        s = seg[(seg.market == market) & (seg.arm == arm)].copy()
        if s.empty:
            continue
        h = hist[hist.channel == channel].set_index("account_id")
        s["ly"] = s.account_id.map(h.touches).fillna(0) * q
        mr = m_rate.loc[(market, channel)]
        rate = (s.account_id.map(h.responses).fillna(0) + SHRINK * mr.responses / max(mr.touches, 1)) \
            / (s.account_id.map(h.touches).fillna(0) + SHRINK)
        s["v"] = s.value * rate
        s["ok"] = _allowed(feats.loc[s.account_id], channel).to_numpy()
        if channel in LIST_CHANNELS:
            # Email programmes go to everyone on the consented list at last year's frequency, so the volume follows
            # the list: scale by today's eligible physicians against those emailed last year (capped at +50%).
            emailed = (s.ly > 0).sum()
            if emailed:
                s["ly"] = s.ly * min(max(s.ok.sum() / emailed, 1.0), 1.5)
        g = s.groupby("segment").agg(ly=("ly", "sum"), phys=("account_id", "size"), v=("v", "mean"))
        rec = _equalise(g.ly, g.phys, g.v, c["segment_change_cap"], c["frequency_decay"])
        for name, grp in s.groupby("segment"):
            total = int(round(rec[name]))
            ly_ok, v_ok = grp.ly.where(grp.ok, 0), grp.v.where(grp.ok, 0)   # only physicians the channel is allowed for
            share_ly = ly_ok / ly_ok.sum() if ly_ok.sum() > 0 else grp.ok / max(grp.ok.sum(), 1)
            share_v = v_ok / v_ok.sum() if v_ok.sum() > 0 else share_ly
            target = total * ((1 - c["value_weight"]) * share_ly + c["value_weight"] * share_v)
            if channel == "rep_visit":
                floor = (grp.potential_band == "high") & (grp.ly > 0)
                target = target.where(~floor, target.clip(lower=c["floor_high_potential_visits"]))
            target = target.clip(upper=MAX_PER_CYCLE)
            alloc = _integerise(target * total / max(target.sum(), 1e-9), total).clip(upper=MAX_PER_CYCLE)
            rows.append(pd.DataFrame({"account_id": grp.account_id.to_numpy(), "segment": name, "channel": channel,
                                      "last_year_touches": grp.ly.round(2).to_numpy(), "recommended_touches": alloc.to_numpy()}))
            budget.append({"cycle": cycle, "cycle_start": start.date(), "market": market, "segment": name,
                           "channel": channel, "physicians": len(grp), "last_year_touches": round(g.ly[name], 1),
                           "recommended_touches": int(alloc.sum()),
                           "change_pct": round(100 * (alloc.sum() / g.ly[name] - 1), 1) if g.ly[name] > 0 else None,
                           "cost_last_year_eur": round(g.ly[name] * cost[channel], 0),
                           "cost_recommended_eur": round(alloc.sum() * cost[channel], 0)})
    plan = pd.concat(rows, ignore_index=True)
    # One budget row per segment and channel (the arms were balanced separately above).
    b = pd.DataFrame(budget).groupby(["cycle", "cycle_start", "market", "segment", "channel"], as_index=False)[
        ["physicians", "last_year_touches", "recommended_touches", "cost_last_year_eur", "cost_recommended_eur"]].sum()
    b["change_pct"] = (100 * (b.recommended_touches / b.last_year_touches.where(b.last_year_touches > 0) - 1)).round(1)
    budget = b[["cycle", "cycle_start", "market", "segment", "channel", "physicians", "last_year_touches",
                "recommended_touches", "change_pct", "cost_last_year_eur", "cost_recommended_eur"]]
    plan["final_touches"], plan["rep_adjusted"] = plan.recommended_touches, False
    plan = _apply_inputs(plan, inputs, start, c)
    plan["user_id"] = np.where(plan.channel == "marketing_email", None,
                               plan.account_id.map(terr).map(
                                   data.read_table("territory_vod", data_dir).set_index("id").rep_user_id))
    plan = plan[(plan.last_year_touches > 0) | (plan.final_touches > 0)]
    plan.insert(1, "cycle", cycle)
    plan.insert(2, "cycle_start", start.date())
    cols = ["account_id", "cycle", "cycle_start", "user_id", "segment", "channel", "last_year_touches",
            "recommended_touches", "rep_adjusted", "final_touches"]
    return plan[cols].reset_index(drop=True), budget.round({"last_year_touches": 1})


def _apply_inputs(plan: pd.DataFrame, inputs: pd.DataFrame, start: pd.Timestamp, c: dict) -> pd.DataFrame:
    """The reps' adjustments for this cycle, as entered in the CRM."""
    mine = inputs[pd.to_datetime(inputs.cycle_start) == start]
    p = plan.set_index(["account_id", "channel"])
    for _, r in mine.iterrows():
        a = r.account_id
        if a not in p.index.get_level_values(0):
            continue
        get = lambda ch: int(p.at[(a, ch), "final_touches"]) if (a, ch) in p.index else 0   # noqa: E731

        def put(ch, n):
            if (a, ch) not in p.index:
                p.loc[(a, ch), ["segment", "last_year_touches", "recommended_touches"]] = \
                    [p.loc[a].segment.iloc[0], 0.0, 0]
            p.at[(a, ch), "final_touches"] = int(n)
            p.at[(a, ch), "rep_adjusted"] = True
        if r.adjustment == "must_see":
            put("rep_visit", max(get("rep_visit"), c["must_see_visits"]))
        elif r.adjustment == "no_access":
            moved = get("rep_visit") + get("remote_call")
            put("rep_visit", 0), put("remote_call", 0), put("rep_email", min(get("rep_email") + moved, MAX_PER_CYCLE))
        elif r.adjustment == "more_digital":
            half = get("rep_visit") // 2
            put("rep_visit", get("rep_visit") - half), put("rep_email", min(get("rep_email") + half, MAX_PER_CYCLE))
        elif r.adjustment == "left_practice":
            for ch in c["channels"]:
                if (a, ch) in p.index:
                    put(ch, 0)
    return p.reset_index().fillna({"rep_adjusted": False})


# ------------------------------------------------------------------------------------------- the cycle and the week

def _state_path(data_dir=None) -> Path:
    return (Path(data_dir) if data_dir else spec.data_dir()) / "runs" / "plan_state.parquet"


def build_cycle(cycle: int, data_dir=None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Segmentation, call plan and segment budget for a cycle, from the data as it stands at the cycle's start."""
    week = (cycle - 1) * cfg()["cycle_weeks"] + 1
    start = cycle_start(cycle)
    try:
        t = features.load_snapshot(week, data_dir).table
    except FileNotFoundError:
        t = features.build(week, data_dir, save=False).table
    hist = last_year(start, data_dir)
    prev = data.read_table("hcp_segment", data_dir)
    prev = prev[prev.cycle == cycle - 1] if len(prev) else None
    seg = segment(t, hist, cycle, start, prev)
    if cfg().get("potential_source") == "zs":              # the brand's own (ZS) potential, where it is recorded
        zs = data.read_table("account_profile_vod", data_dir).set_index("account_id").zs_potential
        band = seg.account_id.map(zs)
        seg["moved"] = band.notna() & (band != seg.current_tier.map(TIER_BAND))
        seg["potential_band"] = band.fillna(seg.potential_band)
        seg["segment"] = seg.potential_band.str.capitalize() + " potential · " + seg.adoption_band
        seg["move_reason"] = np.where(seg.moved, "ZS potential classification", None)
    plan, budget = allocate(seg, hist, t, data.read_table("rep_plan_input", data_dir), cycle, start, data_dir)
    return seg, plan, budget


def start_cycle(cycle: int, data_dir=None, save: bool = True) -> pd.DataFrame:
    """Segment, allocate and write the plan for a cycle; return the schedule state (nothing delivered yet)."""
    seg, plan, budget = build_cycle(cycle, data_dir)
    if save:
        for name, df in [("hcp_segment", seg), ("call_plan", plan), ("segment_budget", budget)]:
            old = data.read_table(name, data_dir)
            old = old[old.cycle != cycle] if len(old) else old
            data.write_table(name, pd.concat([old.astype(object), df.astype(object)], ignore_index=True)
                             if len(old) else df, data_dir)
    state = plan[["account_id", "channel", "cycle", "user_id", "segment"]].assign(
        planned=plan.final_touches.to_numpy(), delivered=0, pending=0, swaps_out=0, first_week=1,
        offset=[zlib.crc32(f"{a}|{ch}".encode()) % 1000 / 1000 for a, ch in zip(plan.account_id, plan.channel)])
    if save:
        _state_path(data_dir).parent.mkdir(parents=True, exist_ok=True)
        state.to_parquet(_state_path(data_dir), index=False)
    return state


def state_for(week: int, data_dir=None) -> pd.DataFrame:
    """The schedule as it stood at the start of `week` (for the runner and for previews)."""
    root = Path(data_dir) if data_dir else spec.data_dir()
    snap = root / "runs" / f"week_{week:02d}" / "plan_state_before.parquet"
    if snap.exists():
        return pd.read_parquet(snap)
    if week_in_cycle(week) == 1 or not _state_path(data_dir).exists():
        return start_cycle(cycle_of(week), data_dir, save=False)
    return pd.read_parquet(_state_path(data_dir))


def top_up_lists(state: pd.DataFrame, feats, week: int) -> pd.DataFrame:
    """Email programmes follow the consented list: a physician who becomes eligible for email during the cycle
    joins the plan at their segment's email frequency, for the weeks that are left."""
    t = feats.table.set_index("hcp_id")
    k, n_weeks = week_in_cycle(week), cfg()["cycle_weeks"]
    seg_of = state.drop_duplicates("account_id").set_index("account_id").segment
    add = []
    for ch in LIST_CHANNELS:
        have = set(state.account_id[(state.channel == ch) & (state.planned > 0)])
        cand = [a for a in seg_of.index if a in t.index and a not in have]
        if not cand:
            continue
        ok = _allowed(t.loc[cand], ch)
        new = [a for a, o in zip(cand, ok) if o]
        if not new:
            continue
        rows = state[(state.channel == ch) & (state.planned > 0)]
        freq = rows.groupby("segment").planned.mean()                     # planned per physician per cycle
        for a in new:
            n = int(round(freq.get(seg_of[a], 0) * (n_weeks - k + 1) / n_weeks))
            if n > 0:
                user = None if ch == "marketing_email" else state.user_id[state.account_id == a].dropna().iloc[0] \
                    if state.user_id[state.account_id == a].notna().any() else None
                add.append({"account_id": a, "channel": ch, "cycle": cycle_of(week), "user_id": user,
                            "segment": seg_of[a], "planned": n, "delivered": 0, "pending": 0, "swaps_out": 0,
                            "first_week": k,
                            "offset": zlib.crc32(f"{a}|{ch}".encode()) % 1000 / 1000})
    if not add:
        return state
    rest = state[~state.set_index(["account_id", "channel"]).index.isin([(r["account_id"], r["channel"]) for r in add])]
    return pd.concat([rest, pd.DataFrame(add)], ignore_index=True)


def due(state: pd.DataFrame, week: int) -> pd.DataFrame:
    """The touches due this week: the next one in each physician's even schedule, plus any postponed earlier."""
    k, n_weeks = week_in_cycle(week), cfg()["cycle_weeks"]
    n, off = state.planned.astype(float), state.offset.astype(float)
    # Spread each physician's touches evenly over the weeks from when they joined the plan (week 1 for most).
    first = state.get("first_week", pd.Series(1, index=state.index)).astype(float)
    span = (n_weeks - first + 1).clip(lower=1)
    pos = (k - first + 1).clip(lower=0)
    now = (np.floor(n * pos / span + off) - np.floor(n * (pos - 1).clip(lower=0) / span + off)).astype(int)
    now = now.where(pos > 0, 0)
    s = state.assign(due_now=now.to_numpy())
    return s[(s.due_now > 0) | (s.pending > 0)].reset_index(drop=True)


def plan_triggers(d: pd.DataFrame, feats, week: int) -> pd.DataFrame:
    """The due touches as triggers (origin 'plan'), so they go through the same constraints and scoring."""
    from nba.rules.engine import TRIGGER_COLUMNS
    t = feats.table.set_index("hcp_id")
    d = d[d.account_id.isin(t.index)]
    reason = [f"Planned {LABEL[ch]} ({seg.lower()}): touch {dl + 1} of {pl} this quarter"
              + (" (rescheduled)" if p > 0 and now == 0 else "")
              for ch, seg, dl, pl, p, now in zip(d.channel, d.segment, d.delivered, d.planned, d.pending, d.due_now)]
    out = pd.DataFrame({
        "trigger_id": [f"W{week:02d}-PLAN-{ch}-{a}" for a, ch in zip(d.account_id, d.channel)], "run_week": feats.as_of,
        "hcp_id": d.account_id.to_numpy(), "market": d.account_id.map(t.market).to_numpy(),
        "territory_id": d.account_id.map(t.territory_id).to_numpy(), "account_type": "hcp",
        "brand": d.account_id.map(t.brand).to_numpy(), "rule_id": "PLAN", "rule_ids": "PLAN", "family": "baseline_plan",
        "trigger_type": "opportunity", "channel": d.channel.to_numpy(), "content_theme": "next_theme",
        "timing": "this_week", "priority": 50, "reason": reason, "origin": "plan"})
    return out[TRIGGER_COLUMNS]


def record(state: pd.DataFrame, d: pd.DataFrame, delivered: set, week: int, swapped_out: set = frozenset(),
           dropped: set = frozenset()) -> pd.DataFrame:
    """After the week: count what was delivered; anything due and not delivered stays pending in the cycle.
    `swapped_out` are the planned touches the engine moved to another physician (they count against the rep's
    reallocation cap for the cycle)."""
    s = state.set_index(["account_id", "channel"])
    for key in swapped_out:
        if key in s.index:
            s.at[key, "swaps_out"] += 1
    for a, ch, now in zip(d.account_id, d.channel, d.due_now):
        x = 1 if (a, ch) in delivered else 0
        # A moved touch was used by another physician; a touch blocked for good is dropped, not retried weekly.
        used = 1 if (x or (a, ch) in swapped_out or (a, ch) in dropped) else 0
        s.at[(a, ch), "delivered"] += x
        s.at[(a, ch), "pending"] = max(int(s.at[(a, ch), "pending"]) + int(now) - used, 0)
    if week_in_cycle(week) == cfg()["cycle_weeks"]:
        s["pending"] = 0                                # a new cycle starts with a new plan
    return s.reset_index()
