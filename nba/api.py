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

from nba import attainment, author, author_parse, data, incentive, playbook, rule_summary, datacatalog, features, measure, pipeline, plan_view, proposals, readiness, runner, spec, story, territory
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


@app.get("/api/rules/summary")
def get_rule_summary():
    return out(rule_summary.summary())


@app.get("/api/rules/{rule_id}")
def get_rule(rule_id: str):
    r = catalogue.by_id().get(rule_id)
    if r is None:
        raise HTTPException(404, f"No rule {rule_id}")
    return {**_rule_json(r, versions.current_overrides(), versions.paused()),
            "history": versions.history().get(rule_id, []),
            "playbook": playbook.generic(r.id, r.channel, r.content_theme), "example": _playbook_example(r)}


def _playbook_example(r):
    """The playbook filled in for one doctor the rule acted on (or picked out) in the latest week."""
    week = runner.completed_weeks()
    if not week or not r.raises_triggers:
        return None
    dec = pd.read_parquet(_week_dir(week) / "decisions.parquet")
    mine = dec[dec.rule_ids.astype(str).str.split(",").map(lambda x: r.id in x)]
    if mine.empty:
        return None
    sent = mine[mine.status == "sent"]
    d = (sent if len(sent) else mine).sort_values(["hcp_id", "final_channel"], na_position="last").iloc[0]
    channel = d.final_channel if isinstance(d.final_channel, str) else d.channel
    names = pd.read_parquet(_root() / "account_vod.parquet", columns=["id", "name"]).set_index("id").name
    try:
        pb = playbook.for_doctor(week, d.hcp_id, channel, d.content_theme, r.id, d.asset_id if isinstance(d.asset_id, str) else None)
    except KeyError:
        return None
    return {"week": week, "hcp_id": d.hcp_id, "name": names.get(d.hcp_id, d.hcp_id), "status": d.status,
            "reason": d.reason, "playbook": pb}


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
                             "brick_id": sel.brick_id,
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


class Sentence(BaseModel):
    text: str


@app.get("/api/author/examples")
def author_examples():
    return author_parse.EXAMPLES


@app.post("/api/author/parse")
def author_parse_text(body: Sentence):
    p = author_parse.parse(body.text)
    return out({**p, **author.validate(p["form"])})


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


# ------------------------------------------------------------------------------------------- segment & plan

@app.get("/api/plan")
def get_plan(cycle: int | None = None):
    """The cycle's segmentation, recommended allocation, rep adjustments and delivery so far."""
    return out(plan_view.summary(cycle))


@app.get("/api/plan/physicians")
def get_plan_physicians(cycle: int = 1, segment: str | None = None):
    return out(plan_view.physicians(cycle, segment))


# ------------------------------------------------------------------------------------------- doctor and rep view

@app.get("/api/territory/reps")
def territory_reps():
    return out(territory.reps())


@app.get("/api/territory/{user_id}")
def territory_page(user_id: str, week: int | None = None):
    """My territory this week: one row per doctor, joining segment, ladder, concern, plan progress and this week's action."""
    try:
        return out(territory.page(user_id, week))
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/attainment")
def get_attainment():
    """Planned against delivered contacts, by potential band and rep, test against control."""
    return out(attainment.report())


@app.get("/api/story/doctors")
def story_doctors():
    return out(story.showcase_doctors())


@app.get("/api/story/doctor/{hcp_id}")
def story_doctor(hcp_id: str):
    try:
        return out(story.doctor(hcp_id))
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/story/reps")
def story_reps():
    return out(story.showcase_reps())


@app.get("/api/story/rep/{user_id}")
def story_rep(user_id: str, week: int | None = None):
    try:
        return out(story.rep(user_id, week))
    except KeyError as e:
        raise HTTPException(404, str(e))


# ------------------------------------------------------------------------------------------- brick trends

