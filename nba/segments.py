"""Segmentation helpers shared by the generator and (from step 2) the feature builder.

Tier A, B or C comes from brick potential, specialty weight and practice size, cut by the
shares in synthetic_design.yaml within each market.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nba import spec

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
