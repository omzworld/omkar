"""Read-only access to the specification pack in spec/ and to config.yaml.

Everything the engine needs to know about the business (rules, constraints, assumptions,
data design) comes from here, so code never hard-codes a business number.
"""
from __future__ import annotations

import os
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
    """Where the generated tables live: config.yaml's data_dir, or the NBA_DATA_DIR environment variable when set
    (useful to keep the frequently rewritten data outside a synced folder such as OneDrive)."""
    override = os.environ.get("NBA_DATA_DIR")
    if override:
        return Path(override).expanduser()
    p = Path(config()["data_dir"]).expanduser()       # "~/..." or an absolute path: outside the project folder
    return p if p.is_absolute() else ROOT / p
