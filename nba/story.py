"""One doctor and one rep, told from the data: the Doctor and rep view.

Doctor: every touch over the pilot (and the 8 weeks before), with its content's journey stage, whether it matched the
doctor's stage, whether they responded, and, in test territories, why the engine planned or moved it; their weekly
journey stage; a control comparison chosen by a fixed rule (same market, segment, starting stage and specialty,
closest number of touches); and the whole comparable peer group in both arms, so one pair never stands alone.

Rep: the rep's 26 weeks against a control rep chosen by a fixed rule (same market, closest number of doctors) and
the arm averages; per week, planned touches delivered and changes from the engine; and one week in detail.
Everything is read from the public tables and the run outputs; nothing here changes data.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from nba import data, spec

STAGES = ["curiosity", "consideration", "experience", "loyalty", "advocacy"]
CH_LABEL = {"rep_visit": "visit", "remote_call": "remote call", "rep_email": "rep email", "marketing_email": "marketing email",
            "webinar": "webinar"}
TOUCHES = """
select c.account_id, c.call_date::timestamp as ts, case when c.call_type = 'remote' then 'remote_call' else 'rep_visit' end as channel,
       nullif(split_part(c.key_message_ids, ':', 1), '') as doc, c.next_step <> 'none' as responded, c.user_id
from call2_vod c join user_vod u on u.id = c.user_id where c.status = 'submitted' and u.role = 'rep'
union all
select s.account_id, s.email_sent_date, 'rep_email', s.approved_document_id,
       exists (select 1 from email_activity_vod a where a.sent_email_id = s.id and a.event_type = 'open'), s.user_id
from sent_email_vod s where s.status = 'sent'
union all
select account_id, sent_datetime, 'marketing_email', approved_document_id, opened, null from agency_email
union all
select account_id, event_date::timestamp, 'webinar', null, attended, null from event_attendee_vod where event_type = 'webinar'
"""


def _start() -> pd.Timestamp:
    return pd.Timestamp(spec.design()["clock"]["pilot_start"])


def _ctx(data_dir=None) -> dict:
    """Shared lookups: accounts, territories, documents, weekly stages, segments, run decisions."""
    root = Path(data_dir) if data_dir else spec.data_dir()
    acc = data.read_table("account_vod", data_dir).set_index("id")
    terr = data.read_table("territory_vod", data_dir).set_index("id")
    docs = data.read_table("promomats_document", data_dir).set_index("document_id")
    st = data.read_table("hcp_stage_weekly", data_dir)
    st["week"] = pd.to_datetime(st.week)
    seg = data.read_table("hcp_segment", data_dir)
    files = sorted((root / "runs").glob("week_*/decisions.parquet"))
    dec = pd.concat([pd.read_parquet(f, columns=["hcp_id", "channel", "final_channel", "origin", "status", "reason",
                                                 "not_sent_reason", "rule_ids", "content_theme", "rep_user_id"])
                     .assign(week=int(f.parent.name[-2:])) for f in files], ignore_index=True) if files else pd.DataFrame()
    return {"acc": acc, "terr": terr, "docs": docs, "st": st, "seg": seg, "dec": dec, "weeks": len(files)}


def _stage_at(st: pd.DataFrame, ids, when: pd.Series) -> pd.Series:
    """Each touch's doctor stage: the latest weekly stage on or before the touch date."""
    s = st[st.account_id.isin(set(ids))].rename(columns={"week": "ts"})
    s = pd.DataFrame({"account_id": s.account_id.astype(str).to_numpy(object), "ts": pd.to_datetime(s.ts).astype("datetime64[ns]"),
                      "stage": s.stage.astype(str).to_numpy(object)}).sort_values("ts")
    # A week's stage row is written after that week's touches, so the stage a touch met is the last row from an
    # earlier week (strictly before the Monday of the touch's week).
    monday = pd.to_datetime(pd.Series(when).to_numpy()).astype("datetime64[ns]")
    monday = monday - pd.to_timedelta(monday.dayofweek, unit="D")
    left = pd.DataFrame({"account_id": pd.Series(ids, dtype=object).astype(str).to_numpy(object),
                         "ts": monday.normalize()}).reset_index().sort_values("ts")
    out = pd.merge_asof(left, s, on="ts", by="account_id", direction="backward", allow_exact_matches=False)
    return out.set_index("index").stage.reindex(range(len(ids)))


