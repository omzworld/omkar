"""The data control center: every dataset the engine reads or writes, checked live against its schema.

For each table in spec/schemas/datasets.yaml: the source system, the grain, rows, file size and age, the date
range it covers, which declared fields are present, and how complete each one is. Then the joins between tables,
with the share of keys that find their match (referential integrity), and the feature table the engines read.
Everything is measured from the Parquet files on disk at the moment of asking; nothing here is hard-coded.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from nba import columns, features, runner, spec
from nba.rules import catalogue

# Joins between tables: (child table, child key, parent table, parent key, what the join means).
RELATIONS = [
    ("account_vod", "territory_id", "territory_vod", "id", "account sits in a territory"),
    ("territory_vod", "rep_user_id", "user_vod", "id", "territory's rep"),
    ("territory_vod", "kam_user_id", "user_vod", "id", "territory's key account manager"),
    ("account_vod", "onekey_id", "hcp_master_opendata", "onekey_id", "physician's OpenData record"),
    ("account_vod", "primary_parent_id", "hco_master_opendata", "hco_id", "physician's organisation"),
    ("address_vod", "account_id", "account_vod", "id", "account's address"),
    ("consent", "account_id", "account_vod", "id", "consent per channel"),
    ("hcp_stage_weekly", "account_id", "account_vod", "id", "journey stage each week"),
    ("call2_vod", "account_id", "account_vod", "id", "rep calls"),
    ("call2_vod", "user_id", "user_vod", "id", "who made the call"),
    ("sent_email_vod", "account_id", "account_vod", "id", "rep emails"),
    ("sent_email_vod", "approved_document_id", "promomats_document", "document_id", "asset emailed"),
    ("email_activity_vod", "sent_email_id", "sent_email_vod", "id", "opens and clicks"),
    ("event_attendee_vod", "account_id", "account_vod", "id", "event invitations"),
    ("agency_email", "account_id", "account_vod", "id", "marketing emails"),
    ("agency_email", "approved_document_id", "promomats_document", "document_id", "asset in the campaign"),
    ("agency_media", "account_id", "account_vod", "id", "media and portal activity"),
    ("iqvia_brick_sales", "brick_id", "account_vod", "brick_id", "sales in the account's brick"),
    ("procedure_volume", "hco_id", "hco_master_opendata", "hco_id", "endoscopy unit procedures"),
    ("rep_capacity", "user_id", "user_vod", "id", "rep slots each week"),
    ("suggestion_vod", "account_id", "account_vod", "id", "engine suggestions"),
    ("suggestion_vod", "user_id", "user_vod", "id", "suggestion's rep"),
    ("rep_brief", "user_id", "user_vod", "id", "weekly talk track"),
]
_CACHE: dict = {}


def _file(name: str, d: Path) -> Path:
    return d / f"{name}.parquet"


def _system(source: str) -> str:
    s = source.split(" (")[0]
    if s.startswith("Engine"):
        return "Engine outputs"
    for key, label in [("Veeva CRM", "Veeva CRM"), ("Events", "Veeva Events"), ("OpenData", "Veeva OpenData"),
                       ("PromoMats", "Veeva Vault PromoMats"), ("IQVIA", "IQVIA"), ("Consent", "Consent platform"),
                       ("Marketing automation", "Agency"), ("Media partner", "Agency"), ("Hospital", "Hospital and KAM records"),
                       ("field operations", "Field operations"), ("segmentation", "Brand segmentation")]:
        if key.lower() in s.lower():
            return label
    return s


def _table(name: str, decl: dict, d: Path, con) -> dict:
    f = _file(name, d)
    fields = decl.get("fields") or {}
    info = {"name": name, "source": decl.get("source", ""), "system": _system(decl.get("source", "")),
            "grain": decl.get("grain", ""), "primary_key": decl.get("primary_key", ""),
            "engine_written": str(decl.get("source", "")).startswith("Engine"), "declared_fields": len(fields)}
    if not f.exists():
        return {**info, "status": "missing", "rows": 0, "fields": []}
    meta = pq.ParquetFile(f).metadata
    actual = set(pq.read_schema(f).names)
    st = f.stat()
    info.update(rows=meta.num_rows, size_kb=round(st.st_size / 1024, 1),
                updated=datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                actual_fields=len(actual))
    present = [k for k in fields if k in actual]
    filled = {}
    if present and meta.num_rows:
        sel = ", ".join(f'count("{k}") AS "{k}"' for k in present)
        row = con.execute(f"SELECT {sel} FROM read_parquet('{f.as_posix()}')").fetchone()
        filled = {k: round(100 * v / meta.num_rows, 1) for k, v in zip(present, row)}
    out_fields = []
    for k, v in fields.items():
        typ = v if isinstance(v, str) else v.get("type", "")
        values = v.get("values") if isinstance(v, dict) else None
        out_fields.append({"name": k, "type": typ, "values": values, "present": k in actual,
                           "filled_pct": filled.get(k)})
    info["fields"] = out_fields
    info["completeness_pct"] = round(sum(filled.values()) / len(filled), 1) if filled else None
    dates = [x["name"] for x in out_fields if x["type"] in ("date", "datetime") and x["present"]]
    if dates and meta.num_rows:
        lo, hi = con.execute(f'SELECT min("{dates[0]}"), max("{dates[0]}") FROM read_parquet(\'{f.as_posix()}\')').fetchone()
        info["date_field"], info["date_from"], info["date_to"] = dates[0], str(lo)[:10], str(hi)[:10]
    missing = [x["name"] for x in out_fields if not x["present"]]
    info["missing_fields"] = missing
    info["status"] = "empty" if meta.num_rows == 0 else ("schema gap" if missing else "ok")
    return info


def _relation(rel, d: Path, con) -> dict:
    child, ck, parent, pk, label = rel
    cf, pf = _file(child, d), _file(parent, d)
    base = {"child": child, "child_key": ck, "parent": parent, "parent_key": pk, "meaning": label}
    if not (cf.exists() and pf.exists()):
        return {**base, "status": "missing"}
    cols_c, cols_p = pq.read_schema(cf).names, pq.read_schema(pf).names
    if ck not in cols_c or pk not in cols_p:
        return {**base, "status": "missing"}
    keys, matched = con.execute(f"""
        WITH c AS (SELECT DISTINCT "{ck}" AS k FROM read_parquet('{cf.as_posix()}') WHERE "{ck}" IS NOT NULL AND "{ck}" <> ''),
             p AS (SELECT DISTINCT "{pk}" AS k FROM read_parquet('{pf.as_posix()}'))
        SELECT count(*), count(p.k) FROM c LEFT JOIN p USING (k)""").fetchone()
    pct = round(100 * matched / keys, 1) if keys else None
    return {**base, "keys": keys, "matched": matched, "match_pct": pct,
            "status": "ok" if pct is not None and pct >= 99.5 else ("empty" if pct is None else "gaps")}


def _feature_table(d: Path) -> dict:
    snaps = sorted((d / "snapshots").glob("features_w*.parquet"))
    if not snaps:
        return {"weeks": 0}
    latest = snaps[-1]
    schema = pq.read_schema(latest)
    names = set(schema.names)
    groups = []
    for g, cols in columns.groups().items():
        if g in (columns.FUNCTIONS, columns.CANDIDATE):
            continue
        built = [c for c in cols if c in names]
        no_source = [c for c in built if c in set(features.NO_SOURCE_BLANK) | set(features.NO_SOURCE_FALSE)]
        groups.append({"group": g, "columns": len(cols), "built": len(built), "no_source": no_source})
    return {"weeks": len(snaps), "latest": latest.stem, "rows": pq.ParquetFile(latest).metadata.num_rows,
            "columns": len(names), "groups": groups,
            "candidate_columns": len(columns.candidate_columns()), "functions": sorted(columns.functions())}


def build(max_age_s: float = 20) -> dict:
    """The whole catalogue. Cached for a few seconds, since the screen asks for it in one go."""
    if _CACHE.get("at", 0) > time.time() - max_age_s:
        return _CACHE["value"]
    d = spec.data_dir()
    con = duckdb.connect()
    t0 = time.time()
    tables = [_table(n, decl, d, con) for n, decl in spec.datasets().items()]
    relations = [_relation(r, d, con) for r in RELATIONS]
    rules = catalogue.load()
    trig = [r for r in rules if r.raises_triggers]
    value = {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "check_seconds": None,
        "tables": tables, "relations": relations, "feature_table": _feature_table(d),
        "engine": {"weeks_run": runner.completed_weeks(), "pilot_weeks": spec.design()["clock"]["weeks_to_simulate"],
                   "run_folders": len(list((d / "runs").glob("week_*"))) if (d / "runs").exists() else 0},
        "spec": {"trigger_rules": len(trig), "trigger_rules_on": sum(r.enabled for r in trig),
                 "rules_written_in_studio": sum(r.owner == "Rule studio" for r in rules),
                 "all_rules": len(rules),
                 "constraint_tables": {n: len(spec.constraint_table(n)) for n in ("consent_rules", "country_code", "cadence", "capacity")},
                 "datasets_declared": len(spec.datasets())},
        "synthetic": True,
        "seed": spec.config().get("seed"),
    }
    value["check_seconds"] = round(time.time() - t0, 2)
    _CACHE.update(at=time.time(), value=value)
    return value
