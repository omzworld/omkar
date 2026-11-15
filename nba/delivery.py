"""Delivery: turn the week's decisions into what the field and the agency receive. Nothing is sent anywhere;
files are written under data/runs/week_NN/.

- Veeva CRM suggestion payloads for reps and key account managers, validated against
  spec/schemas/suggestion_payload.json;
- the agency file of marketing emails;
- one talk track per rep in a test territory (spec/delivery/talk_track_design.md): a structured brief built from
  the data, then prose. Without a language model key the prose comes from a template. Either way a grounding check
  asserts that every number in the prose appears in the structured brief.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pandas as pd

from nba import data, spec
from nba.pipeline import WeekResult

REP_DELIVERED = ["rep_visit", "remote_call", "rep_email", "kam_visit", "kam_brief"]
RECORD_TYPE = {"rep_visit": "Call", "kam_visit": "Call", "kam_brief": "Call", "remote_call": "Remote_Call",
               "rep_email": "Email"}
CHANNEL_LABEL = {"rep_visit": "visit", "remote_call": "remote call", "rep_email": "rep email",
                 "kam_visit": "account visit", "kam_brief": "account brief", "marketing_email": "email",
                 "webinar": "webinar invitation"}
LISTEN_FOR = {"movicol": "ask what changed in the practice", "engagement_triggers": "ask what was most useful so far",
              "bowel_preparations": "ask how preparation quality is tracked in the unit",
              "xifaxan": "ask how patients are followed up after discharge"}
LISTEN_FOR_THEME = {"reason_check": "ask how they prefer to hear from us, and what has not been useful",
                    "introduction": "ask whether we may send material by email"}
NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _n(count: int, word: str, plural: str | None = None) -> str:
    """'1 visit', '3 visits'."""
    return f"{count} {word if count == 1 else (plural or word + 's')}"


def _run_dir(week: int, data_dir) -> Path:
    d = (Path(data_dir) if data_dir else spec.data_dir()) / "runs" / f"week_{week:02d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _label(text) -> str:
    return str(text).replace("_", " ") if text is not None and not pd.isna(text) else ""


# --------------------------------------------------------------------------------------------- suggestions

def suggestions(r: WeekResult, data_dir=None) -> pd.DataFrame:
    """One Veeva suggestion per action a rep or key account manager is asked to take (suggestion_vod rows)."""
    s = r.sent[r.sent.final_channel.isin(REP_DELIVERED)].sort_values(["final_return", "candidate_id"],
                                                                      ascending=[False, True])
    names = data.read_table("account_vod", data_dir).set_index("id").name
    owner = s.kam_user_id.where(s.final_channel.isin(["kam_visit", "kam_brief"]), s.rep_user_id)
    title = [f"{CHANNEL_LABEL[ch].capitalize()}: {_label(t) or 'check in'} - {names.get(a, a)}"[:80]
             for ch, t, a in zip(s.final_channel, s.content_theme, s.hcp_id)]
    return pd.DataFrame({
        "id": [f"SUG-W{r.week:02d}-{i + 1:04d}" for i in range(len(s))], "account_id": s.hcp_id.to_numpy(),
        "user_id": owner.to_numpy(), "title": title, "reason": s.reason.str.slice(0, 255).to_numpy(),
        "suggested_channel": s.final_channel.to_numpy(),
        "approved_document_id": s.asset_id.astype(object).where(s.asset_id.notna(), None).to_numpy(),
        "suggested_date": r.feats.as_of, "expiration_date": r.feats.as_of + pd.Timedelta(days=13),
        "expected_return": s.final_return.to_numpy(), "status": "open", "dismiss_reason": None,
        "rule_ids": s.rule_ids.to_numpy(), "run_id": f"RUN-W{r.week:02d}",
        "chance_tier": s.chance_tier.to_numpy()})


def veeva_payloads(sug: pd.DataFrame) -> list[dict]:
    """The Veeva CRM suggestion records, validated against the schema in the spec pack."""
    schema = json.loads((spec.SPEC / "schemas" / "suggestion_payload.json").read_text())
    out = []
    for owner, g in sug.groupby("user_id", sort=True):
        for priority, (_, row) in enumerate(g.sort_values("expected_return", ascending=False).iterrows(), start=1):
            p = {"Account_vod__c": row.account_id, "OwnerId": owner, "Record_Type": RECORD_TYPE[row.suggested_channel],
                 "Title_vod__c": row.title, "Reason_vod__c": row.reason,
                 "Suggested_Date_vod__c": f"{row.suggested_date:%Y-%m-%d}",
                 "Expiration_Date_vod__c": f"{row.expiration_date:%Y-%m-%d}",
                 "Priority_vod__c": min(priority, 5), "Expected_Return__c": round(float(row.expected_return), 2),
                 "Chance_Tier__c": row.chance_tier, "Rule_Ids__c": row.rule_ids, "Run_Id__c": row.run_id}
            if isinstance(row.approved_document_id, str):
                p["Approved_Document_vod__c"] = row.approved_document_id
            jsonschema.validate(p, schema, format_checker=jsonschema.FormatChecker())
            out.append(p)
    return out


def agency_file(r: WeekResult) -> pd.DataFrame:
    """Marketing emails for the agency to send, two send windows a week."""
    s = r.sent[r.sent.final_channel == "marketing_email"].sort_values("final_return", ascending=False)
    return pd.DataFrame({"account_id": s.hcp_id, "market": s.market, "approved_document_id": s.asset_id,
                         "content_theme": s.content_theme,
                         "send_window": ["Tuesday" if i % 2 == 0 else "Thursday" for i in range(len(s))],
                         "expected_return_eur": s.final_return, "rule_ids": s.rule_ids, "run_id": f"RUN-W{r.week:02d}"})


# --------------------------------------------------------------------------------------------- talk tracks

def _last_week(con, rep: str, territory: str, start, end) -> dict:
    params = {"rep": rep, "t": territory, "s": start.date(), "e": end.date()}

    def q(sql):
        used = {k: v for k, v in params.items() if f"${k}" in sql}
        return con.execute(sql, used).fetchone()
    visits = q("""select count(*) from call2_vod where user_id = $rep and status = 'submitted'
                            and call_type = 'face_to_face' and call_date >= $s and call_date < $e""")[0]
    # Most common dismiss reason, ties broken alphabetically so a replay with the same seed gives the same brief
    # (DuckDB's mode() picks any of the tied values).
    sug = q("""select count(*) filter (where status = 'accepted'), count(*) filter (where status = 'dismissed'),
                       (select dismiss_reason from suggestion_vod
                         where user_id = $rep and suggested_date >= $s and suggested_date < $e and dismiss_reason is not null
                         group by 1 order by count(*) desc, dismiss_reason limit 1)
                  from suggestion_vod
                 where user_id = $rep and suggested_date >= $s and suggested_date < $e""")
    emails = q("""select count(*), count(*) filter (where exists (select 1 from email_activity_vod a
                                 where a.sent_email_id = s.id and a.event_type = 'open'))
                            from sent_email_vod s where user_id = $rep and email_sent_date >= $s
                            and email_sent_date < $e""")
    webinar = q("""select count(*) from event_attendee_vod e join account_vod a on a.id = e.account_id
                             where a.territory_id = $t and e.attended and e.event_type = 'webinar'
                             and e.event_date >= $s and e.event_date < $e""")[0]
    return {"visits_completed": int(visits), "suggestions_accepted": int(sug[0]), "suggestions_dismissed": int(sug[1]),
            "most_common_dismiss_reason": _label(sug[2]) or None, "rep_emails_sent": int(emails[0]),
            "rep_emails_opened": int(emails[1]), "webinar_attendees": int(webinar)}


def structured_brief(r: WeekResult, rep: str, territory: pd.Series, sug: pd.DataFrame, con, names, parents) -> dict:
    t = r.feats.table
    terr_rows = t[t.territory_id == territory.id]
    bricks = terr_rows.drop_duplicates("brick_id").sort_values("brick_potential_index", ascending=False).head(3)
    mine = sug[sug.user_id == rep].sort_values("expected_return", ascending=False)
    d = r.decisions[r.decisions.territory_id == territory.id]
    held = d[d.status == "not_sent"]
    reasons = held.constraint_id.fillna("").astype(str) + " " + held.not_sent_reason.fillna("")
    sent = r.sent.set_index("hcp_id")
    items = []
    for rank, (_, s) in enumerate(mine.iterrows(), start=1):
        dec = sent.loc[s.account_id]
        msgs = dec.key_messages.split("|") if isinstance(dec.key_messages, str) else []
        items.append({"rank": rank, "physician": names.get(s.account_id, s.account_id),
                      "account": parents.get(s.account_id, ""), "channel": CHANNEL_LABEL[s.suggested_channel],
                      "theme": _label(dec.content_theme) or "check in", "reason": s.reason,
                      "expected_return_eur": int(round(s.expected_return)), "key_message": msgs[0] if msgs else None,
                      "listen_for": LISTEN_FOR_THEME.get(dec.content_theme) or
                      LISTEN_FOR.get(dec.family, "ask what would help most"),
                      "suggestion_id": s.id, "origin": dec.origin})
    return {
        "territory": {"id": territory.id, "name": territory["name"], "market": territory.market, "week": r.week,
                      "week_start": f"{r.feats.as_of:%Y-%m-%d}"},
        "last_week": _last_week(con, rep, territory.id, r.feats.as_of - pd.Timedelta(days=7), r.feats.as_of),
        "bricks": [{"brick_id": b.brick_id, "change_pct": None if pd.isna(b.brick_volume_r3m_pct)
                    else float(b.brick_volume_r3m_pct),
                    "months_declining": int(b.brick_r3m_months_declining), "months_growing": int(b.brick_r3m_months_growing)}
                   for _, b in bricks.iterrows()],
        "suggestions": items,
        "candidates_in_territory": int(d.hcp_id.nunique()),
        "held": {"cadence": int(reasons.str.contains("Delayed").sum()),
                 "capacity": int(reasons.str.contains("slots left").sum()),
                 "consent": int(reasons.str.contains("consent|opt-in|opt in", regex=True).sum())},
        "discovery_note": "One suggestion was found by discovery." if any(i["origin"] == "discovery" for i in items)
        else None,
    }


def template_prose(b: dict) -> str:
    lw = b["last_week"]
    lines = ["Your territory last week.",
             f"You completed {_n(lw['visits_completed'], 'visit')}. "
             f"{_n(lw['suggestions_accepted'], 'suggestion')} accepted and {lw['suggestions_dismissed']} dismissed"
             + (f", most often marked {lw['most_common_dismiss_reason']}." if lw["most_common_dismiss_reason"] else ".")
             + (f" You sent {_n(lw['rep_emails_sent'], 'email')} and {lw['rep_emails_opened']} "
                f"{'was' if lw['rep_emails_opened'] == 1 else 'were'} opened." if lw["rep_emails_sent"] else "")
             + (f" {_n(lw['webinar_attendees'], 'physician')} attended a webinar." if lw["webinar_attendees"] else "")]
    trend = []
    for br in b["bricks"]:
        if br["change_pct"] is None:
            continue
        c = br["change_pct"]
        steady = br.get("months_declining", 0) >= 2 if c < 0 else br.get("months_growing", 0) >= 2
        trend.append(f"brick {br['brick_id']} is {'down' if c < 0 else 'up'} {abs(c):g}%"
                     + (" and the trend is steady" if steady else ", a one-off for now") if abs(c) >= 1
                     else f"brick {br['brick_id']} is flat")
    if trend:
        lines.append("Over the last 3 months against the 3 before, " + ", ".join(trend) + ".")
    lines += ["", "This week's suggestions."]
    if not b["suggestions"]:
        lines.append("No new suggestions this week; follow your call plan.")
    for s in b["suggestions"][:3]:
        line = f"{s['rank']}. {s['physician']}" + (f", {s['account']}" if s["account"] else "") \
            + f": {s['channel']}, {s['theme']}. Why: {s['reason']}."
        if s["key_message"]:
            line += f" Key message: \"{s['key_message']}\"."
        line += f" Listen for: {s['listen_for']}."
        lines.append(line)
    more = len(b["suggestions"]) - 3
    if more > 0:
        lines.append(f"{_n(more, 'more suggestion')} {'is' if more == 1 else 'are'} in your Veeva list.")
    h = b["held"]
    lines += ["", "Why these.",
              f"They have the highest expected return of {b['candidates_in_territory']} physicians and accounts "
              f"considered in your territory; {_n(h['cadence'], 'action')} held by cadence, {h['capacity']} by "
              f"capacity and {h['consent']} by consent."]
    if b["discovery_note"]:
        lines.append(b["discovery_note"])
    return "\n".join(lines)


def grounding_check(prose: str, brief: dict) -> tuple[bool, list[str]]:
    """Every number written in the prose must appear in the structured brief."""
    allowed = set(NUMBER.findall(json.dumps(brief, default=str)))
    allowed |= {f"{float(x):g}" for x in allowed}
    missing = [n for n in NUMBER.findall(prose) if n not in allowed and f"{float(n):g}" not in allowed]
    return (not missing), missing


def rep_briefs(r: WeekResult, sug: pd.DataFrame, data_dir=None) -> pd.DataFrame:
    """One talk track per rep in a test territory."""
    con = data.connect(data_dir)
    acc = data.read_table("account_vod", data_dir).set_index("id")
    names = acc.name
    parents = acc.primary_parent_id.map(acc.name).dropna()
    terr = data.read_table("territory_vod", data_dir)
    rows = []
    for _, t in terr[(terr.pilot_arm == "test") & terr.rep_user_id.notna()].sort_values("id").iterrows():
        brief = structured_brief(r, t.rep_user_id, t, sug, con, names, parents)
        prose = template_prose(brief)
        words = prose.split()
        if len(words) > 300:          # keep it under 300 words: drop the "listen for" lines first
            prose = re.sub(r" Listen for: [^.]*\.", "", prose)
        ok, _missing = grounding_check(prose, brief)
        rows.append({"brief_id": f"RB-W{r.week:02d}-{t.rep_user_id}", "run_week": r.feats.as_of,
                     "user_id": t.rep_user_id, "role": "rep", "territory_id": t.id,
                     "structured_brief": json.dumps(brief, default=str), "prose": prose,
                     "word_count": len(prose.split()), "grounding_check_passed": ok,
                     "suggestion_ids": "|".join(s["suggestion_id"] for s in brief["suggestions"]),
                     "model_name": "template"})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------------- deliver

def deliver(r: WeekResult, data_dir=None) -> pd.DataFrame:
    """Write the week's Veeva payloads, agency file and talk tracks. Returns the open suggestions."""
    d = _run_dir(r.week, data_dir)
    sug = suggestions(r, data_dir)
    (d / "veeva_suggestions.json").write_text(json.dumps(veeva_payloads(sug), indent=1))
    agency_file(r).to_csv(d / "agency_marketing_email.csv", index=False)
    briefs = rep_briefs(r, sug, data_dir)
    old = data.read_table("rep_brief", data_dir)
    data.write_table("rep_brief", pd.concat([old.astype(object), briefs.astype(object)], ignore_index=True), data_dir)
    (d / "talk_tracks.md").write_text("\n\n---\n\n".join(
        f"## {b.user_id} ({b.territory_id}), week of {b.run_week:%d %b %Y}\n\n{b.prose}" for b in briefs.itertuples()))
    return sug.drop(columns="chance_tier")
