"""Synthetic data generator: writes every table in spec/schemas/datasets.yaml as Parquet.

Order: people and places -> approved content -> 24 months of history -> market signals ->
forward-looking capacity -> empty engine tables. Deterministic from the seed.
"""
from __future__ import annotations

import pickle
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from nba import data, schema, spec
from nba.synth import behaviour, content, entities, sales
from nba.synth.history import History

ENGINE_TABLES = ["suggestion_vod", "rule_draft", "ml_candidate", "rep_brief", "proposed_rule", "hcp_segment",
                 "call_plan", "segment_budget"]


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


def _account_profile(rng, design, world: dict, stage_weekly: pd.DataFrame) -> pd.DataFrame:
    """The Veeva account profile reps keep for each physician: what they care about, what holds them back, their
    position on Norgine's adoption ladders, and the external (ZS) potential. Mostly rep-entered, some from survey
    agencies; confirmed at different times, and sometimes left blank, as in real CRM data. Ladders reflect the
    physician's stage when the profile was last confirmed, so an old profile can be out of date."""
    h = world["hcp"].reset_index(drop=True)
    n = len(h)
    end = pd.Timestamp(design["clock"]["history_end"])
    sw = stage_weekly.assign(week=pd.to_datetime(stage_weekly.week))
    # Last confirmed: mostly within the last year, some much older (the profile exercise runs once or twice a year).
    age_days = np.where(rng.random(n) < 0.75, rng.integers(7, 365, n), rng.integers(365, 720, n))
    updated = (end - pd.to_timedelta(age_days, unit="D")).normalize()
    snap = pd.DataFrame({"account_id": h.id, "week": updated}).sort_values("week")
    stage = pd.merge_asof(snap, sw.sort_values("week")[["account_id", "week", "stage"]], on="week", by="account_id",
                          direction="backward").set_index("account_id").stage.reindex(h.id).fillna("curiosity").to_numpy()
    usage = pd.Series(stage).map({"curiosity": "unaware", "consideration": "aware", "experience": "occasional",
                                  "loyalty": "regular", "advocacy": "regular"}).to_numpy()
    early = np.isin(stage, ["curiosity", "consideration"])
    barrier = np.where(early, rng.choice(["low_belief", "competitor_preference", "access", "price", "none"], n, p=[.35, .3, .1, .15, .1]),
                       rng.choice(["price", "competitor_preference", "access", "none", "low_belief"], n, p=[.3, .15, .1, .4, .05]))
    belief = np.where(barrier == "low_belief", "non_believer", np.where(early, rng.choice(["neutral", "believer"], n, p=[.6, .4]), "believer"))
    pref = np.where(barrier == "competitor_preference", "competitor_preferred",
                    np.where(np.isin(stage, ["loyalty", "advocacy"]), "norgine_preferred", "no_preference"))
    competitor = pd.Series(h.brand).map({"Movicol": ["generic macrogol", "lactulose", "stimulant laxative"],
                                         "Plenvu_Moviprep": ["sodium picosulfate preparation", "high-volume PEG preparation"],
                                         "Xifaxan": ["lactulose alone", "other antibiotic"]})
    competitor = [rng.choice(opts) if isinstance(opts, list) else None for opts in competitor]
    tier = h.tier.to_numpy()
    zs = np.where(tier == "A", rng.choice(["high", "medium"], n, p=[.8, .2]),
                  np.where(tier == "B", rng.choice(["high", "medium", "low"], n, p=[.15, .7, .15]), rng.choice(["medium", "low"], n, p=[.2, .8])))
    df = pd.DataFrame({
        "account_id": h.id, "message_segment": rng.choice(["patient_focus", "pricing", "product_belief", "efficacy", "safety"], n, p=[.25, .15, .2, .3, .1]),
        "barrier": barrier, "competitor": competitor, "sentiment": rng.choice(["positive", "neutral", "negative"], n, p=[.35, .45, .2]),
        "influence": np.where(h.expert_status.eq("key_people").to_numpy(), "high", rng.choice(["medium", "low"], n, p=[.35, .65])),
        "plan_member": np.isin(tier, ["A", "B"]) | (rng.random(n) < 0.1), "decision_maker": h.hcp_role.isin(["unit_lead", "pharmacist_hospital"]).to_numpy(),
        "zs_potential": zs, "belief_ladder": belief, "preference_ladder": pref, "usage_ladder": usage,
        "last_updated": updated.date, "source": rng.choice(["rep", "survey"], n, p=[.8, .2])})
    # Reps do not fill every field: leave about 15% of the attitudinal fields blank.
    for col in ["message_segment", "barrier", "competitor", "sentiment", "belief_ladder", "preference_ladder"]:
        df.loc[rng.random(n) < 0.15, col] = None
    return df


