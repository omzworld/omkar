"""Turn the table definitions in spec/schemas/datasets.yaml into typed Parquet schemas.

`conform(name, df)` is the single gate every table passes through before it is written:
it orders the columns as the spec lists them, adds any missing column as empty, casts each
column to its declared type and checks that values in a list-of-values field are allowed.
Think of it as the CREATE TABLE statement plus CHECK constraints for our Parquet files.
"""
from __future__ import annotations

import pandas as pd
import pyarrow as pa

from nba import spec

ARROW_TYPES = {
    "string": pa.string(),
    "int": pa.int64(),
    "float": pa.float64(),
    "bool": pa.bool_(),
    "date": pa.date32(),
    "datetime": pa.timestamp("s"),
}

# Tables the spec describes without a field list; their columns are set by the engine module that writes them.
FREE_FORM = {"feature_snapshot"}


def fields(table: str) -> dict[str, dict]:
    """{column: {"type": ..., "values": [...] or None}} in spec order."""
    out = {}
    for col, decl in (spec.datasets()[table].get("fields") or {}).items():
        if isinstance(decl, str):
            out[col] = {"type": decl, "values": None}
        else:
            out[col] = {"type": decl["type"], "values": decl.get("values")}
    return out


def arrow_schema(table: str) -> pa.Schema:
    return pa.schema([(c, ARROW_TYPES[d["type"]]) for c, d in fields(table).items()])


def empty(table: str) -> pd.DataFrame:
    """An empty table with the right columns, for engine-written tables before the engine runs."""
    return pd.DataFrame({c: pd.Series(dtype="object") for c in fields(table)})


def conform(table: str, df: pd.DataFrame) -> pa.Table:
    """Validate and cast a DataFrame to the spec schema. Raises ValueError on any mismatch."""
    if table in FREE_FORM:
        return pa.Table.from_pandas(df, preserve_index=False)
    decl = fields(table)
    extra = set(df.columns) - set(decl)
    if extra:
        raise ValueError(f"{table}: columns not in datasets.yaml: {sorted(extra)}")
    df = df.reindex(columns=list(decl))
    for col, d in decl.items():
        if d["values"]:
            bad = set(df[col].dropna().unique()) - set(d["values"])
            if bad:
                raise ValueError(f"{table}.{col}: values not allowed by datasets.yaml: {sorted(bad)}")
        if d["type"] in ("date", "datetime"):
            df[col] = pd.to_datetime(df[col])
            if d["type"] == "date":
                df[col] = df[col].dt.date
        elif d["type"] == "int":
            df[col] = df[col].astype("Int64")
        elif d["type"] == "bool":
            df[col] = df[col].astype("boolean")
        elif d["type"] == "string":
            df[col] = df[col].astype("string")
    return pa.Table.from_pandas(df, schema=arrow_schema(table), preserve_index=False)
