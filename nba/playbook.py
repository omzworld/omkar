"""Playbooks: what an action means in practice (spec/rules/playbooks.yaml).

A rule's action says "rep visit, efficacy". The playbook says what the rep or agency actually does:
- email: sender, approved template, subject line, the doctor's best send window (learned from when they open
  email), the follow-up steps and the quiet period after it;
- visit or call: the call objective (next rung of the adoption ladder), the slide order (stage opener, the
  action's theme, a slide for the doctor's recorded barrier), the question to ask, the objection handler, the
  leave-behind and what happens afterwards;
- account (KAM) actions and webinars: the agenda or the invitation sequence.

`generic(rule)` describes the playbook for a rule without a doctor (rule studio). `for_doctor(...)` fills it in
for one doctor in one week (talk track, My territory).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

from nba import data, features, spec

EMAIL = {"marketing_email", "rep_email"}
CALL = {"rep_visit", "remote_call"}
KAM = {"kam_visit", "kam_brief"}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DEFAULT_WINDOW = {"UK": "Tuesday 07:30", "DE": "Wednesday 08:00"}
SAMPLE_BRANDS = {"Movicol"}
MAX_SAMPLES = 4


@lru_cache(maxsize=1)
def book() -> dict:
    return yaml.safe_load((spec.ROOT / "spec" / "rules" / "playbooks.yaml").read_text())


def _words(x: str | None) -> str:
    return (x or "").replace("_", " ")


def _theme(theme: str) -> dict:
    return book()["themes"].get(theme, {})


def generic(rule_id: str, channel: str, theme: str) -> dict:
    """The playbook for a rule's action, before it is filled in for a doctor."""
    b, over = book(), book()["rules"].get(rule_id, {})
    ch, th = b["channels"].get(channel, {}), _theme(theme)
    out = {"kind": "email" if channel in EMAIL else "call" if channel in CALL else "account" if channel in KAM
           else "event" if channel == "webinar" else "other", "channel": _words(channel), "theme": _words(theme)}
    if channel in EMAIL or channel == "webinar":
        out.update(sender=ch.get("sender"), subject=th.get("subject") or None,
                   send_window="the doctor's usual opening time, learned from their email history",
                   follow_up=over.get("follow_up", ch.get("follow_up", [])), quiet_days=ch.get("quiet_days"))
    if channel in CALL:
        out.update(objective=over.get("objective", "the next rung of the adoption ladder from where the doctor is"),
                   slides=["Opener for the doctor's ladder stage", th.get("slide") or f"{_words(theme)} slide",
                           "One slide for the barrier in the doctor's profile"],
                   ask=over.get("ask", th.get("ask")), objection="Handler for the doctor's recorded barrier",
                   leave_behind="Printed version of the theme's approved material; a sample where allowed",
                   after=over.get("after", ch.get("after", [])))
    if channel in KAM:
        out.update(objective=over.get("objective", f"Account plan: {_words(theme)}"),
                   agenda=[th.get("slide") or _words(theme), "Agree the unit's next step and owner"],
                   after=over.get("after", ch.get("after", [])))
    return {k: v for k, v in out.items() if v not in (None, [], "")}


@lru_cache(maxsize=2)
def _asset_names(root: str) -> dict:
    d = pd.read_parquet(Path(root) / "promomats_document.parquet", columns=["document_id", "name"])
    return dict(zip(d.document_id, d.name))


PART = [(7, "07:30"), (11, "11:30"), (14, "14:00"), (18, "18:30")]


def _part(hour: int) -> str:
    return next((t for h, t in reversed(PART) if hour >= h), "07:30")


