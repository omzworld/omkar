"""The web API behind the six screens. Start it with `nba serve` (or `make demo`).

Every endpoint returns plain JSON built from the same engine functions the command line uses. When the web app
has been built (web/dist), it is served from the same address, so the demo is one process on one port.
"""
from __future__ import annotations

import json
import threading
import traceback
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from nba import author, datacatalog, features, measure, pipeline, proposals, readiness, runner, spec
from nba.rules import catalogue, engine, versions

app = FastAPI(title="Next best action engine", version="0.1")
WEB = spec.ROOT / "web" / "dist"


def out(obj):
    """Anything (DataFrames, numpy numbers, timestamps) to plain JSON-ready Python."""
    if isinstance(obj, pd.DataFrame):
        return json.loads(obj.to_json(orient="records", date_format="iso"))
    if isinstance(obj, pd.Series):
        return json.loads(obj.to_json(date_format="iso"))
    if isinstance(obj, dict):
        return {k: out(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [out(v) for v in obj]
    if hasattr(obj, "item"):                      # numpy number
        obj = obj.item()
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return None                               # blanks and infinities become null
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    return str(obj)


def _root() -> Path:
    return spec.data_dir()


# ------------------------------------------------------------------------------------------- scene 1: readiness

@app.get("/api/readiness")
def get_readiness():
    """The data audit as it stood before the pilot (the baseline copy of the data)."""
    base = _root() / "baseline"
    return out(readiness.build(base if base.exists() else None))


# ------------------------------------------------------------------------------------------- scene 2: rule studio

class Params(BaseModel):
    parameters: dict = {}
    note: str = ""
    week: int = 1


def _rule_json(r, overrides, paused):
    params = {**r.parameters, **overrides.get(r.id, {})}
    return {"id": r.id, "family": r.family, "brand": r.brand, "markets": r.markets, "trigger_type": r.trigger_type,
            "enabled": r.enabled, "paused": r.id in paused, "channel": r.channel, "content_theme": r.content_theme,
            "priority": r.priority, "condition": r.condition_template, "reason_template": r.reason_template,
            "parameters": params, "catalogue_parameters": r.parameters, "owner": r.owner,
            "version": len(versions.history().get(r.id, [])) + 1, "custom": r.owner == "Rule studio"}


@app.get("/api/rules")
def get_rules():
    overrides, paused = versions.current_overrides(), versions.paused()
    return [_rule_json(r, overrides, paused) for r in catalogue.load() if r.raises_triggers]


@app.get("/api/rules/{rule_id}")
def get_rule(rule_id: str):
    r = catalogue.by_id().get(rule_id)
    if r is None:
        raise HTTPException(404, f"No rule {rule_id}")
    return {**_rule_json(r, versions.current_overrides(), versions.paused()),
            "history": versions.history().get(rule_id, [])}


def _snapshot(week: int) -> features.Features:
    try:
        return features.load_snapshot(week)
    except FileNotFoundError:
        return features.build(week)


@app.post("/api/rules/{rule_id}/preview")
def preview_rule(rule_id: str, body: Params):
    """Who the rule picks out now, and with the new parameters (all territories, the chosen week)."""
    rule = catalogue.by_id().get(rule_id)
    if rule is None:
        raise HTTPException(404, f"No rule {rule_id}")
    feats = _snapshot(body.week)
    current = rule.with_parameters(**versions.current_overrides().get(rule_id, {}))
    try:
        changed = current.with_parameters(**body.parameters)
        changed.condition()
    except Exception as e:  # noqa: BLE001  (shown to the user as a plain message)
        raise HTTPException(400, str(e))
    t = feats.table
    names = pd.read_parquet(_root() / "account_vod.parquet", columns=["id", "name"]).set_index("id").name
    before, after = engine.fired(current, feats), engine.fired(changed, feats)

    def rows(mask):
        sel = t[mask]
        return pd.DataFrame({"hcp_id": sel.hcp_id, "name": sel.hcp_id.map(names), "market": sel.market,
                             "territory_id": sel.territory_id, "pilot_arm": sel.pilot_arm,
                             "reason": engine.reasons(changed if mask is not before else current, sel)})
    added, removed = after & ~before, before & ~after
    return {"week": body.week, "run_date": f"{feats.as_of:%d %b %Y}", "before": int(before.sum()),
            "after": int(after.sum()), "condition_before": current.condition_text,
            "condition_after": changed.condition_text, "added": out(rows(added)), "removed": out(rows(removed)),
            "after_rows": out(rows(after).head(200))}


@app.post("/api/rules/{rule_id}/save")
def save_rule(rule_id: str, body: Params):
    try:
        return versions.save(rule_id, body.parameters, body.note)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))


@app.post("/api/rules/reset")
def reset_rules():
    versions.reset()
    return {"ok": True}


# ------------------------------------------------------------------------------------------- scene 7: write a rule

class Draft(BaseModel):
    form: dict = {}
    week: int | None = None


