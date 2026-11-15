"""Writing a new rule in the rule studio: a guided form, validation, the quick impact test, and approval.

The marketer fills a form (brand, markets, conditions picked from the feature table's columns, the action and
the reason). `build` turns the form into a rule record in the catalogue's own format, with every number held as a
named parameter so it can be changed later like any catalogue rule. `validate` runs the catalogue linter on it and
lists what is still missing. `quick_test` runs it on a real week's feature snapshot, through the constraints
engine and the optimiser, without saving anything. `approve` gives it the next free rule id and saves it to
data/custom_rules.json; the catalogue loader adds approved rules to every later run.

Plain-language parsing of a typed sentence (author.parse in the build brief) needs a language model key; until one
is set the form is the way in, and the marketer still submits a validated form, never free text.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nba import columns, data, features, pipeline, runner, spec
from nba.rules import catalogue, engine
from nba.rules.catalogue import Rule

# Operators the form offers, as (label, condition operator, parameter suffix).
NUMBER_OPS = {">=": ("at least", "min"), "<=": ("at most", "max"), ">": ("more than", "above"),
              "<": ("less than", "below"), "==": ("exactly", "value")}
TEXT_OPS = {"==": "is", "!=": "is not", "in": "is one of"}
NO_SOURCE = set(features.NO_SOURCE_FALSE) | set(features.NO_SOURCE_BLANK)
SKIP = {"hcp_id", "week", "run_week", "as_of"} | columns.PER_RULE
TIMINGS = ["this_week", "within_10_working_days", "next_month"]
EXTRA_CHANNELS = ["next_best", "kam_visit"]


# ------------------------------------------------------------------------------------------- storage

def _path(data_dir: Path | None = None) -> Path:
    return (Path(data_dir) if data_dir else spec.data_dir()) / "custom_rules.json"


def custom_records(data_dir: Path | None = None) -> list[dict]:
    p = _path(data_dir)
    return json.loads(p.read_text()) if p.exists() else []


def custom_ids(data_dir: Path | None = None) -> set[str]:
    return {r["id"] for r in custom_records(data_dir)}


def remove(rule_id: str, data_dir: Path | None = None) -> None:
    recs = [r for r in custom_records(data_dir) if r["id"] != rule_id]
    if len(recs) == len(custom_records(data_dir)):
        raise KeyError(f"{rule_id} is not a rule written in the rule studio")
    _path(data_dir).write_text(json.dumps(recs, indent=1))


# ------------------------------------------------------------------------------------------- form options

def _latest_snapshot() -> tuple[int, pd.DataFrame]:
    week = max(runner.completed_weeks(), 1)
    try:
        feats = features.load_snapshot(week)
    except FileNotFoundError:
        feats = features.build(week)
    return week, feats.table


def options() -> dict:
    """Everything the form offers: brands, markets, channels, themes, and every column a condition may use,
    with its type, values seen this week, and whether there is data for it yet."""
    cat = spec.catalogue()
    week, t = _latest_snapshot()
    allowed = columns.allowed_values()
    group_of = {c: g for g, names in columns.groups().items() for c in names}
    cols = []
    for name in columns.account_columns():
        if name in SKIP or name not in t.columns:
            continue
        s = t[name]
        blank = float(s.isna().mean())
        no_data = name in NO_SOURCE or blank == 1.0 or (s.dtype == bool and name in features.NO_SOURCE_FALSE)
        if pd.api.types.is_bool_dtype(s) or str(s.dtype) == "boolean":
            kind, info = "yes_no", {"share_yes": round(float(s.fillna(False).astype(bool).mean()) * 100, 1)}
        elif pd.api.types.is_numeric_dtype(s):
            v = pd.to_numeric(s, errors="coerce").dropna()
            kind = "number"
            info = {"min": _num(v.min()), "median": _num(v.median()), "max": _num(v.max())} if len(v) else {}
        elif pd.api.types.is_datetime64_any_dtype(s):
            continue
        else:
            kind = "text"
            vals = allowed.get(name) or sorted(s.dropna().astype(str).unique().tolist())
            info = {"values": vals[:40]}
        cols.append({"name": name, "label": name.replace("_", " "), "group": group_of.get(name, ""),
                     "kind": kind, "blank_pct": round(blank * 100, 1), "no_data": bool(no_data), **info})
    docs = data.read_table("promomats_document")
    return {
        "week": week,
        "brands": [b for b in cat["brand_codes"] if b != "Rare_disease"],
        "markets": cat["markets"],
        "families": sorted({r.family for r in catalogue.load() if r.raises_triggers}),
        "channels": sorted(set(docs.channel) - {"direct_mail"}) + EXTRA_CHANNELS,
        "themes": sorted(set(docs.content_theme)) + ["next_theme"],
        "timings": TIMINGS,
        "number_ops": [{"op": k, "label": v[0]} for k, v in NUMBER_OPS.items()],
        "text_ops": [{"op": k, "label": v} for k, v in TEXT_OPS.items()],
        "columns": cols,
        "next_id": next_id(),
    }


def _num(x):
    x = float(x)
    return int(x) if x.is_integer() else round(x, 2)


# ------------------------------------------------------------------------------------------- form -> rule record

def _param_name(column: str, suffix: str, taken: set) -> str:
    name, n = f"{column}_{suffix}", 2
    while name in taken:
        name, n = f"{column}_{suffix}{n}", n + 1
    taken.add(name)
    return name


def build(form: dict) -> dict:
    """The form as a rule record in the catalogue's format, plus the missing fields and the condition in words."""
    params, taken, parts, words, missing = {}, set(), [], [], []
    for c in form.get("conditions") or []:
        col, op, val = c.get("column"), c.get("op"), c.get("value")
        if not col:
            continue
        kind = c.get("kind")
        if kind == "theme":                                   # theme_received('x') == True/False
            if not val:
                missing.append(f"the theme for 'has received a theme'")
                continue
            yes = op != "no"
            parts.append(f"theme_received('{val}') == {yes}")
            words.append(f"{'has' if yes else 'has not'} received {str(val).replace('_', ' ')}")
        elif kind == "yes_no":
            yes = op != "no"
            parts.append(f"{col} == {yes}")
            words.append(f"{col.replace('_', ' ')} is {'yes' if yes else 'no'}")
        elif kind == "number":
            if val in (None, "") or op not in NUMBER_OPS:
                missing.append(f"a number for '{col.replace('_', ' ')}'")
                continue
            p = _param_name(col, NUMBER_OPS[op][1], taken)
            params[p] = _num(float(val))
            parts.append(f"{col} {op} {{{p}}}")
            words.append(f"{col.replace('_', ' ')} {NUMBER_OPS[op][0]} {params[p]}")
        else:                                                 # text
            if op == "in":
                vals = [v for v in (val or []) if v] if isinstance(val, list) else [v.strip() for v in str(val or "").split(",") if v.strip()]
                if not vals:
                    missing.append(f"at least one value for '{col.replace('_', ' ')}'")
                    continue
                parts.append(f"{col} in [{', '.join(repr(v) for v in vals)}]")
                words.append(f"{col.replace('_', ' ')} is one of {', '.join(v.replace('_', ' ') for v in vals)}")
            else:
                if not val:
                    missing.append(f"a value for '{col.replace('_', ' ')}'")
                    continue
                op = "!=" if op == "!=" else "=="
                parts.append(f"{col} {op} {val!r}")
                words.append(f"{col.replace('_', ' ')} {TEXT_OPS[op]} {str(val).replace('_', ' ')}")
    if not parts:
        missing.append("at least one condition")
    for key, label in [("brand", "brand"), ("trigger_type", "risk or opportunity"), ("channel", "action channel"),
                       ("content_theme", "content theme"), ("reason_template", "the reason the rep sees")]:
        if not str(form.get(key) or "").strip():
            missing.append(label)
    if not form.get("markets"):
        missing.append("market")
    record = {
        "id": form.get("id") or "NEW", "family": form.get("family") or _default_family(form.get("brand")),
        "engine": "rules", "brand": form.get("brand") or "", "markets": list(form.get("markets") or []),
        "trigger_type": form.get("trigger_type") or "", "enabled_at_launch": True,
        "condition": " and ".join(parts) or "False",
        "action": {"channel": form.get("channel") or "", "content_theme": form.get("content_theme") or "",
                   "timing": form.get("timing") or "this_week"},
        "priority": int(form.get("priority") or 60), "reason_template": (form.get("reason_template") or "").strip(),
        "parameters": params, "owner": form.get("owner") or "Rule studio", "notes": form.get("note") or "",
    }
    return {"record": record, "missing": missing, "condition_words": " and ".join(words)}


