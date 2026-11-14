"""Read and write the Parquet tables under data/, and query them with DuckDB SQL.

Layout:
  data/<table>.parquet          one file per table in spec/schemas/datasets.yaml
  data/hidden/<table>.parquet   simulator-only truth (behaviour clusters). Only nba.synth and
                                nba.feedback may read it; the engine never does.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pyarrow.parquet as pq

from nba import schema, spec

HIDDEN = "hidden"


def _dir(data_dir: Path | None) -> Path:
    return Path(data_dir) if data_dir else spec.data_dir()


def write_table(name: str, df: pd.DataFrame, data_dir: Path | None = None) -> None:
    d = _dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    pq.write_table(schema.conform(name, df), d / f"{name}.parquet")


def write_hidden(name: str, df: pd.DataFrame, data_dir: Path | None = None) -> None:
    d = _dir(data_dir) / HIDDEN
    d.mkdir(parents=True, exist_ok=True)
    df.to_parquet(d / f"{name}.parquet", index=False)


def read_table(name: str, data_dir: Path | None = None) -> pd.DataFrame:
    return pd.read_parquet(_dir(data_dir) / f"{name}.parquet")


def read_hidden(name: str, data_dir: Path | None = None) -> pd.DataFrame:
    return pd.read_parquet(_dir(data_dir) / HIDDEN / f"{name}.parquet")


def tables(data_dir: Path | None = None) -> list[str]:
    return sorted(p.stem for p in _dir(data_dir).glob("*.parquet"))


def connect(data_dir: Path | None = None) -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB with one view per public table, so you can write plain SQL:
    con.sql("select market, count(*) from account_vod group by 1").df()
    Hidden tables are deliberately not registered."""
    con = duckdb.connect()
    d = _dir(data_dir)
    for name in tables(d):
        con.execute(f"create view {name} as select * from read_parquet('{(d / name).as_posix()}.parquet')")
    return con
