"""My territory this week: one page for a rep, one row per doctor.

For each doctor in the rep's territory, joined from the tables the rep would otherwise open one by one: segment
and the brand's (ZS) potential; where they are on the adoption ladder now (from engagement data) and what the
rep-entered profile says, with how long ago it was confirmed; their main concern and barrier; the last contact;
progress against this quarter's plan; this week's action and why (planned, moved in by the engine, moved to
someone else, or blocked); the lead content for their stage and supporting material for their concern; and
whether they have headroom (good potential, not yet a regular user).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from nba import data, features, plan, runner, spec

LADDER = {"curiosity": "unaware", "consideration": "aware", "experience": "occasional", "loyalty": "regular", "advocacy": "advocate"}
# Supporting material for a concern: the barrier first (it is what holds them back), else their main message segment.
BARRIER_THEME = {"price": "economic_evidence", "competitor_preference": "clinical_evidence", "low_belief": "real_world_evidence",
                 "access": "access"}
MESSAGE_THEME = {"pricing": "economic_evidence", "efficacy": "clinical_evidence", "safety": "safety",
                 "patient_focus": "patient_instructions", "product_belief": "real_world_evidence"}
CHANNELS = ["rep_visit", "remote_call", "rep_email"]
LABEL = {"rep_visit": "visit", "remote_call": "remote call", "rep_email": "rep email", "marketing_email": "marketing email"}
STALE_DAYS = 365


def _v(x):
    """A value, or None when blank (so the page shows nothing rather than a placeholder)."""
    return None if x is None or (not isinstance(x, (str, bool)) and pd.isna(x)) else x


def reps(data_dir: Path | None = None) -> list[dict]:
    t = data.read_table("territory_vod", data_dir)
    t = t[(t.pilot_arm == "test") & t.rep_user_id.notna()]
    return [{"rep": r, "territory": tid, "name": n} for r, tid, n in zip(t.rep_user_id, t.id, t.name)]


def page(user: str, week: int | None = None, data_dir: Path | None = None) -> dict:
    done = runner.completed_weeks(data_dir)
    if done == 0:
        return {"weeks_run": 0}
    week = min(max(int(week or done), 1), done)
    root = Path(data_dir) if data_dir else spec.data_dir()
    terr = data.read_table("territory_vod", data_dir).set_index("id")
    if user not in set(terr.rep_user_id.dropna()):
        raise KeyError(f"No rep {user}")
    tid = terr.index[terr.rep_user_id == user][0]
    acc = data.read_table("account_vod", data_dir).set_index("id")
    ids = list(acc.index[(acc.territory_id == tid) & (acc.account_type == "hcp") & (acc.status == "active")])
    feats = features.load_snapshot(week, data_dir)
    f = feats.table.set_index("hcp_id").reindex(ids)
    prof = data.read_table("account_profile_vod", data_dir).set_index("account_id").reindex(ids)
    seg = data.read_table("hcp_segment", data_dir)
    seg = seg[seg.cycle == plan.cycle_of(week)].set_index("account_id").reindex(ids)
    st_path = root / "runs" / f"week_{week:02d}" / "plan_state_before.parquet"
    state = pd.read_parquet(st_path) if st_path.exists() else pd.DataFrame(columns=["account_id", "channel", "planned", "delivered"])
    state = state[state.account_id.isin(ids)]
    dec = pd.read_parquet(root / "runs" / f"week_{week:02d}" / "decisions.parquet")
    dec = dec[dec.hcp_id.isin(ids) & dec.status.isin(["sent", "moved", "blocked"])]
    sug = data.read_table("suggestion_vod", data_dir)
    sug = sug[(sug.user_id == user) & (pd.to_datetime(sug.suggested_date) == feats.as_of)]
    rep_said = dict(zip(zip(sug.account_id, sug.suggested_channel), sug.status))
    docs = data.read_table("promomats_document", data_dir)
    docs = docs[(docs.status == "approved") & (pd.to_datetime(docs.expiration_date) > feats.as_of)].sort_values("document_id")

    def supporting(brand, market, barrier, message):
        theme = BARRIER_THEME.get(barrier) or MESSAGE_THEME.get(message)
        if not theme:
            return None, None
        hit = docs[(docs["product"] == brand) & (docs.market == market) & (docs.content_theme == theme)]
        return theme, (hit.name.iloc[0] if len(hit) else None)

    rows = []
    for h in ids:
        r, p, s = f.loc[h], prof.loc[h], seg.loc[h]
        mine = dec[dec.hcp_id == h]
        actions = []
        for d in mine.itertuples():
            kind = ("planned" if d.status == "sent" else "given to another doctor" if d.status == "moved" else "blocked") \
                if d.origin == "plan" else "moved in by the engine"
            decision = rep_said.get((h, d.final_channel)) if d.origin != "plan" and d.final_channel in CHANNELS else None
            actions.append({"kind": kind, "channel": LABEL.get(d.final_channel, d.final_channel), "theme": d.content_theme,
                            "why": d.reason if d.status == "sent" else d.not_sent_reason, "rep_decision": decision,
                            "own": d.final_channel in CHANNELS})
        sp = state[state.account_id == h]
        progress = {LABEL[c]: {"planned": int(g.planned.sum()), "done": int(g.delivered.sum())}
                    for c, g in sp.groupby("channel") if c in LABEL and g.planned.sum() > 0}
        stage = r.stage if isinstance(r.stage, str) else None
        ladder_now = LADDER.get(stage)
        updated = pd.to_datetime(p.last_updated) if pd.notna(p.last_updated) else None
        age = int((feats.as_of - updated).days) if updated is not None else None
        theme, material = supporting(r.brand, r.market, p.barrier, p.message_segment)
        band = s.potential_band if isinstance(s.potential_band, str) else None
        rows.append({
            "id": h, "name": acc.loc[h, "name"], "specialty": acc.loc[h, "specialty_1_vod"],
            "segment": s.segment if isinstance(s.segment, str) else None, "potential": band, "zs_potential": _v(p.zs_potential),
            "ladder_now": ladder_now, "stage": stage, "profile_ladder": _v(p.usage_ladder),
            "profile_out_of_date": bool(isinstance(p.usage_ladder, str) and ladder_now and p.usage_ladder != ladder_now
                                        and not (p.usage_ladder == "regular" and ladder_now == "advocate")),
            "belief": _v(p.belief_ladder), "preference": _v(p.preference_ladder), "concern": _v(p.message_segment), "barrier": _v(p.barrier),
            "competitor": _v(p.competitor), "sentiment": _v(p.sentiment), "influence": _v(p.influence),
            "profile_age_days": age, "profile_stale": bool(age is not None and age > STALE_DAYS), "profile_source": _v(p.source),
            "days_since_contact": None if pd.isna(r.days_since_last_touch) else int(r.days_since_last_touch),
            "last_channel": LABEL.get(r.last_touch_channel, r.last_touch_channel) if isinstance(r.last_touch_channel, str) else None,
            "days_since_response": None if pd.isna(r.days_since_last_response) else int(r.days_since_last_response),
            # Behind: fewer done than the plan's pro rata share for the weeks already finished this quarter.
            "progress": progress, "behind": any(v["done"] < v["planned"] * (plan.week_in_cycle(week) - 1)
                                                / spec.assumptions()["planning"]["cycle_weeks"] - 0.5 for v in progress.values()),
            "actions": actions, "has_own_action": any(a["own"] for a in actions),
            "lead_theme": next((a["theme"] for a in actions if a["kind"] in ("planned", "moved in by the engine")), None),
            "support_theme": theme, "support_material": material,
            "headroom": bool(band in ("high", "medium") and stage in ("curiosity", "consideration", "experience")),
        })
    rows.sort(key=lambda x: (not x["has_own_action"], not any(a["kind"] == "moved in by the engine" for a in x["actions"]),
                             x["name"]))
    own = [a for x in rows for a in x["actions"] if a["own"]]
    planned_q = sum(v["planned"] for x in rows for v in x["progress"].values())
    done_q = sum(v["done"] for x in rows for v in x["progress"].values())
    brief = data.read_table("rep_brief", data_dir)
    brief = brief[(brief.user_id == user) & (pd.to_datetime(brief.run_week) == feats.as_of)]
    return {
        "weeks_run": done, "week": week, "date": f"{feats.as_of:%d %b %Y}", "rep": user, "territory": tid,
        "territory_name": terr.loc[tid, "name"], "market": terr.loc[tid, "market"],
        "summary": {"doctors": len(rows), "actions_this_week": len(own),
                    "changes_from_engine": sum(1 for a in own if a["kind"] == "moved in by the engine"),
                    "quarter_planned": planned_q, "quarter_done": done_q,
                    "week_in_quarter": plan.week_in_cycle(week), "quarter_weeks": spec.assumptions()["planning"]["cycle_weeks"],
                    "behind_plan": sum(x["behind"] for x in rows), "headroom": sum(x["headroom"] for x in rows),
                    "stale_profiles": sum(x["profile_stale"] for x in rows),
                    "profiles_out_of_date": sum(x["profile_out_of_date"] for x in rows)},
        "talk_track": brief.prose.iloc[0] if len(brief) else None,
        "rows": rows,
    }
