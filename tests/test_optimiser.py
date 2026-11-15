"""Step 3 definition of done: the optimiser reproduces spec/examples/optimiser_example.md exactly, and the
weekly summary shows blocked and delayed counts by constraint."""
import pandas as pd
import pytest

from nba import pipeline, spec
from nba.optimiser import expected_return, select

COST = spec.assumptions()["touch_cost"]


def _example() -> pd.DataFrame:
    """One rep, three visit slots, five allowed triggers (the table in optimiser_example.md)."""
    rows = [  # physician, trigger, chance, value
        ("Dr A", "Brick decline, efficacy visit", 0.50, 900),
        ("Dr B", "Webinar attended, dosing visit", 0.55, 700),
        ("Dr C", "New in target brick, intro visit", 0.40, 600),
        ("Dr D", "No contact 60 days, efficacy visit", 0.30, 500),
        ("Dr E", "Low-tier, intro visit", 0.20, 300),
    ]
    df = pd.DataFrame(rows, columns=["hcp_id", "reason", "probability_of_response", "value_of_response"])
    df["candidate_id"] = df.hcp_id
    df["channel"], df["priority"], df["verdict"] = "rep_visit", 50, "allowed"
    df["rep_user_id"], df["kam_user_id"], df["market"] = "REP1", "KAM1", "UK"
    df["constraint_reason"] = None
    df["cost_of_touch"] = COST["rep_visit"]
    df["expected_return"] = expected_return(df.probability_of_response, df.value_of_response, df.cost_of_touch)
    df["substitute_channel"], df["substitute_allowed"], df["substitute_probability"] = "rep_email", True, 0.25
    df["substitute_return"] = expected_return(df.substitute_probability, df.value_of_response, COST["rep_email"])
    return df


def test_costs_match_the_example():
    assert COST["rep_visit"] == 150 and COST["rep_email"] == 10


def test_expected_returns_match_the_hand_calculation():
    assert _example().expected_return.tolist() == [300, 235, 90, 0, -90]


def test_optimiser_reproduces_the_hand_calculated_example():
    out = select(_example(), {("rep_visit", "REP1"): 3, ("rep_email", "REP1"): 40}).set_index("hcp_id")
    assert out.loc[["Dr A", "Dr B", "Dr C"], "status"].tolist() == ["sent"] * 3
    assert out.loc[["Dr A", "Dr B", "Dr C"], "rank"].tolist() == [1, 2, 3]            # slots 1, 2, 3
    assert out.loc["Dr D", "status"] == "substituted"
    assert out.loc["Dr D", "final_channel"] == "rep_email"
    assert out.loc["Dr D", "final_return"] == 115                                       # 0.25 x 500 - 10
    assert out.loc["Dr E", "status"] == "not_sent"
    assert "not positive" in out.loc["Dr E", "not_sent_reason"]
    sent = out[out.status.isin(["sent", "substituted"])]
    assert (sent.final_channel == "rep_visit").sum() == 3 and (sent.final_channel == "rep_email").sum() == 1


def test_no_substitute_without_email_capacity():
    out = select(_example(), {("rep_visit", "REP1"): 3, ("rep_email", "REP1"): 0}).set_index("hcp_id")
    assert out.loc["Dr D", "status"] == "not_sent"
    assert "no rep visit slots left" in out.loc["Dr D", "not_sent_reason"]


def test_best_action_per_physician():
    df = _example()
    extra = df.iloc[[0]].assign(candidate_id="Dr A email", channel="rep_email", cost_of_touch=10,
                                expected_return=expected_return(0.2, 900, 10))
    out = select(pd.concat([df, extra], ignore_index=True), {("rep_visit", "REP1"): 3, ("rep_email", "REP1"): 40})
    a = out[out.hcp_id == "Dr A"].set_index("candidate_id")
    assert a.loc["Dr A", "status"] == "sent"
    assert "higher return" in a.loc["Dr A email", "not_sent_reason"]


def test_dial_at_rules_only_ranks_by_priority_and_keeps_negative_returns():
    df = _example()
    df["priority"] = [10, 20, 30, 40, 90]                       # rules would put Dr E first
    out = select(df, {("rep_visit", "REP1"): 3, ("rep_email", "REP1"): 0}, dial=0.0).set_index("hcp_id")
    assert out.loc[["Dr E", "Dr D", "Dr C"], "status"].tolist() == ["sent"] * 3
    full = select(df, {("rep_visit", "REP1"): 3, ("rep_email", "REP1"): 0}, dial=1.0)
    assert full[full.status == "sent"].final_return.sum() > out[out.status == "sent"].final_return.sum()


# ---------------------------------------------------------------- the weekly run on synthetic data

@pytest.fixture(scope="module")
def week1(full):
    return pipeline.run_week(1, data_dir=full, rebuild_features=True, save=False)


def test_weekly_summary_shows_blocked_and_delayed_by_constraint(week1):
    s = pipeline.summary(week1)
    held = s["constraints"]
    assert {"blocked", "delayed"} <= set(held.verdict)
    assert held.constraint_id.notna().all() and (held.candidates > 0).all()
    assert s["headline"]["blocked"] == held[held.verdict == "blocked"].candidates.sum()


def test_every_candidate_has_a_verdict_and_every_unsent_one_a_reason(week1):
    d = week1.decisions
    assert d.verdict.isin(["allowed", "delayed", "blocked"]).all()
    assert d[d.verdict != "allowed"].constraint_id.notna().all()
    assert d[d.status == "not_sent"].not_sent_reason.notna().all()
    # A swap that displaces a planned touch must be worth more than it; a slot freed by a blocked planned touch is
    # already budgeted and goes to the best remaining candidate; planned touches go ahead as planned.
    moved = set(d.candidate_id[d.status == "moved"])
    swaps = d[(d.status == "sent") & (d.origin != "plan") & d.replaces.isin(moved)]
    by_id = d.set_index("candidate_id").expected_return
    assert all(er > by_id[r] for er, r in zip(swaps.final_return, swaps.replaces))


def test_the_week_never_exceeds_the_plan(week1):
    """Per rep and channel (per market for marketing email), touches sent never exceed the planned touches due."""
    d = week1.decisions
    planned = d[d.origin == "plan"].resource.astype(str).value_counts()
    sent = d[d.status == "sent"].resource.astype(str).value_counts()
    for key, n in sent.items():
        assert n <= planned.get(key, 0), key


def test_every_engine_touch_displaces_one_planned_touch(week1):
    """Budget neutral: each touch the engine adds takes the slot of exactly one planned touch (one it moved, or one
    a hard block freed), like for like, and no slot is used twice."""
    d = week1.decisions
    added = d[(d.status == "sent") & (d.origin != "plan")]
    moved = d[d.status == "moved"]
    freed = d[(d.origin == "plan") & (d.status == "blocked")]
    assert added.replaces.notna().all() and added.replaces.is_unique
    assert set(moved.candidate_id) <= set(added.replaces)
    assert set(added.replaces) <= set(moved.candidate_id) | set(freed.candidate_id)
    by_id = d.set_index("candidate_id")
    assert all(by_id.at[r, "channel"] == ch for r, ch in zip(added.replaces, added.channel))


def test_at_most_one_touch_per_physician_per_channel(week1):
    assert not week1.sent.duplicated(["hcp_id", "final_channel"]).any()


def test_every_output_row_carries_the_audit_columns(week1):
    s = week1.sent
    for col in ["rule_ids", "constraint_id", "chance_tier", "reason"]:
        assert col in s.columns
    assert s.chance_tier.isin(["own_history", "segment", "benchmark"]).all()
