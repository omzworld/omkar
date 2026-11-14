"""People and places: bricks, territories, users, physicians and organisations, addresses, consent.

Returns the public Veeva-shaped tables plus an internal `hcp` frame (one row per physician with
tier, brand, hidden cluster and starting stage) that the history simulation uses.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nba import spec
from nba.segments import assign_tier, specialty_weight

HCP_TYPE = {"gp": "physician", "gastroenterology": "physician", "hepatology": "physician",
            "paediatrics": "physician", "internal_medicine": "physician",
            "endoscopy_nurse": "nurse", "pharmacist_hospital": "pharmacist"}
BRAND = {"gp": "Movicol", "paediatrics": "Movicol", "internal_medicine": "Movicol",
         "gastroenterology": "Plenvu_Moviprep", "endoscopy_nurse": "Plenvu_Moviprep",
         "pharmacist_hospital": "Plenvu_Moviprep", "hepatology": "Xifaxan"}
# Where each specialty works: (parent type, probability), remaining probability goes to the second option.
PARENT = {"gp": ("practice", 1.0, None), "paediatrics": ("practice", 0.6, "hospital"),
          "internal_medicine": ("practice", 0.6, "hospital"), "gastroenterology": ("endoscopy_unit", 0.6, "hospital"),
          "endoscopy_nurse": ("endoscopy_unit", 1.0, None), "hepatology": ("hospital", 1.0, None),
          "pharmacist_hospital": ("hospital", 1.0, None)}
REGIONS = {"UK": ["London", "South East", "South West", "Midlands", "East Anglia", "North West", "North East",
                  "Yorkshire", "Scotland", "Wales"],
           "DE": ["Nord", "Ost", "West", "Mitte", "Bayern", "Baden"]}
TOWNS = {"UK": ["Ashford", "Bolton", "Carlisle", "Derby", "Exeter", "Falkirk", "Gloucester", "Harrogate", "Ipswich",
                "Kendal", "Leeds", "Luton", "Norwich", "Oldham", "Preston", "Reading", "Salford", "Swansea",
                "Taunton", "Wigan", "York", "Bath", "Crewe", "Dundee"],
         "DE": ["Aachen", "Bamberg", "Celle", "Dresden", "Erfurt", "Fulda", "Giessen", "Hagen", "Jena", "Kassel",
                "Lübeck", "Mainz", "Münster", "Neuss", "Passau", "Regensburg", "Siegen", "Trier", "Ulm", "Wuppertal"]}
SURNAMES = {"UK": ["Ahmed", "Baker", "Clarke", "Davies", "Evans", "Fraser", "Green", "Hughes", "Iqbal", "Jones",
                   "Khan", "Lewis", "Morgan", "Nolan", "Okafor", "Patel", "Quinn", "Roberts", "Shah", "Taylor",
                   "Walsh", "Wright", "Young", "Singh", "Murphy", "Lind"],
            "DE": ["Bauer", "Becker", "Fischer", "Hoffmann", "Klein", "Koch", "Krüger", "Lange", "Meyer", "Müller",
                   "Neumann", "Richter", "Schmidt", "Schneider", "Schulz", "Wagner", "Weber", "Wolf", "Yilmaz", "Zimmer"]}
CONSENT_CHANNELS = ["marketing_email", "rep_email", "webinar", "remote_call", "paid_media", "portal"]


def _scaled(n: int, scale: float, minimum: int = 1) -> int:
    return max(minimum, round(n * scale))


def _bricks(rng, design, scale) -> pd.DataFrame:
    rows = []
    for m, n in design["brick_sales"]["bricks_per_market"].items():
        n_terr = _scaled(design["markets"][m]["territories"], scale, 2)
        n = max(n_terr, _scaled(n, scale))
        size = rng.lognormal(0, 0.5, n)
        terr = rng.permutation(np.arange(n) % n_terr)
        rural = rng.random(n) < 0.25
        for i in range(n):
            rows.append(dict(brick_id=f"{m}-B{i + 1:03d}", market=m, territory_id=f"{m}-T{terr[i] + 1:02d}",
                             size=size[i], rural=bool(rural[i])))
    b = pd.DataFrame(rows)
    b["potential_index"] = 100 * b["size"] / b.groupby("market")["size"].transform("mean")
    return b


def _territories_and_users(rng, design, scale):
    terr, users = [], []
    for m, cfg in design["markets"].items():
        n_terr, n_kam = _scaled(cfg["territories"], scale, 2), _scaled(cfg["kams"], scale)
        regions = REGIONS[m]
        vacant = rng.random(n_terr) < 0.03
        for k in range(n_kam):
            users.append(dict(id=f"{m}-KAM{k + 1:02d}", role="kam", market=m, weekly_visit_slots=6, weekly_email_slots=10))
        for i in range(n_terr):
            tid, rep = f"{m}-T{i + 1:02d}", None
            if not vacant[i]:
                rep = f"{m}-REP{i + 1:02d}"
                users.append(dict(id=rep, role="rep", market=m, weekly_visit_slots=25, weekly_email_slots=40))
            terr.append(dict(id=tid, name=f"{regions[i % len(regions)]} {i // len(regions) + 1:02d}", market=m,
                             rep_user_id=rep, kam_user_id=f"{m}-KAM{i % n_kam + 1:02d}", vacant=bool(vacant[i])))
        for k in range(_scaled(2, scale)):
            users.append(dict(id=f"{m}-MSL{k + 1:02d}", role="msl", market=m, weekly_visit_slots=6, weekly_email_slots=10))
        users.append(dict(id=f"{m}-MGR01", role="manager", market=m, weekly_visit_slots=0, weekly_email_slots=0))
    return pd.DataFrame(terr), pd.DataFrame(users)


def _hcos(rng, design, bricks, scale, n_practices: dict) -> pd.DataFrame:
    rows = []
    kinds = [("endoscopy_unit", "endoscopy_units", "EU"), ("hospital", "hospitals", "HOS"),
             ("pharmacy", "pharmacies", "PH"), ("practice", None, "PR")]
    for m, cfg in design["markets"].items():
        b = bricks[bricks.market == m]
        p = (b["size"] / b["size"].sum()).to_numpy()
        towns = TOWNS[m]
        for kind, key, code in kinds:
            n = n_practices[m] if key is None else _scaled(cfg[key], scale)
            brick = rng.choice(b["brick_id"].to_numpy(), n, p=p)
            size = {"endoscopy_unit": rng.integers(8, 60, n), "hospital": rng.integers(40, 400, n),
                    "pharmacy": rng.integers(2, 8, n), "practice": rng.integers(3, 12, n)}[kind]
            for i in range(n):
                town = towns[rng.integers(len(towns))]
                label = {"endoscopy_unit": f"{town} Endoscopy Unit", "hospital": f"{town} General Hospital",
                         "pharmacy": f"{town} Pharmacy", "practice": f"{town} Medical Practice"}[kind]
                rows.append(dict(hco_id=f"{m}-{code}{i + 1:03d}", name=f"{label} {i + 1}", hco_type=kind, market=m,
                                 brick_id=brick[i], size=int(size[i]), town=town,
                                 liver_unit_flag=bool(kind == "hospital" and rng.random() < 0.3)))
    h = pd.DataFrame(rows)
    h["unit_tier"] = assign_tier(h.assign(score=h["size"]), "score", group_cols=["market", "hco_type"])
    return h


def _hcps(rng, design, bricks, scale):
    """Physicians and other HCPs (before parents are attached)."""
    mix = design["specialty_mix"]
    names, probs = list(mix), np.array(list(mix.values()), dtype=float)
    clusters = design["clusters"]
    cl_names, cl_p = list(clusters), np.array([c["share"] for c in clusters.values()])
    frames = []
    for m, cfg in design["markets"].items():
        n = _scaled(cfg["hcps"], scale, 20)
        df = pd.DataFrame({"market": m, "specialty": rng.choice(names, n, p=probs / probs.sum()),
                           "cluster": rng.choice(cl_names, n, p=cl_p / cl_p.sum())})
        df["id"] = [f"{m}-H{i + 1:05d}" for i in range(n)]
        frames.append(df)
    h = pd.concat(frames, ignore_index=True)
    h["hcp_type"] = h["specialty"].map(HCP_TYPE)
    h["brand"] = h["specialty"].map(BRAND)
    n = len(h)
    role = np.where(h.hcp_type == "nurse", "endoscopy_nurse",
                    np.where(h.hcp_type == "pharmacist", "pharmacist_hospital", "prescriber"))
    role = np.where((h.specialty == "gastroenterology") & (rng.random(n) < 0.08), "unit_lead", role)
    role = np.where((h.hcp_type == "physician") & (rng.random(n) < 0.02), "medical_only_contact", role)
    h["hcp_role"] = role
    first, second = zip(*[(PARENT[s][0], PARENT[s][2] or PARENT[s][0]) for s in h.specialty])
    keep_first = rng.random(n) < h.specialty.map(lambda s: PARENT[s][1]).to_numpy()
    h["parent_type"] = np.where(keep_first, first, second)
    return h


def _attach_parents(rng, h: pd.DataFrame, hcos: pd.DataFrame) -> pd.DataFrame:
    parent = np.empty(len(h), dtype=object)
    for (m, kind), idx in h.groupby(["market", "parent_type"]).groups.items():
        pool = hcos[(hcos.market == m) & (hcos.hco_type == kind)]
        sub = h.loc[idx]
        choices = np.empty(len(sub), dtype=object)
        if kind == "hospital":  # hepatologists work in liver-unit hospitals where there is one
            liver = pool[pool.liver_unit_flag]
            is_hep = (sub.specialty == "hepatology").to_numpy()
            src = liver if len(liver) else pool
            choices[is_hep] = rng.choice(src.hco_id.to_numpy(), is_hep.sum())
            choices[~is_hep] = rng.choice(pool.hco_id.to_numpy(), (~is_hep).sum())
        else:
            choices[:] = rng.choice(pool.hco_id.to_numpy(), len(sub))
        parent[h.index.get_indexer(idx)] = choices
    h["primary_parent_id"] = parent
    return h.merge(hcos[["hco_id", "brick_id", "size", "town"]].rename(columns={"hco_id": "primary_parent_id"}),
                   on="primary_parent_id", how="left")


def _consent(rng, h: pd.DataFrame, design, start, end) -> pd.DataFrame:
    """One row per HCP per consent channel. Email consent drives email, webinar invitations."""
    rules = spec.constraint_table("consent_rules").set_index(["market", "channel"])
    rate = h.cluster.map({k: v["consent_email_rate"] for k, v in design["clusters"].items()}).to_numpy()
    n = len(h)
    email = rng.random(n) < rate
    single_only = (h.market == "DE").to_numpy() & (rng.random(n) < 0.15)  # DE: some only gave single opt-in
    remote = rng.random(n) < 0.40
    digital = rng.random(n) < np.where(h.cluster == "digital_responders", 0.70, 0.40)
    span = (end - start).days + 3 * 365
    captured = start - pd.Timedelta(days=3 * 365) + pd.to_timedelta(rng.integers(0, span, n), unit="D")
    source = rng.choice(["rep_capture", "web_form", "event"], n, p=[0.5, 0.35, 0.15])
    granted = {"marketing_email": email, "rep_email": email, "webinar": email, "remote_call": remote,
               "paid_media": digital, "portal": digital}
    frames = []
    for ch in CONSENT_CHANNELS:
        ctype = np.array([rules.loc[(m, ch), "consent_type"] for m in h.market])
        if ch in ("marketing_email", "rep_email", "webinar"):
            ctype = np.where(single_only, "email_opt_in", ctype)
        g = granted[ch]
        frames.append(pd.DataFrame({
            "account_id": h.id, "market": h.market, "channel": ch, "status": np.where(g, "granted", "none"),
            "consent_type": ctype, "captured_date": np.where(g, captured, pd.NaT),
            "source": np.where(g, source, None)}))
    return pd.concat(frames, ignore_index=True)


def build(rng: np.random.Generator, design: dict, scale: float = 1.0) -> dict:
    start = pd.Timestamp(design["clock"]["history_start"])
    end = pd.Timestamp(design["clock"]["history_end"])
    bricks = _bricks(rng, design, scale)
    territories, users = _territories_and_users(rng, design, scale)
    h = _hcps(rng, design, bricks, scale)
    n_practices = {m: int(np.ceil((g.parent_type == "practice").sum() / 3.5)) for m, g in h.groupby("market")}
    hcos = _hcos(rng, design, bricks, scale, n_practices)
    h = _attach_parents(rng, h, hcos)
    # practice_size: clinicians at the practice for primary care, bed-size proxy for hospitals
    h["practice_size"] = h["size"].astype(int)
    h = h.merge(bricks[["brick_id", "territory_id", "potential_index", "rural"]], on="brick_id", how="left")
    h["tier"] = assign_tier(h.assign(score=h.potential_index * h.specialty.map(specialty_weight())
                                     * np.log1p(h.practice_size)), "score")
    n = len(h)
    lang = {m: c["language"] for m, c in design["markets"].items()}
    h["language"] = h.market.map(lang)
    h.loc[(h.market == "DE") & (rng.random(n) < 0.02), "language"] = "en"
    h["status"] = np.where(rng.random(n) < 0.015, "inactive", "active")
    h["no_promo_flag"] = rng.random(n) < 0.02
    specialist = h.specialty.isin(["gastroenterology", "hepatology"]).to_numpy()
    h["expert_status"] = np.where(rng.random(n) < np.where(specialist, 0.06, 0.01), "key_people", "none")
    h["prescriber"] = (h.hcp_type == "physician") | ((h.hcp_type == "nurse") & (rng.random(n) < 0.2))
    h["paediatric_prescriber"] = (h.specialty == "paediatrics") | ((h.specialty == "gp") & (rng.random(n) < 0.3))
    h["care_home_prescriber"] = h.specialty.isin(["gp", "internal_medicine"]) & (rng.random(n) < 0.15)
    h["year_of_birth"] = rng.integers(1956, 1993, n)
    h["name"] = [f"Dr {chr(65 + rng.integers(26))}. {SURNAMES[m][rng.integers(len(SURNAMES[m]))]}" for m in h.market]
    h["onekey_id"] = [f"W{m}{i:07d}" for i, m in zip(range(1, n + 1), h.market)]
    stage0 = rng.choice(5, n, p=[0.30, 0.28, 0.25, 0.14, 0.03])
    h["stage0"] = stage0
    territories = _pilot_arms(rng, territories, h)
    consent = _consent(rng, h, design, start, end)
    return dict(bricks=bricks, territories=territories, users=users, hcos=hcos, hcp=h, consent=consent)


def _pilot_arms(rng, territories: pd.DataFrame, h: pd.DataFrame) -> pd.DataFrame:
    """Stratified by market and tier mix: sort territories by share of tier A, then split each pair."""
    share_a = h.assign(a=h.tier == "A").groupby("territory_id")["a"].mean()
    t = territories.copy()
    t["share_a"] = t["id"].map(share_a).fillna(0)
    t["pilot_arm"] = "none"
    for m, g in t[~t.vacant].groupby("market"):
        ids = g.sort_values("share_a")["id"].to_numpy()
        for k in range(0, len(ids), 2):
            pair = ids[k:k + 2]
            arms = rng.permutation(["test", "control"])[:len(pair)]
            t.loc[t.id.isin(pair), "pilot_arm"] = t.loc[t.id.isin(pair), "id"].map(dict(zip(pair, arms)))
    return t.drop(columns="share_a")