def _rep_plan_input(rng, design, world: dict) -> pd.DataFrame:
    """Reps' adjustments to the cycle plan, as they would enter them in the CRM before each cycle (about 4% of
    physicians each cycle). Two cycles: the pilot's first and second quarter."""
    h = world["hcp"]
    terr = world["territories"].set_index("id").rep_user_id
    start = pd.Timestamp(design["clock"]["pilot_start"])
    kinds = {"must_see": ("Key opinion leader for the area; wants a visit every month", 0.35),
             "no_access": ("Practice does not see reps; keep to approved email", 0.30),
             "more_digital": ("Asked for information by email rather than visits", 0.25),
             "left_practice": ("Has left the practice; remove from the plan", 0.10)}
    names, probs = list(kinds), np.array([v[1] for v in kinds.values()])
    rows = []
    for cycle in range(2):
        pick = rng.random(len(h)) < 0.04
        sel = h[pick & h.territory_id.notna().to_numpy()]
        adj = rng.choice(names, len(sel), p=probs / probs.sum())
        rows.append(pd.DataFrame({"account_id": sel.id.to_numpy(), "user_id": sel.territory_id.map(terr).to_numpy(),
                                  "cycle_start": (start + pd.Timedelta(weeks=13 * cycle)).date(),
                                  "adjustment": adj, "reason": [kinds[a][0] for a in adj]}))
    return pd.concat(rows, ignore_index=True)


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
    # Competitor campaigns over the history and the pilot (hidden from the engine), from their own random stream.
    clock = design["clock"]
    n_weeks = (pd.Timestamp(clock["history_end"]) - pd.Timestamp(clock["history_start"])).days // 7 \
        + clock["weeks_to_simulate"] + 8
    world["pushes"] = behaviour.competitor_pushes(np.random.default_rng([seed, 101]), design, world["bricks"], n_weeks)
    docs = content.documents(rng, design)
    log("Simulating 24 months of today's multi-channel plan ...")
    sim = History(rng, design, world, docs)
    hist = sim.run()
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
    out["rep_plan_input"] = _rep_plan_input(np.random.default_rng([seed, 202]), design, world)
    out["account_profile_vod"] = _account_profile(np.random.default_rng([seed, 303]), design, world, hist["hcp_stage_weekly"])
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
    data.write_hidden("competitor_push", world["pushes"], data_dir)
    # The simulator's state at the end of the history, so the pilot (nba.feedback) carries on from it.
    sim.clear_rows()
    root = Path(data_dir) if data_dir else spec.data_dir()
    with open(root / data.HIDDEN / "simulator.pkl", "wb") as f:
        pickle.dump(sim, f)
    # A copy of every table as generated, so each pilot run (nba run) starts from the same place.
    base = root / "baseline"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir()
    for p in root.glob("*.parquet"):
        shutil.copy2(p, base / p.name)
    (base / data.HIDDEN).mkdir()
    shutil.copy2(root / data.HIDDEN / "simulator.pkl", base / data.HIDDEN / "simulator.pkl")
    for sub in ("runs", "snapshots"):           # outputs of earlier runs no longer match the new data
        shutil.rmtree(root / sub, ignore_errors=True)
    return {name: len(df) for name, df in out.items()}
