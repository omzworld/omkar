"""Read-only access to the specification pack in spec/ and to config.yaml.

Everything the engine needs to know about the business (rules, constraints, assumptions,
data design) comes from here, so code never hard-codes a business number.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec"


def _yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def config() -> dict:
    return _yaml(ROOT / "config.yaml")


@lru_cache
def datasets() -> dict:
    """Table definitions: {table_name: {fields: {...}, ...}}."""
    return _yaml(SPEC / "schemas" / "datasets.yaml")["tables"]


@lru_cache
def design() -> dict:
    """Synthetic data design: markets, clusters, history plan, brick sales, pilot arms."""
    return _yaml(SPEC / "data" / "synthetic_design.yaml")


@lru_cache
def assumptions() -> dict:
    """Return model inputs: touch costs, values, chance tiers, caps."""
    return _yaml(SPEC / "assumptions" / "return_assumptions.yaml")


@lru_cache
def catalogue() -> dict:
    return _yaml(SPEC / "rules" / "rules_catalogue.yaml")


def constraint_table(name: str) -> pd.DataFrame:
    """One of consent_rules, country_code, cadence, capacity."""
    return pd.read_csv(SPEC / "constraints" / f"{name}.csv")


def data_dir() -> Path:
    return ROOT / config()["data_dir"]