@lru_cache(maxsize=4)
def _open_windows(root: str, as_of: pd.Timestamp) -> tuple[dict, dict]:
    """When each doctor usually opens email (weekday and part of day, from all history before `as_of`; needs 3+
    opens and one slot holding at least a third of them), and the usual slot for their market and specialty."""
    d = Path(root)
    sent = pd.read_parquet(d / "sent_email_vod.parquet", columns=["id", "account_id"])
    ev = pd.read_parquet(d / "email_activity_vod.parquet", columns=["sent_email_id", "event_type", "event_datetime"])
    ev = ev[(ev.event_type == "open") & (ev.event_datetime < as_of)].merge(sent, left_on="sent_email_id", right_on="id")
    acc = pd.read_parquet(d / "account_vod.parquet", columns=["id", "specialty_1_vod", "territory_id"])
    if ev.empty:
        return {}, {}
    ev["slot"] = ev.event_datetime.dt.day_of_week.map(lambda i: DAYS[i]) + " " + ev.event_datetime.dt.hour.map(_part)
    g = ev.groupby(["account_id", "slot"]).size().reset_index(name="n").sort_values(["account_id", "n", "slot"],
                                                                                    ascending=[True, False, True])
    tot = ev.groupby("account_id").size()
    best = g.drop_duplicates("account_id")
    best = best[(best.account_id.map(tot) >= 3) & (best.n * 3 >= best.account_id.map(tot))]
    own = {a: (slot, int(n), int(tot[a])) for a, slot, n in zip(best.account_id, best.slot, best.n)}
    ev = ev.merge(acc, left_on="account_id", right_on="id", suffixes=("", "_a"))
    ev["seg"] = ev.territory_id.str[:2] + "|" + ev.specialty_1_vod.fillna("")
    sg = ev.groupby(["seg", "slot"]).size().reset_index(name="n").sort_values(["seg", "n", "slot"], ascending=[True, False, True])
    seg = dict(zip(sg.drop_duplicates("seg").seg, sg.drop_duplicates("seg").slot))
    return own, seg


def for_doctor(week: int, hcp_id: str, channel: str, theme: str, rule_id: str | None = None,
               asset: str | None = None, data_dir=None) -> dict:
    """The playbook filled in for one doctor this week."""
    root = Path(data_dir) if data_dir else spec.data_dir()
    feats = features.load_snapshot(week, data_dir)
    row = feats.table.set_index("hcp_id").loc[hcp_id]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    prof = data.read_table("account_profile_vod", data_dir).set_index("account_id")
    p = prof.loc[hcp_id] if hcp_id in prof.index else None
    barrier = p.barrier if p is not None and isinstance(p.barrier, str) and p.barrier != "none" else None
    if asset and asset in _asset_names(str(root)):
        asset = f"{_asset_names(str(root))[asset]} ({asset})"
    stage = row.stage if isinstance(row.stage, str) else None
    pb = generic(rule_id or "", channel, theme)
    b = book()
    th = _theme(theme)
    if channel in EMAIL or channel == "webinar":
        own, seg = _open_windows(str(root), feats.as_of)
        win, peer = own.get(hcp_id), seg.get(f"{row.market}|{row.specialty}")
        pb["send_window"] = (f"{win[0]} ({win[1]} of their {win[2]} opens were in that slot)" if win
                             else f"{peer} (when {_words(row.specialty)}s in {row.market} usually open; too few of their own opens)"
                             if peer else f"{DEFAULT_WINDOW.get(row.market, 'Tuesday 07:30')} (market default)")
        pb["subject"] = (th.get("subject") or "").replace("{brand}", _words(row.brand)) or None
        if asset:
            pb["template"] = asset
    if channel in CALL:
        over = b["rules"].get(rule_id or "", {})
        pb["objective"] = over.get("objective") or b["objective_by_stage"].get(stage, pb.get("objective"))
        slides = [f"Open: {b['open_slide_by_stage'].get(stage, 'Agenda')}",
                  f"Lead: {th.get('slide') or _words(theme)}" + (f" ({asset})" if asset else "")]
        bar = b["barriers"].get(barrier)
        if bar and bar["theme"] != theme:
            slides.append(f"Support: {_theme(bar['theme']).get('slide', _words(bar['theme']))} (their barrier: {_words(barrier)})")
        pb["slides"] = slides if th.get("slide") else []
        pb["objection"] = bar["objection"] if bar else "No barrier recorded: ask what would stop them using it."
        can_sample = (row.brand in SAMPLE_BRANDS and channel == "rep_visit" and bool(row.hcp_prescriber)
                      and (row.samples_ytd or 0) < MAX_SAMPLES)
        pb["leave_behind"] = (f"Sample ({int(row.samples_ytd or 0)} of {MAX_SAMPLES} used this year) and the printed "
                              f"{_words(theme)} leaflet") if can_sample else \
            f"The {_words(theme)} leaflet, emailed after the call" if channel == "remote_call" else f"Printed {_words(theme)} leaflet"
        if not th.get("slide"):                      # a conversation, not a detail: no slides, objection or leaflet
            pb.pop("objection", None)
            pb.pop("leave_behind", None)
        if p is not None and pd.notna(p.last_updated) and (feats.as_of - pd.to_datetime(p.last_updated)).days > 365:
            pb["after"] = [*pb.get("after", []), "Profile is over a year old: confirm concern, barrier and ladders"]
    pb["stage"] = stage
    pb["barrier"] = barrier
    return {k: v for k, v in pb.items() if v not in (None, [], "")}