def _default_family(brand: str | None) -> str:
    return {"Movicol": "movicol", "Plenvu_Moviprep": "bowel_preparations", "Xifaxan": "xifaxan"}.get(brand or "", "engagement_triggers")


def validate(form: dict) -> dict:
    """The record, what is missing, and every problem the catalogue linter finds."""
    b = build(form)
    problems = []
    if len(b["record"]["reason_template"]) > 140:
        problems.append("The reason is longer than 140 characters; reps see it on a phone.")
    if not b["missing"] or b["record"]["condition"] != "False":
        try:
            rule = Rule.from_record(b["record"])
            problems += [p.split(": ", 1)[-1] for p in catalogue.lint([rule])
                         if not (b["missing"] and ("unknown brand" in p or "unknown action" in p))]
        except Exception as e:  # noqa: BLE001  (shown to the marketer as a plain message)
            problems.append(str(e))
    return {**b, "problems": problems, "ready": not b["missing"] and not problems}


# ------------------------------------------------------------------------------------------- quick impact test

def quick_test(form: dict, week: int | None = None) -> dict:
    """Run the draft on a real week: who it matches, what the constraints engine does with it, and how many the
    optimiser would send next to every other rule. Nothing is saved."""
    v = validate(form)
    if not v["ready"]:
        return {**v, "test": None}
    week = week or max(runner.completed_weeks(), 1)
    try:
        feats = features.load_snapshot(week)
    except FileNotFoundError:
        feats = features.build(week)
    rule = Rule.from_record(v["record"])
    t = feats.table
    hit = engine.fired(rule, feats)
    rows = t[hit]
    terr = data.read_table("territory_vod").set_index("id")
    names = data.read_table("account_vod").set_index("id").name
    reps = rows.territory_id.map(terr.rep_user_id).dropna()
    # Triggers from every rule this week, the draft included, for the overlap and the full pipeline.
    all_trig = engine.raise_triggers(feats, extra=[rule])
    mine = all_trig[all_trig.rule_id == rule.id]
    others = all_trig[all_trig.rule_id != rule.id]
    overlap = int(mine.hcp_id.isin(others.hcp_id).sum())
    verdicts = {"allowed": 0, "delayed": 0, "blocked": 0}
    by_constraint = []
    sent = 0
    if not mine.empty:
        from nba import candidates, constraints
        c = constraints.evaluate(candidates.build(mine, feats), feats, {})
        verdicts.update(c.verdict.value_counts().to_dict())
        held = c[c.verdict != "allowed"]
        if not held.empty:
            by_constraint = (held.groupby(["verdict", "constraint_id"]).agg(
                candidates=("candidate_id", "size"), example=("constraint_reason", "first"))
                .reset_index().sort_values("candidates", ascending=False).to_dict("records"))
        r = pipeline.run_week(week, dial=1.0, save=False, extra_rules=[rule])
        sent = int((r.sent.rule_id == rule.id).sum())
    sample = rows.head(60)
    return {**v, "test": {
        "week": week, "run_date": f"{feats.as_of:%d %b %Y}",
        "matched": int(hit.sum()), "matched_test_arm": int((rows.pilot_arm == "test").sum()),
        "by_market": rows.market.value_counts().to_dict(), "territories": int(rows.territory_id.nunique()),
        "reps": int(reps.nunique()), "verdicts": {k: int(n) for k, n in verdicts.items()},
        "by_constraint": by_constraint, "would_send_test_arm": sent, "overlap_other_rules": overlap,
        "sample": [{"hcp_id": h, "name": names.get(h, ""), "market": m, "territory_id": tr, "brick_id": bk,
                    "pilot_arm": a, "reason": rs}
                   for h, m, tr, bk, a, rs in zip(sample.hcp_id, sample.market, sample.territory_id, sample.brick_id,
                                                  sample.pilot_arm, engine.reasons(rule, sample))],
        "note": f"Tested on the week of {feats.as_of:%d %b %Y}. A rule that depends on a monthly signal may show "
                "few matches in a quiet week."}}


# ------------------------------------------------------------------------------------------- approval

def next_id(data_dir: Path | None = None) -> str:
    nums = [int(m.group(1)) for r in catalogue.load() if (m := re.fullmatch(r"R(\d+)", r.id))]
    return f"R{max(nums, default=0) + 1:03d}"


def approve(form: dict, data_dir: Path | None = None) -> dict:
    v = validate(form)
    if not v["ready"]:
        raise ValueError("The rule is not ready: " + "; ".join(v["missing"] + v["problems"]))
    rec = {**v["record"], "id": next_id(data_dir),
           "approved_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
           "approval_note": form.get("note") or ""}
    recs = custom_records(data_dir) + [rec]
    _path(data_dir).write_text(json.dumps(recs, indent=1))
    return rec
