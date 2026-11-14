"""Step 1 definition of done: every table is generated to spec, consent coverage matches the design,
the run is reproducible from the seed, and hidden behaviour clusters never reach the engine."""
from pathlib import Path

import pandas as pd
import pytest

from nba import data, readiness, schema, spec
from nba.synth import generate

ROOT = Path(__file__).resolve().parent.parent
QUIET = dict(log=lambda *_: None)


@pytest.fixture(scope="session")
def full(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("full")
    generate(data_dir=d, **QUIET)
    return d


def test_every_table_in_the_spec_is_written_with_its_columns(full):
    for table in spec.datasets():
        df = data.read_table(table, full)
        if table not in schema.FREE_FORM:
            assert list(df.columns) == list(schema.fields(table)), table


def test_population_matches_the_design(full):
    acc = data.read_table("account_vod", full)
    hcps = acc[acc.account_type == "hcp"].groupby("market").size()
    for m, cfg in spec.design()["markets"].items():
        assert hcps[m] == cfg["hcps"]


def test_consent_coverage_within_5_points_of_design(full):
    report = readiness.build(full)
    assert readiness.passed(report), report["consent"]


def test_pilot_arms_are_balanced_per_market(full):
    t = data.read_table("territory_vod", full)
    for m, g in t[~t.vacant].groupby("market"):
        counts = g.pilot_arm.value_counts()
        assert abs(counts.get("test", 0) - counts.get("control", 0)) <= 1, m
    assert (t[t.vacant].pilot_arm == "none").all()


def test_same_seed_reproduces_every_number(tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    generate(seed=7, scale=0.1, data_dir=a, **QUIET)
    generate(seed=7, scale=0.1, data_dir=b, **QUIET)
    generate(seed=8, scale=0.1, data_dir=c, **QUIET)
    for table in spec.datasets():
        pd.testing.assert_frame_equal(data.read_table(table, a), data.read_table(table, b), obj=table)
    assert not data.read_table("call2_vod", a).equals(data.read_table("call2_vod", c))


def test_hidden_clusters_are_not_in_any_public_table(full):
    for table in data.tables(full):
        assert "cluster" not in data.read_table(table, full).columns, table
    assert "hcp_cluster" not in data.tables(full)


def test_engine_modules_never_read_hidden_data():
    """Only the simulator (synth, feedback) may touch data/hidden."""
    allowed = {"synth", "feedback", "data.py"}
    for path in (ROOT / "nba").rglob("*.py"):
        rel = path.relative_to(ROOT / "nba").parts
        if rel[0] in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        assert "read_hidden" not in text and "hcp_cluster" not in text, path
