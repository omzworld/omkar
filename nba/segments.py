"""Segmentation helpers shared by the generator and (from step 2) the feature builder.

Tier A, B or C comes from brick potential, specialty weight and practice size, cut by the
shares in synthetic_design.yaml within each market.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nba import spec

# Each specialty's main brand (business reference data used by the generator and the feature builder).
BRAND = {"gp": "Movicol", "paediatrics": "Movicol", "internal_medicine": "Movicol",
         "gastroenterology": "Plenvu_Moviprep", "endoscopy_nurse": "Plenvu_Moviprep",
         "pharmacist_hospital": "Plenvu_Moviprep", "hepatology": "Xifaxan"}
OTHER_SPECIALTY_WEIGHT = 0.6  # specialties without a weight in return_assumptions.yaml


def specialty_weight() -> dict:
    w = dict(spec.assumptions()["value_allocation"]["specialty_weight"])
    for s in spec.design()["specialty_mix"]:
        w.setdefault(s, OTHER_SPECIALTY_WEIGHT)
    return w


def assign_tier(df: pd.DataFrame, score_col: str, group_cols: list[str] | None = None) -> np.ndarray:
    """Top share by score is A, the next share B, the rest C, within each group (default: market)."""
    shares = spec.design()["tiers"]
    a, b = shares["A"], shares["A"] + shares["B"]
    rank = df.groupby(group_cols or ["market"])[score_col].rank(pct=True, ascending=False, method="first")
    return np.where(rank <= a, "A", np.where(rank <= b, "B", "C"))


def potential(c: pd.DataFrame) -> pd.Series:
    """A physician's potential: specialty weight x brick potential x practice size relative to similar practices
    (same market and practice type), capped between a quarter and four times the average. Organisations get 1."""
    w = specialty_weight()
    hcp = c.account_type == "hcp"
    size = np.log1p(c.practice_size.astype(float).fillna(1))
    peers = [c.market, c.practice_type.fillna("none")]
    size_rel = (size / size.groupby(peers).transform("mean")).fillna(1)
    raw = (c.specialty.map(w).fillna(OTHER_SPECIALTY_WEIGHT).astype(float)
           * c.brick_potential_index.astype(float).fillna(100) / 100 * size_rel).clip(0.25, 4)
    return pd.Series(np.where(hcp, raw, 1.0), index=c.index)
