"""Step 2 definition of done: one firing and one silent fixture per rule, the catalogue linter, and the
safe evaluator. Plus a few hand-written fixtures with realistic values for the demo rules."""
import pandas as pd
import pytest

from nba.rules import catalogue
from nba.rules.catalogue import Rule
from nba.rules.expr import Condition, ConditionError, Context
from tests import fixtures

RULES = catalogue.load()


@pytest.mark.parametrize("rule", RULES, ids=[r.id for r in RULES])
def test_every_rule_has_a_firing_and_a_silent_fixture(rule):
    cond = rule.condition()
    (fire_row, fire_ctx), (silent_row, silent_ctx) = fixtures.firing_and_silent(cond.tree)
    assert cond.evaluate(pd.DataFrame([fire_row]), fire_ctx).iloc[0], f"should fire: {fire_row}"
    assert not cond.evaluate(pd.DataFrame([silent_row]), silent_ctx).iloc[0], f"should not fire: {silent_row}"


# ---------------------------------------------------------------- hand-written fixtures for demo rules

def _r(rule_id, **params) -> Rule:
    r = catalogue.by_id()[rule_id]
    return r.with_parameters(**params) if params else r


def test_brick_decline_rule_with_realistic_rows():
    rows = pd.DataFrame([
        dict(brick_volume_qoq_pct=-9.3, days_since_rep_visit=64, tier="A"),     # fires
        dict(brick_volume_qoq_pct=-7.0, days_since_rep_visit=64, tier="A"),     # decline too small
        dict(brick_volume_qoq_pct=-9.3, days_since_rep_visit=30, tier="A"),     # visited recently
        dict(brick_volume_qoq_pct=-9.3, days_since_rep_visit=64, tier="C"),     # tier C has its own rule
        dict(brick_volume_qoq_pct=None, days_since_rep_visit=64, tier="A"),     # no sales data: never fires
        dict(brick_volume_qoq_pct=-9.3, days_since_rep_visit=None, tier="A"),   # never visited: unknown, no fire
    ])
    assert _r("R075").condition().evaluate(rows).tolist() == [True, False, False, False, False, False]
    # Rule studio: lower the threshold to 6% and the second row now fires too.
    assert _r("R075", decline_pct=6).condition().evaluate(rows).tolist() == [True, True, False, False, False, False]


def test_theme_function_rule():
    rows = pd.DataFrame([dict(hcp_id="A", paediatric_prescriber=True), dict(hcp_id="B", paediatric_prescriber=True),
                         dict(hcp_id="C", paediatric_prescriber=False)])
    ctx = Context(themes=pd.DataFrame([dict(hcp_id="B", theme="paediatric", days_ago=20, ignored_count=0)]))
    assert _r("R081").condition().evaluate(rows, ctx).tolist() == [True, False, False]


def test_reason_is_filled_in_plain_language():
    from nba.rules.engine import reasons
    row = pd.DataFrame([dict(brick_id="UK-B014", brick_volume_qoq_pct=-9.3, days_since_rep_visit=64)])
    assert reasons(_r("R075"), row) == ["Brick UK-B014 down 9.3% on prior quarter, no visit in 64 days"]


# ---------------------------------------------------------------- evaluator safety and semantics

@pytest.mark.parametrize("text", [
    "__import__('os').system('ls')", "tier.upper() == 'A'", "days_since_rep_visit + 1 > 3",
    "[x for x in tier]", "open('f')", "lambda: 1",
])
def test_evaluator_refuses_anything_but_conditions(text):
    with pytest.raises(ConditionError):
        Condition(text)


def test_missing_values_never_fire_even_with_not_equal():
    rows = pd.DataFrame({"stage": ["loyalty", None]})
    assert Condition("stage != 'curiosity'").evaluate(rows).tolist() == [True, False]


def test_in_and_not_in():
    rows = pd.DataFrame({"tier": ["A", "C", None]})
    assert Condition("tier in ['A','B']").evaluate(rows).tolist() == [True, False, False]
    assert Condition("tier not in ['A','B']").evaluate(rows).tolist() == [False, True, False]


# ---------------------------------------------------------------- linter

def test_catalogue_is_clean():
    assert catalogue.lint() == []


def _fake(condition, **kw) -> Rule:
    base = catalogue.by_id()["R075"]
    return Rule(**{**base.__dict__, "id": "R999", "condition_template": condition, "parameters": {}, **kw})


def test_linter_fails_on_a_missing_column():
    problems = catalogue.lint([_fake("days_since_last_dinner >= 3")])
    assert any("days_since_last_dinner" in p for p in problems)


def test_linter_fails_on_a_value_that_does_not_exist():
    problems = catalogue.lint([_fake("hcp_role == 'hospital_pharmacist'")])
    assert any("hospital_pharmacist" in p for p in problems)


def test_linter_fails_on_a_trigger_rule_using_a_candidate_column():
    problems = catalogue.lint([_fake("channel == 'rep_visit'")])
    assert any("candidate-level" in p for p in problems)


def test_linter_fails_on_a_missing_parameter():
    problems = catalogue.lint([_fake("brick_volume_qoq_pct <= -{decline}")])
    assert any("decline" in p for p in problems)
