"""Step 4 definition of done, on a 20% sample so the tests stay quick: the runner completes, Veeva payloads
validate against the schema, every test-territory rep gets a grounded talk track every week, responses and
dismissals change next week's features, and a replay with the same seed is identical."""
import json

import jsonschema
import pandas as pd
import pytest

from nba import data, features, spec
from nba.delivery import grounding_check
from nba.runner import run
from nba.synth import generate

WEEKS = 3
QUIET = dict(log=lambda *_: None)


def _fresh(path):
    generate(seed=11, scale=0.2, data_dir=path, **QUIET)
    run(WEEKS, data_dir=path, **QUIET)
    return path


@pytest.fixture(scope="module")
def pilot(tmp_path_factory):
    return _fresh(tmp_path_factory.mktemp("pilot"))


def test_runner_completes_every_week(pilot):
    summary = pd.read_parquet(pilot / "runs" / "summary.parquet")
    assert summary.week.tolist() == list(range(1, WEEKS + 1))
    assert (summary.sent > 0).all()


def test_veeva_payloads_validate_against_the_schema(pilot):
    schema = json.loads((spec.SPEC / "schemas" / "suggestion_payload.json").read_text())
    for week in range(1, WEEKS + 1):
        payloads = json.loads((pilot / "runs" / f"week_{week:02d}" / "veeva_suggestions.json").read_text())
        assert payloads, week
        for p in payloads:
            jsonschema.validate(p, schema, format_checker=jsonschema.FormatChecker())


def test_every_test_rep_has_a_grounded_talk_track_every_week(pilot):
    terr = data.read_table("territory_vod", pilot)
    reps = set(terr[(terr.pilot_arm == "test") & terr.rep_user_id.notna()].rep_user_id)
    briefs = data.read_table("rep_brief", pilot)
    for week in range(1, WEEKS + 1):
        b = briefs[pd.to_datetime(briefs.run_week) == features.as_of(week)]
        assert set(b.user_id) == reps, week
        assert b.grounding_check_passed.all()
        assert (b.word_count < 300).all()


def test_grounding_check_catches_an_invented_number():
    brief = {"last_week": {"visits_completed": 18}, "suggestions": [{"reason": "no visit in 64 days"}]}
    assert grounding_check("You completed 18 visits; no visit in 64 days.", brief)[0]
    ok, missing = grounding_check("You completed 18 visits and 25 were planned.", brief)
    assert not ok and missing == ["25"]


def test_suggestions_are_accepted_or_dismissed_with_a_reason(pilot):
    s = data.read_table("suggestion_vod", pilot)
    assert set(s.status) <= {"accepted", "dismissed"}
    assert s[s.status == "dismissed"].dismiss_reason.notna().all()
    assert s[s.status == "accepted"].dismiss_reason.isna().all()


def test_control_territories_never_get_engine_suggestions(pilot):
    s = data.read_table("suggestion_vod", pilot)
    acc = data.read_table("account_vod", pilot).set_index("id").territory_id
    arm = data.read_table("territory_vod", pilot).set_index("id").pilot_arm
    assert (s.account_id.map(acc).map(arm) == "test").all()


def test_responses_and_dismissals_change_next_weeks_features(pilot):
    week1 = features.load_snapshot(1, pilot).table.set_index("hcp_id")
    week2 = features.load_snapshot(2, pilot).table.set_index("hcp_id")
    s = data.read_table("suggestion_vod", pilot)
    dismissed_w1 = s[(pd.to_datetime(s.suggested_date) == features.as_of(1)) & (s.status == "dismissed")].account_id
    assert len(dismissed_w1) > 0
    assert (week2.loc[dismissed_w1, "dismissals_30d"] >= 1).all()
    accepted = s[(pd.to_datetime(s.suggested_date) == features.as_of(1)) & (s.status == "accepted")]
    touched = accepted[accepted.account_id.isin(week1.index[week1.account_type == "hcp"])].account_id
    assert len(touched) > 0
    assert (week2.loc[touched, "days_since_last_touch"] <= 7).all()        # touched during week 1


def test_replay_with_the_same_seed_is_identical(pilot, tmp_path):
    again = _fresh(tmp_path / "again")
    for table in spec.datasets():
        a, b = data.read_table(table, pilot), data.read_table(table, again)
        if table == "rep_brief":           # the prose may differ when a language model writes it
            a, b = a.drop(columns="prose"), b.drop(columns="prose")
        pd.testing.assert_frame_equal(a, b, obj=table)