@app.get("/api/bricks/trend")
def brick_trend(ids: str, until: str | None = None, months: int = 13):
    """Monthly Movicol units and competitor share for a few bricks, for the small trend lines beside a reason."""
    wanted = [i for i in ids.split(",") if i][:200]
    if not wanted:
        return {}
    until = pd.to_datetime(until).date().isoformat() if until else None     # accepts "09 Nov 2026" or ISO dates
    f = (_root() / "iqvia_brick_sales.parquet").as_posix()
    import duckdb
    con = duckdb.connect()
    cut = "and month < date_trunc('month', ?::date)" if until else ""
    params = [wanted] + ([until] if until else [])
    df = con.execute(f"""
        select brick_id, strftime(month, '%Y-%m') as month, round(units, 1) as units,
               round(100 * competitor_units / nullif(units + competitor_units, 0), 1) as competitor_share_pct
        from read_parquet('{f}') where product = 'Movicol' and list_contains(?, brick_id) {cut}
        qualify row_number() over (partition by brick_id order by month desc) <= {int(months)}
        order by brick_id, month""", params).df()
    return {b: out(g.drop(columns="brick_id")) for b, g in df.groupby("brick_id")}


# ------------------------------------------------------------------------------------------- data control center

@app.get("/api/data/catalog")
def data_catalog():
    return out(datacatalog.build())


@app.get("/api/data/table/{name}")
def data_table(name: str, limit: int = 50, offset: int = 0, search: str = "", sort: str = "", desc: bool = False,
               week: int | None = None):
    try:
        return out(datacatalog.preview(name, limit, offset, search, sort, desc, week))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


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
    seg = data.read_table("hcp_segment")
    seg_of = seg.sort_values("cycle").drop_duplicates("account_id", keep="last").set_index("account_id").segment \
        if len(seg) else pd.Series(dtype=object)
    r.decisions["segment_name"] = r.decisions.hcp_id.map(seg_of)
    sent = r.decisions[r.decisions.status.isin(["sent", "substituted"])].sort_values(
        ["reallocated", "final_return"], ascending=[False, False])
    names = pd.read_parquet(_root() / "account_vod.parquet", columns=["id", "name"]).set_index("id").name
    cols = ["hcp_id", "territory_id", "brick_id", "final_channel", "content_theme", "asset_id", "probability_of_response",
            "chance_tier", "value_of_response", "cost_of_touch", "final_return", "rule_ids", "reason", "status",
            "not_sent_reason", "origin", "reallocated", "segment_name"]
    held = r.decisions[(r.decisions.status == "not_sent")].sort_values("expected_return", ascending=False)
    moved = r.decisions[r.decisions.status.isin(["moved", "blocked"])].sort_values("expected_return")
    return out({"headline": s["headline"], "triggers": triggers, "constraints": s["constraints"],
                "by_channel": s["by_channel"], "not_sent": s["not_sent"], "by_rule": s["by_rule"],
                "sent": sent[cols].head(100).assign(name=lambda d: d.hcp_id.map(names)),
                "held": held[cols + ["verdict", "constraint_id", "constraint_reason"]].head(100)
                .assign(name=lambda d: d.hcp_id.map(names)),
                "moved": moved[cols].head(150).assign(name=lambda d: d.hcp_id.map(names))})


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
                                                      "model_name": brief.model_name},
            "playbooks": {} if brief is None else _suggestion_playbooks(week, user_id, json.loads(brief.structured_brief))}


@app.get("/api/incentive/{user_id}")
def get_incentive(user_id: str, week: int | None = None):
    try:
        return out(incentive.tracker(user_id, week))
    except KeyError as e:
        raise HTTPException(404, str(e))


def _suggestion_playbooks(week: int, user_id: str, structured: dict) -> dict:
    """The playbook for each suggestion in a talk track, keyed by suggestion id."""
    sug = pd.read_parquet(_root() / "suggestion_vod.parquet").set_index("id")
    dec = pd.read_parquet(_week_dir(week) / "decisions.parquet")
    dec = dec[dec.status == "sent"]
    res = {}
    for item in structured.get("suggestions", []):
        sid = item.get("suggestion_id")
        if sid not in sug.index:
            continue
        s = sug.loc[sid]
        d = dec[(dec.hcp_id == s.account_id) & (dec.final_channel == s.suggested_channel)]
        if d.empty:
            continue
        d = d.iloc[0]
        try:
            res[sid] = playbook.for_doctor(week, s.account_id, s.suggested_channel, d.content_theme, d.rule_id,
                                           d.asset_id if isinstance(d.asset_id, str) else None)
        except KeyError:
            continue
    return res


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
                sales: float | None = None, savings: bool = False):
    return out(measure.report(fee_per_quarter=fee, margin_pct=margin, lift_override_pts=lift,
                              brand_sales_per_quarter_eur=sales, count_touch_savings=savings))


@app.get("/api/assumptions")
def get_assumptions():
    return spec.assumptions()


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
