"""Feedback simulator: what happens in the field after the engine's suggestions go out.

This module stands in for the real world during the synthetic pilot. Like nba.synth it may read the hidden
behaviour clusters; the engine never does. Each pilot week:
- control territories (and any vacant one) carry on with today's plan, exactly as in the 24-month history;
- in test territories, reps accept or dismiss each suggestion (trust grows a little every week because the
  reason is shown); accepted touches, agency emails and webinar invitations are executed and physicians respond
  according to their hidden behaviour, the asset's journey stage and how recently they saw the same theme;
- journey stages move, consent is captured at some visits and lost at some unsubscribes;
- every outcome is written to the same Veeva-shaped tables, so next week's features see it;
- when a month or quarter completes, brick sales and endoscopy procedure volumes for it are added.
Randomness is seeded by (seed, week), so a replay reproduces every number.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from nba import data, spec
from nba.features import as_of
from nba.synth.behaviour import ANY_STAGE, STAGES
from nba.synth.history import CLICK_GIVEN_OPEN, UNSUBSCRIBE_PER_EMAIL
from nba.synth.sales import OTC_BASE_UNITS, PRICE, XIFAXAN_UNIT_SCALE

REP_DELIVERED = {"rep_visit", "remote_call", "rep_email", "kam_visit", "kam_brief"}
EMPTY = {"call2_vod": ["account_id", "user_id", "call_date", "call_type", "status", "product", "key_message_ids",
                       "next_step", "suggestion_id"],
         "sent_email_vod": ["account_id", "user_id", "email_sent_date", "approved_document_id", "status",
                            "suggestion_id", "_resp", "_click", "_unsub"],
         "agency_email": ["campaign_id", "account_id", "market", "approved_document_id", "sent_datetime", "opened",
                          "clicked", "unsubscribed"],
         "agency_media": ["account_id", "market", "week", "impressions", "clicks", "portal_visits",
                          "portal_content_viewed"],
         "event_attendee_vod": ["event_id", "account_id", "event_type", "event_date", "registered", "attended"]}
CONSENT_AT_VISIT = 0.05            # chance a rep visit captures email consent from a physician without it
CONSENT_AT_INTRO_VISIT = 0.15      # higher when the visit is an introduction aimed at capturing consent


def _path(data_dir) -> Path:
    return (Path(data_dir) if data_dir else spec.data_dir()) / data.HIDDEN / "simulator.pkl"


def load(data_dir=None):
    with open(_path(data_dir), "rb") as f:
        return pickle.load(f)


def save(sim, data_dir=None):
    sim.clear_rows()
    with open(_path(data_dir), "wb") as f:
        pickle.dump(sim, f)


def _arms(sim, data_dir) -> tuple[np.ndarray, list]:
    terr = data.read_table("territory_vod", data_dir).set_index("id").pilot_arm
    hcp_arm = sim.h.territory_id.map(terr).to_numpy()
    hcos = sim.world["hcos"]
    brick_terr = sim.world["bricks"].set_index("brick_id").territory_id
    unit_arm = hcos.brick_id.map(brick_terr).map(terr)
    return hcp_arm, hcos.hco_id[unit_arm != "test"].tolist()


# --------------------------------------------------------------------------------------- reps and suggestions

RECENT_VISIT_DAYS = 30          # a rep is less keen on a physician they saw in the last month ...
RECENT_VISIT_ACCEPT_FACTOR = 0.55
RECENT_VISIT_SEEN_RECENTLY = 0.7  # ... and then usually says "seen recently"
LOW_TIER_ACCEPT_FACTOR = 0.6     # reps push back on suggestions for low-potential (tier C) accounts ...
LOW_TIER_NOT_A_PRIORITY = 0.7    # ... and then usually say "not a priority"


def rep_decisions(sim, suggestions: pd.DataFrame, week: int, rng, sent: pd.DataFrame | None = None) -> pd.DataFrame:
    """Each rep accepts or dismisses each suggestion."""
    if suggestions.empty:
        return suggestions
    fs = spec.design()["feedback_simulation"]
    cluster = suggestions.account_id.map(sim.h.set_index("id").cluster)
    base = np.where((cluster == "rep_led") & (suggestions.suggested_channel == "rep_visit"),
                    fs["rep_accept_probability"]["rep_led_cluster_rep_visit"], fs["rep_accept_probability"]["other"])
    p = np.clip(base + fs["accept_probability_increase_per_week_with_reason"] * (week - 1), 0, 0.95)
    recent = np.zeros(len(suggestions), bool)
    if sent is not None and "days_since_rep_visit" in sent:
        days = suggestions.account_id.map(sent.drop_duplicates("hcp_id").set_index("hcp_id").days_since_rep_visit)
        recent = (days < RECENT_VISIT_DAYS).fillna(False).to_numpy()
        p = np.where(recent, p * RECENT_VISIT_ACCEPT_FACTOR, p)
    low = np.zeros(len(suggestions), bool)
    if sent is not None and "tier" in sent:
        low = (suggestions.account_id.map(sent.drop_duplicates("hcp_id").set_index("hcp_id").tier) == "C").to_numpy()
        p = np.where(low, p * LOW_TIER_ACCEPT_FACTOR, p)
    accepted = rng.random(len(suggestions)) < p
    reasons, probs = zip(*fs["dismiss_reasons"].items())
    reason = rng.choice(reasons, len(suggestions), p=np.array(probs) / sum(probs))
    reason = np.where(recent & (rng.random(len(suggestions)) < RECENT_VISIT_SEEN_RECENTLY), "seen_recently", reason)
    reason = np.where(low & (rng.random(len(suggestions)) < LOW_TIER_NOT_A_PRIORITY), "not_a_priority", reason)
    s = suggestions.copy()
    s["status"] = np.where(accepted, "accepted", "dismissed")
    s["dismiss_reason"] = np.where(accepted, None, reason)
    return s


def _execute(sim, w, date, idx, channel, doc_ids, rng):
    """Touch physicians idx on a channel with the given assets; return who responded."""
    doc_pos = pd.Series(range(len(sim.docs)), index=sim.docs.document_id)
    pos = doc_ids.map(doc_pos)
    has_doc = pos.notna().to_numpy()
    p_idx = pos.fillna(0).astype(int).to_numpy()
    theme = np.where(has_doc, sim.doc_theme[p_idx], -1)
    doc_stage = np.where(has_doc, sim.doc_stage[p_idx], ANY_STAGE)
    repeated = np.where(has_doc, sim.last_theme_week[idx, np.maximum(theme, 0)] >= w - 4, False)
    resp = rng.random(len(idx)) < sim.beh.response_prob(idx, channel, sim.stage[idx], doc_stage, repeated)
    sim.last_touch_week[idx] = w
    sim.last_theme_week[idx[has_doc], theme[has_doc]] = w
    on_seq = has_doc & (doc_stage == sim.stage[idx])
    sim.responded[idx[resp & on_seq]] = True
    sim.access_landed[idx[resp & (theme == sim.access)]] = True
    return resp


def execute_engine(sim, w, date, sent: pd.DataFrame, suggestions: pd.DataFrame, week: int, rng) -> None:
    """Carry out what the engine sent in test territories: accepted rep suggestions, agency emails, webinars."""
    pos = pd.Series(range(sim.n), index=sim.h.id)
    acc = suggestions[suggestions.status == "accepted"].set_index("account_id")
    rows = sim.rows
    for channel in ["rep_visit", "remote_call", "rep_email", "kam_visit", "kam_brief", "marketing_email", "webinar"]:
        s = sent[sent.final_channel == channel]
        if channel in REP_DELIVERED:
            s = s[s.hcp_id.isin(acc.index)]
        if s.empty:
            continue
        kam = channel in ("kam_visit", "kam_brief")
        is_hcp = s.hcp_id.isin(pos.index)
        office = s if kam else s[~is_hcp]            # organisations: a logged call, no physician response
        if len(office):
            docs = office.asset_id.astype(object).where(office.asset_id.notna(), None)
            rows["call2_vod"].append(pd.DataFrame({
                "account_id": office.hcp_id.to_numpy(),
                "user_id": (office.kam_user_id if kam else office.rep_user_id).to_numpy(),
                "call_date": date + pd.to_timedelta(rng.integers(0, 5, len(office)), unit="D"),
                "call_type": "face_to_face", "status": "submitted", "product": office.brand.to_numpy(),
                "key_message_ids": [f"{d}:KM1|{d}:KM2" if d else None for d in docs],
                "next_step": rng.choice(["none", "send_material", "follow_up_call"], len(office), p=[0.4, 0.3, 0.3]),
                "suggestion_id": office.hcp_id.map(acc.id).to_numpy() if channel in REP_DELIVERED else None}))
        s = s.iloc[0:0] if kam else s[is_hcp]
        if s.empty:
            continue
        sug_id = s.hcp_id.map(acc.id) if channel in REP_DELIVERED else pd.Series(None, index=s.index)
        days = date + pd.to_timedelta(rng.integers(0, 5, len(s)), unit="D")
        idx = s.hcp_id.map(pos).to_numpy()
        resp = _execute(sim, w, date, idx, channel, s.asset_id.astype(object), rng)
        docs = s.asset_id.astype(object).where(s.asset_id.notna(), None).to_numpy()
        if channel in ("rep_visit", "remote_call"):
            rows["call2_vod"].append(pd.DataFrame({
                "account_id": s.hcp_id.to_numpy(), "user_id": s.rep_user_id.to_numpy(), "call_date": days,
                "call_type": "remote" if channel == "remote_call" else "face_to_face", "status": "submitted",
                "product": s.brand.to_numpy(), "key_message_ids": [f"{d}:KM1|{d}:KM2" if d else None for d in docs],
                "next_step": np.where(resp, rng.choice(["send_material", "follow_up_call"], len(s)), "none"),
                "suggestion_id": sug_id.to_numpy()}))
        elif channel in ("rep_email", "marketing_email"):
            clicked = resp & (rng.random(len(s)) < CLICK_GIVEN_OPEN)
            unsub = rng.random(len(s)) < UNSUBSCRIBE_PER_EMAIL
            sim.email_active[idx[unsub]] = False
            sim.unsub_week[idx[unsub]] = w
            sent_at = days + pd.to_timedelta(rng.integers(7, 18, len(s)), unit="h")
            if channel == "rep_email":
                rows["sent_email_vod"].append(pd.DataFrame({
                    "account_id": s.hcp_id.to_numpy(), "user_id": s.rep_user_id.to_numpy(), "email_sent_date": sent_at,
                    "approved_document_id": docs, "status": "sent", "suggestion_id": sug_id.to_numpy(),
                    "_resp": resp, "_click": clicked, "_unsub": unsub}))
            else:
                rows["agency_email"].append(pd.DataFrame({
                    "campaign_id": [f"{m}-NBA{week:02d}" for m in s.market], "account_id": s.hcp_id.to_numpy(),
                    "market": s.market.to_numpy(), "approved_document_id": docs, "sent_datetime": sent_at,
                    "opened": resp, "clicked": clicked, "unsubscribed": unsub}))
        elif channel == "webinar":
            sim.ever_attended[idx[resp]] = True
            rows["event_attendee_vod"].append(pd.DataFrame({
                "event_id": [f"{m}-NBA-WEB-W{week:02d}" for m in s.market], "account_id": s.hcp_id.to_numpy(),
                "event_type": "webinar", "event_date": date + pd.Timedelta(days=3),
                "registered": resp | (rng.random(len(s)) < 0.12), "attended": resp}))


def capture_consent(sim, date, rng, intro_ids: set) -> list[str]:
    """Some rep visits win email consent from physicians who had not given it."""
    calls = pd.concat(sim.rows["call2_vod"] or [pd.DataFrame(columns=["account_id", "status", "call_type"])])
    visited = set(calls[(calls.status == "submitted") & (calls.call_type == "face_to_face")].account_id)
    pos = pd.Series(range(sim.n), index=sim.h.id)
    ids = [a for a in sorted(visited) if a in pos.index and not sim.email_active[pos[a]]]
    p = np.array([CONSENT_AT_INTRO_VISIT if a in intro_ids else CONSENT_AT_VISIT for a in ids])
    won = [a for a, hit in zip(ids, rng.random(len(ids)) < p) if hit]
    for a in won:
        sim.email_active[pos[a]] = True
        sim.email_since[pos[a]] = np.datetime64(date)
    return won


# --------------------------------------------------------------------------------------- tables

def _collect(sim, week) -> dict[str, pd.DataFrame]:
    for name, cols in EMPTY.items():     # an empty frame with the right columns, for tables with no rows this week
        if not sim.rows[name]:
            sim.rows[name].append(pd.DataFrame(columns=cols))
    out = sim._tables(prefix=f"-W{week:02d}-")
    for k in ["final_stage", "unsubscribed"]:
        out.pop(k, None)
    return {k: v for k, v in out.items() if len(v)}


def _append(name: str, new: pd.DataFrame, data_dir) -> None:
    old = data.read_table(name, data_dir)
    new = new.reindex(columns=old.columns)
    data.write_table(name, pd.concat([old.astype(object), new.astype(object)], ignore_index=True), data_dir)


def _update_consent(won: list[str], unsubscribed: list[str], date, data_dir) -> None:
    if not won and not unsubscribed:
        return
    c = data.read_table("consent", data_dir).astype(object)
    email = c.channel.isin(["marketing_email", "rep_email", "webinar"])
    gain = email & c.account_id.isin(won)
    c.loc[gain, "status"], c.loc[gain, "captured_date"], c.loc[gain, "source"] = "granted", date, "rep_capture"
    loss = email & c.account_id.isin(unsubscribed) & (c.status == "granted")
    c.loc[loss, "status"] = "withdrawn"
    data.write_table("consent", c, data_dir)


def _month_sales(sim, month: pd.Timestamp, rng, data_dir) -> pd.DataFrame:
    """Brick sales for a completed pilot month, continuing each brick's history."""
    cfg = spec.design()["brick_sales"]
    units_by_stage = np.array([cfg["units_per_hcp_month_by_stage"][s] for s in STAGES])
    season = {pd.Timestamp(f"2000-{m}-01").month: f for m, f in cfg["seasonality"].items()}
    prev_month = month - pd.offsets.MonthBegin(1)
    sales = data.read_table("iqvia_brick_sales", data_dir)
    prev = sales[pd.to_datetime(sales.month) == prev_month].set_index(["brick_id", "product"])
    b = sim.world["bricks"].set_index("brick_id")
    rows = []
    for product, scale in [("Movicol", 1.0), ("Xifaxan", XIFAXAN_UNIT_SCALE)]:
        mine = sim.h.brand.to_numpy() == product
        own = pd.Series(units_by_stage[sim.stage[mine]] * scale, index=sim.h.brick_id[mine]).groupby(level=0).sum()
        own = own.reindex(b.index, fill_value=0) + OTC_BASE_UNITS * scale * b.potential_index / 100
        own = own * rng.lognormal(0, cfg["noise_sd"], len(b)) * season.get(month.month, 1.0)
        p = prev.xs(product, level="product").reindex(b.index)
        total_prev = (p.units + p.competitor_units).fillna(own)
        total = total_prev / season.get(prev_month.month, 1.0) * season.get(month.month, 1.0) * 1.002 \
            * rng.lognormal(0, 0.04, len(b))
        comp = np.maximum(total - own, 0.15 * total)
        price = b.market.map(PRICE[product])
        rows.append(pd.DataFrame({"brick_id": b.index, "market": b.market.to_numpy(), "product": product,
                                  "month": month, "units": own.round(1).to_numpy(),
                                  "value": (own * price).round(2).to_numpy(), "competitor_units": comp.round(1).to_numpy()}))
    return pd.concat(rows, ignore_index=True)


