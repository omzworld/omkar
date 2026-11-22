"""Rule studio upgrade: the plain-language parser (spec/authoring/examples.md), playbooks, the incentive curve."""
import pytest

from nba import author, author_parse, incentive, playbook, spec


def _parsed(text):
    p = author_parse.parse(text)
    return p, author.build(p["form"])


def test_spec_example_brick_decline():
    p, b = _parsed("If a Movicol brick drops more than 8% and the GP has not seen a rep in two months, "
                   "send a rep visit with the efficacy asset")
    r = b["record"]
    assert r["family"] == "movicol" and r["trigger_type"] == "risk"
    assert r["action"]["channel"] == "rep_visit" and r["action"]["content_theme"] == "efficacy"
    assert "brick_volume_r3m_pct <=" in r["condition"] and "brick_r3m_months_declining >=" in r["condition"]
    assert "days_since_rep_visit >=" in r["condition"] and "specialty == 'gp'" in r["condition"]
    assert sorted(r["parameters"].values()) == [-8, 2, 60]
    assert b["missing"] == ["market"]


def test_spec_example_webinar():
    _, b = _parsed("Invite gastroenterologists who opened our last two emails to the next webinar")
    r = b["record"]
    assert r["action"]["channel"] == "webinar" and r["action"]["content_theme"] == "clinical_evidence"
    assert "specialty == 'gastroenterology'" in r["condition"] and "email_opens_30d >=" in r["condition"]
    assert "brand" in b["missing"] and "market" in b["missing"]


def test_spec_example_paediatric():
    _, b = _parsed("Send the paediatric asset to paediatric prescribers who have never had it")
    r = b["record"]
    assert r["family"] == "movicol" and r["action"] == {"channel": "marketing_email", "content_theme": "paediatric", "timing": "this_week"}
    assert r["condition"] == "paediatric_prescriber == True and theme_received('paediatric') == False"


def test_spec_example_unsupported():
    p, b = _parsed("Flag physicians who attended a competitor's symposium")
    assert p["unsupported"] == ["competitor event attendance"] and "at least one condition" in b["missing"]


def test_spec_example_kam():
    _, b = _parsed("KAM brief when an endoscopy unit's procedures rise 15% in a quarter")
    r = b["record"]
    assert r["family"] == "bowel_preparations" and r["action"]["channel"] == "kam_brief"
    assert r["action"]["content_theme"] == "dosing_nursing" and list(r["parameters"].values()) == [15]


@pytest.mark.parametrize("text", author_parse.EXAMPLES)
def test_ready_made_prompts_validate(text):
    """Every ready-made prompt parses to a form the catalogue linter accepts (market may be left to the user)."""
    p = author_parse.parse(text)
    v = author.validate(p["form"])
    assert set(v["missing"]) <= {"market"} and not v["problems"], (v["missing"], v["problems"])


def test_playbook_generic_covers_every_switched_on_trigger_rule():
    from nba.rules import catalogue
    for r in catalogue.load():
        if r.raises_triggers and r.enabled:
            pb = playbook.generic(r.id, r.channel, r.content_theme)
            assert pb["channel"]
            if r.channel in ("rep_visit", "remote_call"):
                assert pb["objective"] and pb["after"]
            if r.channel in ("marketing_email", "rep_email"):
                assert pb["sender"] and pb["follow_up"]


def test_incentive_curve():
    c = spec.assumptions()["incentive"]
    assert incentive.payout(c["threshold_pct"] - 1) == 0
    assert incentive.payout(c["threshold_pct"]) == c["payout_at_threshold_pct"]
    assert incentive.payout(100) == 100
    assert incentive.payout(200) == c["payout_at_cap_pct"]
