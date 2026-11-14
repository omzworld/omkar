"""Feature table and trigger raising on the full synthetic dataset."""
import pandas as pd
import pytest

from nba import columns, data, features
from nba.rules import engine


@pytest.fixture(scope="module")
def week1(full):
    return features.build(1, data_dir=full)


def test_feature_table_has_every_account_column(week1):
    t = week1.table
    assert set(columns.account_columns()) <= set(t.columns)
    assert t.hcp_id.is_unique


def test_one_row_per_account(full, week1):
    assert len(week1.table) == len(data.read_table("account_vod", full))


def test_features_only_use_data_before_the_run_date(week1):
    t = week1.table
    assert (t.days_since_last_touch.dropna() >= 0).all()
    assert (t.days_since_rep_visit.dropna() > 0).all()


def test_snapshot_round_trip(full, week1):
    again = features.load_snapshot(1, data_dir=full)
    def norm(df):  # an all-blank column may come back as None or NaN; both mean blank
        return df.astype(object).where(df.notna(), None)
    pd.testing.assert_frame_equal(norm(again.table), norm(week1.table), check_dtype=False)


def test_no_hidden_cluster_in_features(week1):
    assert not any("cluster" in c for c in week1.table.columns)


def test_triggers_have_reasons_and_lowering_a_threshold_only_adds(week1):
    before = engine.raise_triggers(week1)
    assert len(before) > 0
    assert not before.reason.str.contains(r"[{}]").any()
    assert (before.origin == "rule").all()
    after = engine.raise_triggers(week1, overrides={"R075": {"decline_pct": 6}})
    diff = engine.compare(before, after, "R075")
    assert diff["after"] > diff["before"] and not diff["removed"]


def test_brand_rules_only_reach_their_brand(week1):
    tr = engine.raise_triggers(week1)
    movicol_rules = {r.id for r in engine.trigger_rules() if r.brand == "Movicol"}
    assert (tr[tr.rule_id.isin(movicol_rules)].brand == "Movicol").all()