def _quarter_procedures(sim, quarter: pd.Period, rng, data_dir) -> pd.DataFrame:
    """Endoscopy unit procedures for a completed pilot quarter, continuing each unit's history."""
    pv = data.read_table("procedure_volume", data_dir)
    last = pv.sort_values("quarter").groupby("hco_id").tail(1).set_index("hco_id")
    stage = pd.Series(sim.stage, index=sim.h.id)
    unit_stage = sim.h.assign(s=sim.h.id.map(stage)).groupby("primary_parent_id").s.mean()
    prev_stage = sim.unit_stage_prev if hasattr(sim, "unit_stage_prev") else unit_stage
    change = (unit_stage - prev_stage).reindex(last.index).fillna(0)
    sim.unit_stage_prev = unit_stage
    vol = last.colonoscopies * (1 + rng.normal(0.01, 0.03, len(last))) * rng.lognormal(0, 0.05, len(last))
    share = np.clip(last.norgine_prep_share + 0.04 * change + rng.normal(0, 0.02, len(last)), 0.02, 0.95)
    inadequate = np.clip(0.10 + 0.08 * (1 - share) + rng.normal(0, 0.01, len(last)), 0.03, 0.4)
    return pd.DataFrame({"hco_id": last.index, "quarter": f"{quarter.year}-Q{quarter.quarter}",
                         "colonoscopies": vol.round().astype(int).to_numpy(), "norgine_prep_share": share.round(3).to_numpy(),
                         "inadequate_prep_rate": inadequate.round(3).to_numpy()})