@app.get("/api/author/options")
def author_options():
    return out(author.options())


@app.post("/api/author/check")
def author_check(body: Draft):
    return out(author.validate(body.form))


@app.post("/api/author/test")
def author_test(body: Draft):
    try:
        return out(author.quick_test(body.form, body.week))
    except Exception as e:  # noqa: BLE001  (shown to the marketer as a plain message)
        raise HTTPException(400, str(e))


@app.post("/api/author/approve")
def author_approve(body: Draft):
    try:
        return out(author.approve(body.form))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/author/remove/{rule_id}")
def author_remove(rule_id: str):
    try:
        author.remove(rule_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


# ------------------------------------------------------------------------------------------- data control center

@app.get("/api/data/catalog")
def data_catalog():
    return out(datacatalog.build())


# ------------------------------------------------------------------------------------------- scene 3: weekly run

class WeekRun(BaseModel):
    week: int = 1
    dial: float = 1.0


@app.post("/api/week")
def run_week(body: WeekRun):
    """One week of the engine for the test territories, without changing the pilot's data."""
    if not (_root() / "snapshots" / f"features_w{body.week:02d}.parquet").exists() and body.week > 1 + \
            runner.completed_weeks():
        raise HTTPException(400, f"Run the pilot to week {body.week - 1} first.")
    r = pipeline.run_week(body.week, dial=body.dial, save=False)
    s = pipeline.summary(r)
    triggers = r.triggers.groupby("rule_id").agg(triggers=("hcp_id", "size"), example=("reason", "first")).reset_index()
    sent = r.sent.sort_values("final_return", ascending=False)
    names = pd.read_parquet(_root() / "account_vod.parquet", columns=["id", "name"]).set_index("id").name
    cols = ["hcp_id", "territory_id", "final_channel", "content_theme", "asset_id", "probability_of_response",
            "chance_tier", "value_of_response", "cost_of_touch", "final_return", "rule_ids", "reason", "status",
            "not_sent_reason"]
    held = r.decisions[(r.decisions.status == "not_sent")].sort_values("expected_return", ascending=False)
    return out({"headline": s["headline"], "triggers": triggers, "constraints": s["constraints"],
                "by_channel": s["by_channel"], "not_sent": s["not_sent"], "by_rule": s["by_rule"],
                "sent": sent[cols].head(100).assign(name=lambda d: d.hcp_id.map(names)),
                "held": held[cols + ["verdict", "constraint_id", "constraint_reason"]].head(100)
                .assign(name=lambda d: d.hcp_id.map(names))})


# ------------------------------------------------------------------------------------------- scene 4: delivery

def _week_dir(week: int) -> Path:
    d = _root() / "runs" / f"week_{week:02d}"
    if not (d / "veeva_suggestions.json").exists():
        raise HTTPException(404, f"No delivery for week {week}: run the pilot to that week first.")
    return d


@app.get("/api/delivery/{week}")
def delivery_week(week: int):
    d = _week_dir(week)
    payloads = json.loads((d / "veeva_suggestions.json").read_text())
    briefs = pd.read_parquet(_root() / "rep_brief.parquet")
    briefs = briefs[pd.to_datetime(briefs.run_week) == features.as_of(week)]
    owners = pd.Series([p["OwnerId"] for p in payloads]).value_counts()
    agency = pd.read_csv(d / "agency_marketing_email.csv")
    return out({"week": week, "run_date": f"{features.as_of(week):%d %b %Y}", "payload_count": len(payloads),
                "owners": [{"user_id": u, "suggestions": int(n)} for u, n in owners.items()],
                "reps_with_briefs": briefs[["user_id", "territory_id", "word_count", "grounding_check_passed"]],
                "agency_rows": len(agency), "agency": agency.head(50)})


@app.get("/api/delivery/{week}/user/{user_id}")
def delivery_user(week: int, user_id: str):
    d = _week_dir(week)
    payloads = [p for p in json.loads((d / "veeva_suggestions.json").read_text()) if p["OwnerId"] == user_id]
    briefs = pd.read_parquet(_root() / "rep_brief.parquet")
    b = briefs[(pd.to_datetime(briefs.run_week) == features.as_of(week)) & (briefs.user_id == user_id)]
    brief = b.iloc[0] if len(b) else None
    return {"user_id": user_id, "payloads": payloads,
            "talk_track": None if brief is None else {"prose": brief.prose, "word_count": int(brief.word_count),
                                                      "grounding_check_passed": bool(brief.grounding_check_passed),
                                                      "structured": json.loads(brief.structured_brief),
                                                      "model_name": brief.model_name}}


@app.get("/api/delivery/{week}/accounts")
def delivery_accounts(week: int):
    """Key account manager view: each endoscopy unit or hospital with a suggestion, its signals and stakeholders."""
    d = _week_dir(week)
    dec = pd.read_parquet(d / "decisions.parquet")
    kam = dec[dec.status.isin(["sent", "substituted"]) & dec.final_channel.isin(["kam_visit", "kam_brief"])]
    t = features.load_snapshot(week).table
    acc = pd.read_parquet(_root() / "account_vod.parquet").set_index("id")
    out_rows = []
    for _, k in kam.sort_values("final_return", ascending=False).iterrows():
        unit = t[t.hcp_id == k.hcp_id].iloc[0]
        staff = t[(t.unit_id == k.hcp_id) & (t.account_type == "hcp")]
        staff_sent = dec[dec.hcp_id.isin(staff.hcp_id) & dec.status.isin(["sent", "substituted"])]
        msgs = k.key_messages.split("|") if isinstance(k.key_messages, str) else []
        out_rows.append({
            "account_id": k.hcp_id, "name": acc.name.get(k.hcp_id), "kam": k.kam_user_id, "action": k.final_channel,
            "theme": k.content_theme, "reason": k.reason, "expected_return": k.final_return,
            "signals": {"unit tier": unit.unit_tier, "procedures last quarter": unit.unit_colonoscopies_qtr,
                        "procedures vs prior quarter (%)": unit.unit_procedure_volume_qoq_pct,
                        "share points moved to competitors": unit.unit_competitor_share_change,
                        "inadequate preparation rate (%)": unit.inadequate_prep_rate_reported,
                        "days since KAM visit": unit.days_since_kam_visit},
            "stakeholders": [{"name": acc.name.get(s.hcp_id), "role": s.hcp_role, "stage": s.stage}
                             for _, s in staff.iterrows()][:12],
            "sequence": [f"1. {k.final_channel.replace('_', ' ')}: {str(k.content_theme).replace('_', ' ')}"] +
                        [f"{i + 2}. {acc.name.get(s.hcp_id)}: {s.final_channel.replace('_', ' ')}, "
                         f"{str(s.content_theme).replace('_', ' ')}" for i, (_, s) in enumerate(staff_sent.iterrows())],
            "key_messages": msgs})
    return out(out_rows)


# ------------------------------------------------------------------------------------------- scene 5: feedback

@app.get("/api/feedback")
def get_feedback():
    weeks = runner.completed_weeks()
    if not weeks:
        return {"weeks": 0}
    acc = proposals.acceptance_by_rule()
    s = pd.read_parquet(_root() / "suggestion_vod.parquet")
    reasons = s[s.status == "dismissed"].dismiss_reason.value_counts().rename_axis("reason").reset_index(name="count")
    by_week = s.groupby("suggested_date").agg(suggestions=("id", "size"),
                                              accepted=("status", lambda x: int((x == "accepted").sum()))).reset_index()
    by_week["acceptance_pct"] = (100 * by_week.accepted / by_week.suggestions).round(1)
    rules = {r.id: r for r in catalogue.load()}
    acc["reason_template"] = acc.rule_id.map(lambda i: rules[i].reason_template if i in rules else "")
    return out({"weeks": weeks, "by_rule": acc.sort_values("acceptance_rate"), "dismiss_reasons": reasons,
                "by_week": by_week, "proposals": proposals.proposals(), "versions": versions.history()})


@app.post("/api/feedback/proposals/{rule_id}/approve")
def approve(rule_id: str):
    try:
        return proposals.approve(rule_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


# ------------------------------------------------------------------------------------------- pilot runs

class PilotRun(BaseModel):
    weeks: int = 8
    fresh: bool = False
    dial: float = 1.0


STATE = {"running": False, "target": 0, "week": 0, "error": None}
LOCK = threading.Lock()


def _run_pilot(weeks: int, fresh: bool, dial: float):
    try:
        runner.run(weeks, dial=dial, fresh=fresh, log=lambda *_: None,
                   progress=lambda w: STATE.update(week=w))
    except Exception:  # noqa: BLE001
        STATE["error"] = traceback.format_exc(limit=3)
    finally:
        STATE["running"] = False


@app.post("/api/pilot/run")
def pilot_run(body: PilotRun):
    with LOCK:
        if STATE["running"]:
            raise HTTPException(409, "A run is already in progress.")
        done = 0 if body.fresh else runner.completed_weeks()
        STATE.update(running=True, target=body.weeks, week=done, error=None)
    threading.Thread(target=_run_pilot, args=(body.weeks, body.fresh, body.dial), daemon=True).start()
    return STATE


@app.get("/api/pilot/status")
def pilot_status():
    return {**STATE, "completed_weeks": runner.completed_weeks(), "pilot_weeks": spec.design()["clock"]["weeks_to_simulate"]}


# ------------------------------------------------------------------------------------------- scene 6: measure

@app.get("/api/measure")
def get_measure(fee: float | None = None, margin: float = 70.0, lift: float | None = None,
                sales: float | None = None, savings: bool = True):
    return out(measure.report(fee_per_quarter=fee, margin_pct=margin, lift_override_pts=lift,
                              brand_sales_per_quarter_eur=sales, count_touch_savings=savings))


@app.get("/api/assumptions")
def get_assumptions():
    return spec.assumptions()


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