def _touches(ids: list, ctx: dict, data_dir=None, before_weeks: int = 8) -> pd.DataFrame:
    con = data.connect(data_dir)
    t = con.execute(f"select * from ({TOUCHES}) where list_contains(?, account_id) and ts >= ?",
                    [list(ids), (_start() - pd.Timedelta(weeks=before_weeks)).to_pydatetime()]).df()
    if t.empty:
        return t.assign(stage=None, content_stage=None, theme=None, matched=False, week=0)
    t = t.sort_values(["account_id", "ts", "channel"]).reset_index(drop=True)
    t["stage"] = _stage_at(ctx["st"], t.account_id.tolist(), t.ts).to_numpy()
    t["content_stage"] = t.doc.map(ctx["docs"].journey_stage)
    t["theme"] = t.doc.map(ctx["docs"].content_theme)
    t["matched"] = [isinstance(a, str) and a == b for a, b in zip(t.content_stage, t.stage)]
    t["week"] = ((t.ts - _start()).dt.days // 7 + 1).astype(int)
    return t


def _stage_path(h: str, ctx: dict, before_weeks: int = 8) -> list[dict]:
    s = ctx["st"][(ctx["st"].account_id == h) & (ctx["st"].week >= _start() - pd.Timedelta(weeks=before_weeks))]
    s = s.sort_values("week")
    return [{"week": int((w - _start()).days // 7 + 1), "date": f"{w:%d %b %Y}", "stage": st} for w, st in zip(s.week, s.stage)]


def _start_end(ids, ctx) -> tuple[pd.Series, pd.Series]:
    st = ctx["st"]
    start = st[st.week < _start()].sort_values("week").groupby("account_id").stage.last()
    end = st.sort_values("week").groupby("account_id").stage.last()
    idx = pd.Index(ids)
    return start.reindex(idx), end.reindex(idx)


def _arm(h, ctx) -> str:
    t = ctx["acc"].territory_id.get(h)
    return ctx["terr"].pilot_arm.get(t, "none") if isinstance(t, str) else "none"


def _segment(h, ctx, cycle=1):
    s = ctx["seg"]
    r = s[(s.account_id == h) & (s.cycle == cycle)]
    return r.segment.iloc[0] if len(r) else None


def _profile(h: str, ctx: dict, t: pd.DataFrame) -> dict:
    a = ctx["acc"].loc[h]
    terr = ctx["terr"].loc[a.territory_id] if isinstance(a.territory_id, str) and a.territory_id in ctx["terr"].index else None
    mine = t[(t.account_id == h) & (t.week >= 1)]
    start, end = _start_end([h], ctx)
    return {"id": h, "name": a["name"], "specialty": a.specialty_1_vod, "market": a.market, "territory": a.territory_id,
            "rep": terr.rep_user_id if terr is not None else None, "arm": _arm(h, ctx),
            "segment_q1": _segment(h, ctx, 1), "segment_q2": _segment(h, ctx, 2),
            "stage_start": start.iloc[0], "stage_end": end.iloc[0],
            "stages_moved": int(STAGES.index(end.iloc[0]) - STAGES.index(start.iloc[0])) if isinstance(start.iloc[0], str) and isinstance(end.iloc[0], str) else None,
            "touches": int(len(mine)), "matched": int(mine.matched.sum()), "responses": int(mine.responded.sum()),
            "matched_pct": round(100 * mine.matched.mean(), 0) if len(mine) else None}


def showcase_doctors(data_dir=None, n: int = 12) -> list[dict]:
    """Test doctors who moved forward after the engine moved a touch to them (for the picker)."""
    ctx = _ctx(data_dir)
    if not ctx["weeks"]:
        return []
    d = ctx["dec"]
    moved_in = d[(d.status == "sent") & (d.origin != "plan")].groupby("hcp_id").size()
    ids = list(moved_in.index)
    start, end = _start_end(ids, ctx)
    gain = end.map(STAGES.index) - start.map(STAGES.index)
    df = pd.DataFrame({"gain": gain, "moved_in": moved_in.reindex(ids).to_numpy()}, index=ids).dropna()
    df = df[(df.gain >= 1) & (df.gain <= 2)]
    df["arm"] = [_arm(h, ctx) for h in df.index]
    df = df[df.arm == "test"].sort_values(["gain", "moved_in"], ascending=False).head(n)
    return [{"id": h, "name": ctx["acc"].loc[h, "name"], "specialty": ctx["acc"].loc[h, "specialty_1_vod"],
             "stages_moved": int(r.gain), "changes": int(r.moved_in)} for h, r in df.iterrows()]


def doctor(h: str, data_dir=None) -> dict:
    ctx = _ctx(data_dir)
    if h not in ctx["acc"].index:
        raise KeyError(f"No doctor {h}")
    a = ctx["acc"].loc[h]
    start, _ = _start_end([h], ctx)
    seg = _segment(h, ctx, 1)
    # Peers: same market, quarter-1 segment, starting stage and specialty, in both arms.
    s1 = ctx["seg"][ctx["seg"].cycle == 1].set_index("account_id")
    peers = [p for p in s1.index[(s1.segment == seg)] if p != h and ctx["acc"].market.get(p) == a.market
             and ctx["acc"].specialty_1_vod.get(p) == a.specialty_1_vod]
    ps, pe = _start_end(peers, ctx)
    peers = [p for p in peers if ps.get(p) == start.iloc[0]]
    t = _touches([h] + peers, ctx, data_dir)
    pt = t[t.week >= 1].groupby("account_id").agg(touches=("ts", "size"), matched=("matched", "mean"), responses=("responded", "sum"))
    ps, pe = _start_end(peers, ctx)
    group = pd.DataFrame({"arm": [_arm(p, ctx) for p in peers],
                          "moved": [(isinstance(e, str) and isinstance(s, str) and STAGES.index(e) > STAGES.index(s))
                                    for s, e in zip(ps.reindex(peers), pe.reindex(peers))]}, index=peers).join(pt)
    group["touches"] = group.touches.fillna(0)
    by_arm = {arm: {"doctors": int(len(g)), "moved_up_pct": round(100 * g.moved.mean(), 0) if len(g) else None,
                    "avg_touches": round(g.touches.mean(), 1) if len(g) else None,
                    "matched_pct": round(100 * g.matched.mean(), 0) if g.matched.notna().any() else None}
              for arm, g in group.groupby("arm") if arm in ("test", "control")}
    # The comparison: the opposite arm's peer with the closest number of touches (ties: id order). A fixed rule, so
    # the comparison is not hand-picked.
    me = t[(t.account_id == h) & (t.week >= 1)]
    other = "control" if _arm(h, ctx) == "test" else "test"
    cand = group[group.arm == other].assign(gap=lambda g: (g.touches - len(me)).abs()).sort_values(["gap"]).index
    comp = cand[0] if len(cand) else None

    def timeline(x: str) -> list[dict]:
        tt = t[t.account_id == x].copy()
        d = ctx["dec"]
        mine = d[(d.hcp_id == x)] if len(d) else d
        rows = []
        for r in tt.itertuples():
            why, origin = None, ("before the pilot" if r.week < 1 else ("today's plan" if _arm(x, ctx) == "control" else None))
            if r.week >= 1 and len(mine) and _arm(x, ctx) == "test":
                m = mine[(mine.week == r.week) & (mine.final_channel == r.channel) & (mine.status == "sent")]
                if len(m):
                    origin = "planned" if m.origin.iloc[0] == "plan" else "moved in"
                    why = m.reason.iloc[0]
                elif r.channel == "webinar":
                    origin = "webinar"
            clean = lambda v: None if v is None or (not isinstance(v, str) and pd.isna(v)) else v   # noqa: E731
            rows.append({"date": f"{r.ts:%d %b %Y}", "week": int(r.week), "channel": r.channel, "label": CH_LABEL.get(r.channel, r.channel),
                         "theme": clean(r.theme), "content_stage": clean(r.content_stage), "stage": clean(r.stage), "matched": bool(r.matched),
                         "responded": bool(r.responded), "origin": origin, "why": why})
        moved_away = []
        if len(mine) and _arm(x, ctx) == "test":
            for r in mine[mine.status == "moved"].itertuples():
                moved_away.append({"week": int(r.week), "date": f"{_start() + pd.Timedelta(weeks=r.week - 1):%d %b %Y}",
                                   "channel": CH_LABEL.get(r.channel, r.channel), "why": r.not_sent_reason})
        return rows, moved_away

    t_me, away_me = timeline(h)
    out = {"weeks_run": ctx["weeks"], "doctor": {**_profile(h, ctx, t), "touches_list": t_me, "moved_away": away_me,
                                                 "stages": _stage_path(h, ctx)},
           "peers": {"rule": "same market, quarter-1 segment, starting stage and specialty", "by_arm": by_arm}}
    if comp:
        t_c, away_c = timeline(comp)
        out["comparison"] = {**_profile(comp, ctx, t), "touches_list": t_c, "moved_away": away_c, "stages": _stage_path(comp, ctx),
                             "rule": f"the {other} doctor in that peer group with the closest number of touches"}
    return out


def rep(user: str, week: int | None = None, data_dir=None) -> dict:
    ctx = _ctx(data_dir)
    terr = ctx["terr"]
    if user not in set(terr.rep_user_id.dropna()):
        raise KeyError(f"No rep {user}")
    tid = terr.index[terr.rep_user_id == user][0]
    arm, market = terr.loc[tid].pilot_arm, terr.loc[tid].market

    def summary(u: str) -> dict:
        t_id = terr.index[terr.rep_user_id == u][0]
        acc = ctx["acc"]
        ids = list(acc.index[(acc.territory_id == t_id) & (acc.account_type == "hcp")])
        tt = _touches(ids, ctx, data_dir, before_weeks=0)
        visits = tt[(tt.channel == "rep_visit") & (tt.user_id == u)]
        s, e = _start_end(ids, ctx)
        moved = [(isinstance(a, str) and isinstance(b, str) and STAGES.index(b) > STAGES.index(a)) for a, b in zip(s, e)]
        sug = data.read_table("suggestion_vod", data_dir)
        sug = sug[sug.user_id == u]
        weekly = visits.groupby("week").size()
        return {"rep": u, "territory": t_id, "arm": terr.loc[t_id].pilot_arm, "doctors": len(ids), "visits": int(len(visits)),
                "visits_matched_pct": round(100 * visits.matched.mean(), 0) if len(visits) else None,
                "next_step_pct": round(100 * visits.responded.mean(), 0) if len(visits) else None,
                "doctors_moved_up_pct": round(100 * np.mean(moved), 0) if moved else None,
                "changes": int(len(sug)), "changes_accepted_pct": round(100 * (sug.status == "accepted").mean(), 0) if len(sug) else None,
                "visits_by_week": {int(k): int(v) for k, v in weekly.items()}}

    me = summary(user)
    # The comparison: the opposite arm's rep in the same market with the closest number of doctors (a fixed rule).
    other = "control" if arm == "test" else "test"
    acc = ctx["acc"]
    size = acc[acc.account_type == "hcp"].territory_id.value_counts()
    cands = terr[(terr.pilot_arm == other) & (terr.market == market) & terr.rep_user_id.notna()].copy()
    cands["gap"] = (pd.Series(cands.index.map(size), index=cands.index).fillna(0) - me["doctors"]).abs()
    comp = summary(cands.sort_values(["gap"]).rep_user_id.iloc[0]) if len(cands) else None

    weeks, detail = [], None
    d = ctx["dec"]
    if len(d) and arm == "test":
        mine = d[(d.rep_user_id == user) & d.final_channel.isin(["rep_visit", "remote_call", "rep_email"])]   # the rep's own touches
        for w, g in mine.groupby("week"):
            weeks.append({"week": int(w), "planned_delivered": int(((g.origin == "plan") & (g.status == "sent")).sum()),
                          "moved_in": int(((g.origin != "plan") & (g.status == "sent")).sum()),
                          "moved_out": int((g.status == "moved").sum()), "blocked": int((g.status == "blocked").sum())})
        if week is None:
            busiest = sorted(weeks, key=lambda x: (-x["moved_in"], x["week"]))
            week = busiest[0]["week"] if busiest else 1
        g = mine[mine.week == week]
        names = acc.name
        sug = data.read_table("suggestion_vod", data_dir)
        sug = sug[(sug.user_id == user) & (pd.to_datetime(sug.suggested_date) == _start() + pd.Timedelta(weeks=week - 1))]
        status = dict(zip(zip(sug.account_id, sug.suggested_channel), sug.status))
        planned = g[(g.origin == "plan") & g.status.isin(["sent", "moved", "blocked"]) & g.final_channel.isin(["rep_visit", "remote_call", "rep_email"])]
        changes = g[(g.origin != "plan") & (g.status == "sent") & g.final_channel.isin(["rep_visit", "remote_call", "rep_email"])]
        brief = data.read_table("rep_brief", data_dir)
        brief = brief[(brief.user_id == user) & (pd.to_datetime(brief.run_week) == _start() + pd.Timedelta(weeks=week - 1))]
        detail = {"week": int(week), "date": f"{_start() + pd.Timedelta(weeks=week - 1):%d %b %Y}",
                  "planned": [{"doctor": names.get(r.hcp_id, r.hcp_id), "id": r.hcp_id, "channel": CH_LABEL.get(r.final_channel, r.final_channel),
                               "theme": r.content_theme, "status": r.status, "note": r.not_sent_reason} for r in planned.itertuples()],
                  "changes": [{"doctor": names.get(r.hcp_id, r.hcp_id), "id": r.hcp_id, "channel": CH_LABEL.get(r.final_channel, r.final_channel),
                               "theme": r.content_theme, "why": r.reason, "rep_decision": status.get((r.hcp_id, r.final_channel), "open")}
                              for r in changes.itertuples()],
                  "talk_track": brief.prose.iloc[0] if len(brief) else None}
    arms = {}
    for a_ in ("test", "control"):
        reps = terr[(terr.pilot_arm == a_) & terr.rep_user_id.notna()].rep_user_id
        arms[a_] = {"reps": int(len(reps))}
    return {"weeks_run": ctx["weeks"], "rep": me, "comparison": comp, "weeks": weeks, "detail": detail,
            "comparison_rule": f"the {other} rep in {market} with the closest number of doctors"}


def showcase_reps(data_dir=None) -> list[dict]:
    """Test reps, most engine changes accepted first (for the picker)."""
    ctx = _ctx(data_dir)
    sug = data.read_table("suggestion_vod", data_dir)
    if sug.empty:
        return []
    g = sug.groupby("user_id").agg(changes=("id", "size"), accepted=("status", lambda s: int((s == "accepted").sum())))
    terr = ctx["terr"].reset_index().set_index("rep_user_id")
    g = g[g.index.isin(terr.index)]
    g["territory"] = terr.loc[g.index, "id"]
    return [{"rep": u, "territory": r.territory, "changes": int(r.changes), "accepted": int(r.accepted)}
            for u, r in g.sort_values(["accepted", "changes"], ascending=False).head(15).iterrows()]