# --------------------------------------------------------------------------------------- one week

def simulate_week(week: int, sent: pd.DataFrame, suggestions: pd.DataFrame, data_dir=None) -> dict:
    """Simulate pilot week `week` given what the engine sent; write everything; return the outcome counts."""
    sim = load(data_dir)
    rng = np.random.default_rng([spec.design()["seed"], week])
    sim.rng = rng
    sim.clear_rows()
    w, date = sim.n_weeks + week, as_of(week)
    hcp_arm, control_units = _arms(sim, data_dir)
    sim.plan, sim.unit_plan = hcp_arm != "test", control_units

    sim.begin_week()
    sim.plan_week(w, date)                                   # control territories: today's plan
    suggestions = rep_decisions(sim, suggestions, week, rng, sent)
    execute_engine(sim, w, date, sent, suggestions, week, rng)
    intro = set(sent[(sent.final_channel == "rep_visit") & (sent.content_theme == "introduction")].hcp_id)
    won = capture_consent(sim, date, rng, intro)
    unsub_now = sim.h.id.to_numpy()[sim.unsub_week == w].tolist()
    sim.end_week(w, date)

    tables = _collect(sim, week)
    for name, df in tables.items():
        _append(name, df, data_dir)
    if not suggestions.empty:
        _append("suggestion_vod", suggestions, data_dir)
    _update_consent(won, unsub_now, date, data_dir)

    next_day = date + pd.Timedelta(days=7)
    if next_day.month != date.month:                         # a month completed this week
        _append("iqvia_brick_sales", _month_sales(sim, date.to_period("M").to_timestamp(), rng, data_dir), data_dir)
    if next_day.quarter != date.quarter:                     # a quarter completed this week
        _append("procedure_volume", _quarter_procedures(sim, date.to_period("Q"), rng, data_dir), data_dir)
    save(sim, data_dir)
    return {"suggestions": len(suggestions), "accepted": int((suggestions.get("status") == "accepted").sum()),
            "dismissed": int((suggestions.get("status") == "dismissed").sum()), "consent_won": len(won),
            "unsubscribed": len(unsub_now)}
