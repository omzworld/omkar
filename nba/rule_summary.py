"""Rule studio summary: how many rules of each type, and what they did in the latest weeks of the run.

For trigger rules (risks and opportunities): the doctors each rule picked out, how many of them it was acted on
for (sent), and how many were held by a guardrail. For guardrails and cadence rules: how many actions each one
blocked or delayed. Four weeks are returned so the screen can show the trend.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from nba import runner, spec
from nba.rules import catalogue, versions

TYPE_OF_FAMILY = {"eligibility_and_consent": "guardrail", "cadence_and_caps": "cadence", "channel_choice": "channel",
                  "content_sequence": "content", "field_events_feedback": "capacity"}
TYPES = [("risk", "Risks", "A doctor or brick is slipping: act before it costs prescriptions"),
         ("opportunity", "Opportunities", "A signal that a doctor is ready for the next step"),
         ("guardrail", "Guardrails", "Consent, compliance and approved content: block what must not go"),
         ("cadence", "Cadence and caps", "Gaps between touches and monthly limits: delay what would be too much"),
         ("channel", "Channel choice", "Which channel to prefer for a doctor"),
         ("content", "Content order", "Which theme comes next for a doctor"),
         ("capacity", "Capacity and feedback", "Rep and KAM slots, and what rep feedback changes")]
FAMILY_LABEL = {"engagement_triggers": "Engagement signals", "movicol": "Movicol", "bowel_preparations": "Bowel preparations",
                "xifaxan": "Xifaxan", "rare_disease": "Rare disease", "eligibility_and_consent": "Eligibility and consent",
                "cadence_and_caps": "Cadence and caps", "channel_choice": "Channel choice",
                "content_sequence": "Content order", "field_events_feedback": "Capacity, events and feedback"}


def rule_type(r) -> str:
    if r.trigger_type in ("risk", "opportunity"):
        return r.trigger_type
    return TYPE_OF_FAMILY.get(r.family, "guardrail")


def _week_counts(root: Path, week: int) -> pd.DataFrame:
    """Per rule for one week: doctors picked out, doctors acted on, actions held (blocked or delayed by it)."""
    d = root / "runs" / f"week_{week:02d}"
    trig = pd.read_parquet(d / "triggers.parquet", columns=["hcp_id", "rule_ids"])
    dec = pd.read_parquet(d / "decisions.parquet", columns=["hcp_id", "rule_ids", "status", "constraint_id"])
    t = trig.assign(rule=trig.rule_ids.astype(str).str.split(",")).explode("rule")
    reach = t.groupby("rule").hcp_id.nunique()
    s = dec[dec.status == "sent"]
    s = s.assign(rule=s.rule_ids.astype(str).str.split(",")).explode("rule")
    acted = s.groupby("rule").hcp_id.nunique()
    held = dec[dec.status.isin(["not_sent", "blocked"]) & dec.constraint_id.notna()].groupby("constraint_id").size()
    out = pd.DataFrame({"reach": reach, "acted": acted, "held": held}).fillna(0).astype(int)
    out.index.name = "rule"
    return out.reset_index().assign(week=week)


def summary(data_dir: Path | None = None) -> dict:
    root = Path(data_dir) if data_dir else spec.data_dir()
    done = runner.completed_weeks(data_dir)
    weeks = list(range(max(1, done - 3), done + 1)) if done else []
    counts = pd.concat([_week_counts(root, w) for w in weeks]) if weeks else pd.DataFrame(
        columns=["rule", "reach", "acted", "held", "week"])
    paused = versions.paused()
    rules = []
    for r in catalogue.load():
        c = counts[counts.rule == r.id]
        by_week = {int(w): row for w, row in zip(c.week, c.to_dict("records"))}
        trend = [int(by_week.get(w, {}).get("reach" if r.raises_triggers else "held", 0)) for w in weeks]
        last = by_week.get(weeks[-1], {}) if weeks else {}
        rules.append({"id": r.id, "family": r.family, "type": rule_type(r), "brand": r.brand,
                      "on": bool(r.enabled and r.id not in paused), "channel": r.channel, "theme": r.content_theme,
                      "reason": r.reason_template, "editable": r.raises_triggers, "custom": r.owner == "Rule studio",
                      "reach": int(last.get("reach", 0)), "acted": int(last.get("acted", 0)),
                      "held": int(last.get("held", 0)), "trend": trend})
    df = pd.DataFrame(rules)
    types = []
    for key, label, blurb in TYPES:
        g = df[df.type == key]
        on = g[g.on]
        trend = [int(sum(x[i] for x in on.trend)) for i in range(len(weeks))]
        types.append({"type": key, "label": label, "blurb": blurb, "rules_total": len(g), "rules_on": len(on),
                      "reach": int(on.reach.sum()), "acted": int(on.acted.sum()), "held": int(on.held.sum()),
                      "trend": trend, "measure": "doctors picked out" if key in ("risk", "opportunity") else "actions held"})
    families = [{"family": f, "label": FAMILY_LABEL.get(f, f.replace("_", " ")),
                 "rules": [x for x in rules if x["family"] == f]} for f in dict.fromkeys(df.family)]
    # Doctors any switched-on trigger rule picked out in the latest week (a doctor counted once).
    doctors = 0
    if weeks:
        trig = pd.read_parquet(root / "runs" / f"week_{weeks[-1]:02d}" / "triggers.parquet", columns=["hcp_id"])
        doctors = int(trig.hcp_id.nunique())
    return {"weeks": weeks, "latest_week": weeks[-1] if weeks else None, "rules_total": len(df),
            "rules_on": int(df.on.sum()), "doctors_reached": doctors, "types": types, "families": families}
