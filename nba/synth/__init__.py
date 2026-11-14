"""Synthetic data generator: writes every table in spec/schemas/datasets.yaml as Parquet.

Order: people and places -> approved content -> 24 months of history -> market signals ->
forward-looking capacity -> empty engine tables. Deterministic from the seed.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from nba import data, schema, spec
from nba.synth import content, entities, sales
from nba.synth.history import History

ENGINE_TABLES = ["suggestion_vod", "rule_draft", "ml_candidate", "rep_brief", "proposed_rule"]


def _account_tables(world: dict) -> dict:
    h, hcos = world["hcp"], world["hcos"]
    hcp_accounts = pd.DataFrame({
        "id": h.id, "name": h.name, "account_type": "hcp", "hcp_type": h.hcp_type, "specialty_1_vod": h.specialty,
        "hcp_role": h.hcp_role, "primary_parent_id": h.primary_parent_id, "territory_id": h.territory_id,
        "brick_id": h.brick_id, "market": h.market, "language": h.language, "onekey_id": h.onekey_id,
        "status": h.status})
    terr = world["bricks"].set_index("brick_id").territory_id
    lang = {m: c["language"] for m, c in spec.design()["markets"].items()}
    hco_accounts = pd.DataFrame({
        "id": hcos.hco_id, "name": hcos.name, "account_type": hcos.hco_type, "territory_id": hcos.brick_id.map(terr),
        "brick_id": hcos.brick_id, "market": hcos.market, "language": hcos.market.map(lang), "status": "active"})
    account = pd.concat([hcp_accounts, hco_accounts], ignore_index=True)

    practice_type = np.where(h.parent_type == "practice", "primary_care", "hospital")
    master = pd.DataFrame({
        "onekey_id": h.onekey_id, "specialty": h.specialty, "practice_type": practice_type,
        "practice_size": h.practice_size, "year_of_birth": h.year_of_birth, "no_promo_flag": h.no_promo_flag,
        "prescriber": h.prescriber, "paediatric_prescriber": h.paediatric_prescriber,
        "care_home_prescriber": h.care_home_prescriber, "expert_status": h.expert_status})
    hco_master = hcos[["hco_id", "name", "hco_type", "market", "brick_id", "liver_unit_flag", "unit_tier"]]
    return {"account_vod": account, "hcp_master_opendata": master, "hco_master_opendata": hco_master}


def _addresses(rng, account: pd.DataFrame, world: dict) -> pd.DataFrame:
    b = world["bricks"].set_index("brick_id")
    towns = pd.concat([world["hcp"].set_index("id").town, world["hcos"].set_index("hco_id").town])
    n = len(account)
    uk = account.market == "UK"
    postcode = np.where(uk, [f"{chr(65 + a)}{chr(65 + c)}{d} {e}{chr(65 + f)}{chr(65 + g)}"
                             for a, c, d, e, f, g in rng.integers(0, 10, (n, 6))],
                        [f"{x:05d}" for x in rng.integers(10000, 99999, n)])
    return pd.DataFrame({"id": "ADR-" + account.id, "account_id": account.id, "postcode": postcode,
                         "city": account.id.map(towns), "brick_id": account.brick_id,
                         "rural_flag": account.brick_id.map(b.rural).astype(bool),
                         "postal_address_verified": rng.random(n) < 0.92, "primary": True})


def _rep_capacity(rng, design, users: pd.DataFrame) -> pd.DataFrame:
    """Open slots per field user for each pilot week (what is left after their existing call plan)."""
    start = pd.Timestamp(design["clock"]["pilot_start"])
    field = users[users.role.isin(["rep", "kam"])].reset_index(drop=True)
    weeks = [start + pd.Timedelta(weeks=k) for k in range(design["clock"]["weeks_to_simulate"])]
    n = len(field) * len(weeks)
    role = np.repeat(field.role.to_numpy(), len(weeks))
    on_leave = rng.random(n) < 0.04
    visits = np.where(role == "rep", rng.normal(10, 3, n), rng.normal(5, 1, n))
    emails = np.where(role == "rep", rng.normal(30, 5, n), rng.normal(8, 2, n))
    return pd.DataFrame({"user_id": np.repeat(field.id.to_numpy(), len(weeks)), "week": np.tile(weeks, len(field)),
                         "visit_slots_open": np.where(on_leave, 0, np.clip(visits.round(), 1, 25)).astype(int),
                         "email_slots_open": np.where(on_leave, 0, np.clip(emails.round(), 0, 40)).astype(int),
                         "on_leave": on_leave})


def generate(seed: int | None = None, scale: float = 1.0, data_dir: Path | None = None, log=print) -> dict:
    """Generate everything and write it. Returns {table: row count}."""
    design = spec.design()
    seed = design["seed"] if seed is None else seed
    rng = np.random.default_rng(seed)

    log("Building physicians, organisations, territories and consent ...")
    world = entities.build(rng, design, scale)
    docs = content.documents(rng, design)
    log("Simulating 24 months of today's multi-channel plan ...")
    hist = History(rng, design, world, docs).run()
    log("Building brick sales and procedure volumes ...")
    out = _account_tables(world)
    out["address_vod"] = _addresses(rng, out["account_vod"], world)
    out["territory_vod"] = world["territories"]
    out["user_vod"] = world["users"]
    consent = world["consent"]
    email_channels = ["marketing_email", "rep_email", "webinar"]
    withdrawn = consent.account_id.isin(hist["unsubscribed"]) & consent.channel.isin(email_channels) \
        & (consent.status == "granted")
    consent.loc[withdrawn, "status"] = "withdrawn"
    out["consent"] = consent
    out["promomats_document"] = docs
    out["iqvia_channel_preference"] = content.channel_preference(rng, design)
    for k in ["call2_vod", "sent_email_vod", "email_activity_vod", "agency_email", "agency_media",
              "event_attendee_vod", "hcp_stage_weekly"]:
        out[k] = hist[k]
    out["iqvia_brick_sales"] = sales.brick_sales(rng, design, world, hist["hcp_stage_weekly"])
    out["procedure_volume"] = sales.procedure_volume(rng, design, world, hist["hcp_stage_weekly"])
    out["rep_capacity"] = _rep_capacity(rng, design, world["users"])
    for t in ENGINE_TABLES:
        out[t] = schema.empty(t)
    out["feature_snapshot"] = pd.DataFrame({"account_id": pd.Series(dtype="string"),
                                            "run_week": pd.Series(dtype="datetime64[s]")})

    missing = set(spec.datasets()) - set(out)
    if missing:
        raise RuntimeError(f"Generator does not produce: {sorted(missing)}")
    log("Writing Parquet tables ...")
    for name, df in out.items():
        data.write_table(name, df, data_dir)
    # Simulator-only truth. The engine never reads this folder.
    data.write_hidden("hcp_cluster", world["hcp"][["id", "cluster"]].rename(columns={"id": "account_id"}), data_dir)
    return {name: len(df) for name, df in out.items()}
