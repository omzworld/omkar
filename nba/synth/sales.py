"""Market signals: IQVIA brick sales (monthly) and endoscopy unit procedure volumes (quarterly).

Brick sales follow the physicians' journey stages, so moving physicians along the journey shows up
in sales, with noise and seasonality as set in synthetic_design.yaml.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nba.synth.behaviour import STAGE_INDEX

PRICE = {"Movicol": {"UK": 7.2, "DE": 6.8}, "Xifaxan": {"UK": 255.0, "DE": 240.0}}
XIFAXAN_UNIT_SCALE = 0.25   # packs per physician-month relative to the Movicol stage table
OTC_BASE_UNITS = 30         # pharmacy and over-the-counter units per brick-month at average potential


def brick_sales(rng: np.random.Generator, design: dict, world: dict, stage_weekly: pd.DataFrame) -> pd.DataFrame:
    cfg = design["brick_sales"]
    units_by_stage = np.array([cfg["units_per_hcp_month_by_stage"][s] for s in STAGE_INDEX])
    season = {pd.Timestamp(f"2000-{m}-01").month: f for m, f in cfg["seasonality"].items()}
    h = world["hcp"][["id", "brick_id", "brand", "market"]]
    bricks = world["bricks"]

    sw = stage_weekly.assign(month=pd.to_datetime(stage_weekly.week).dt.to_period("M"))
    monthly = sw.sort_values("week").groupby(["account_id", "month"]).tail(1)   # stage at month end
    monthly = monthly.merge(h, left_on="account_id", right_on="id")
    monthly["units"] = monthly.stage.map(STAGE_INDEX).map(dict(enumerate(units_by_stage)))
    rows = []
    for product, brands, scale in [("Movicol", ["Movicol"], 1.0), ("Xifaxan", ["Xifaxan"], XIFAXAN_UNIT_SCALE)]:
        m = monthly[monthly.brand.isin(brands)]
        u = (m.groupby(["brick_id", "month"])["units"].sum() * scale).unstack(fill_value=0)
        u = u.reindex(bricks.brick_id, fill_value=0)
        months = u.columns
        base = (OTC_BASE_UNITS * scale * bricks.set_index("brick_id").potential_index / 100).to_numpy()[:, None]
        noise = rng.lognormal(0, cfg["noise_sd"], u.shape)
        seas = np.array([season.get(p.month, 1.0) for p in months])[None, :]
        own = (u.to_numpy() + base) * noise * seas
        # Competitors: the brick's total market grows slowly; competitors take what Norgine does not.
        share0 = rng.uniform(0.25, 0.5, len(u))[:, None]
        growth = rng.normal(0.002, 0.004, len(u))[:, None]
        t = np.arange(len(months))[None, :]
        total = (own[:, :1] / share0) * (1 + growth) ** t * seas * rng.lognormal(0, 0.04, u.shape)
        competitor = np.maximum(total - own, 0.15 * total)
        market = bricks.set_index("brick_id").market.reindex(u.index).to_numpy()
        price = np.array([PRICE[product][mk] for mk in market])[:, None]
        rows.append(pd.DataFrame({
            "brick_id": np.repeat(u.index.to_numpy(), len(months)), "market": np.repeat(market, len(months)),
            "product": product, "month": np.tile([p.to_timestamp() for p in months], len(u)),
            "units": own.round(1).ravel(), "value": (own * price).round(2).ravel(),
            "competitor_units": competitor.round(1).ravel()}))
    return pd.concat(rows, ignore_index=True)


def procedure_volume(rng: np.random.Generator, design: dict, world: dict, stage_weekly: pd.DataFrame) -> pd.DataFrame:
    hcos, h = world["hcos"], world["hcp"]
    units = hcos[hcos.hco_type == "endoscopy_unit"].reset_index(drop=True)
    sw = stage_weekly.assign(quarter=pd.to_datetime(stage_weekly.week).dt.to_period("Q"))
    sw = sw.sort_values("week").groupby(["account_id", "quarter"]).tail(1)
    sw = sw.merge(h[["id", "primary_parent_id"]], left_on="account_id", right_on="id")
    sw["s"] = sw.stage.map(STAGE_INDEX)
    unit_stage = sw.groupby(["primary_parent_id", "quarter"])["s"].mean().unstack()
    quarters = sorted(sw.quarter.unique())
    base = units.unit_tier.map({"A": 3000, "B": 1500, "C": 600}).to_numpy() * rng.uniform(0.8, 1.2, len(units))
    drift = rng.normal(0.01, 0.03, len(units))
    share0 = rng.uniform(0.2, 0.6, len(units))
    rows = []
    for q_i, q in enumerate(quarters):
        st = unit_stage.reindex(units.hco_id)[q].fillna(2.0).to_numpy() if q in unit_stage.columns else np.full(len(units), 2.0)
        vol = base * (1 + drift) ** q_i * rng.lognormal(0, 0.05, len(units))
        share = np.clip(share0 + 0.04 * (st - 2) + rng.normal(0, 0.02, len(units)), 0.02, 0.95)
        inadequate = np.clip(0.10 + 0.08 * (1 - share) + rng.normal(0, 0.01, len(units)), 0.03, 0.4)
        rows.append(pd.DataFrame({"hco_id": units.hco_id, "quarter": f"{q.year}-Q{q.quarter}",
                                  "colonoscopies": vol.round().astype(int), "norgine_prep_share": share.round(3),
                                  "inadequate_prep_rate": inadequate.round(3)}))
    return pd.concat(rows, ignore_index=True)
