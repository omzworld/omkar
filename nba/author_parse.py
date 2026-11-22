"""Plain-language rule writing without a language model: a phrase parser that turns a typed sentence into the
rule studio's form (author.build then lists what is still missing, and the marketer submits the checked form).

It recognises the signals, people, actions and content the catalogue uses, in the words a brand team writes:
"if a Movicol brick drops more than 8% and the GP has not seen a rep in two months, send a rep visit with the
efficacy asset". Anything it cannot map is returned as `unrecognised` or `unsupported` rather than guessed.
When a language model key is set this is the fallback; the output is the same form either way.
"""
from __future__ import annotations

import re

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "twelve": 12, "a": 1, "an": 1}
N = r"(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|twelve|a|an)"
UNIT_DAYS = {"day": 1, "week": 7, "month": 30}


def _n(x: str) -> float:
    return float(NUM_WORDS.get(x.lower(), x))


def _days(num: str, unit: str) -> int:
    return int(_n(num) * UNIT_DAYS[unit.rstrip("s")])


def _c(column, kind, op, value):
    return {"column": column, "kind": kind, "op": op, "value": value}


# Signals: (pattern, builder(match) -> list of conditions, reason fragment, risk?)
SIGNALS = [
    (r"brick (?:drops|declines|falls|is down)[^.,;]*?(?:more than|over|by|at least)?\s*" + N + r"\s*%",
     lambda m: [_c("brick_volume_r3m_pct", "number", "<=", -_n(m[1])), _c("brick_r3m_months_declining", "number", ">=", 2)],
     "Brick {brick_id} down {brick_volume_r3m_pct}% over 3 months", True),
    (r"brick (?:grows|rises|is up|increases)[^.,;]*?(?:more than|over|by|at least)?\s*" + N + r"\s*%",
     lambda m: [_c("brick_volume_r3m_pct", "number", ">=", _n(m[1])), _c("brick_r3m_months_growing", "number", ">=", 2)],
     "Brick {brick_id} up {brick_volume_r3m_pct}% over 3 months", False),
    (r"competitor share (?:rises|grows|is up|increases)[^.,;]*?" + N + r"\s*(?:points|pts|%)",
     lambda m: [_c("brick_competitor_share_r3m_change", "number", ">=", _n(m[1]))],
     "Competitor share up {brick_competitor_share_r3m_change} points over 3 months", True),
    (r"(?:not seen a rep|no rep visit|no visit|not been visited|not visited)[^.,;]*?(?:in|for)\s+" + N + r"\s+(days?|weeks?|months?)",
     lambda m: [_c("days_since_rep_visit", "number", ">=", _days(m[1], m[2]))], "no rep visit in {days_since_rep_visit} days", False),
    (r"(?:not responded|no response|not replied|gone quiet|silent)[^.,;]*?(?:in|for)\s+" + N + r"\s+(days?|weeks?|months?)",
     lambda m: [_c("days_since_last_response", "number", ">=", _days(m[1], m[2]))],
     "no response in {days_since_last_response} days", True),
    (r"(?:no touch|not contacted|no contact)[^.,;]*?(?:in|for)\s+" + N + r"\s+(days?|weeks?|months?)",
     lambda m: [_c("days_since_last_touch", "number", ">=", _days(m[1], m[2]))], "no contact in {days_since_last_touch} days", False),
    (r"opened (?:our )?(?:last )?" + N + r" emails? (?:but|without|and) (?:never |not |did not |didn't )?click",
     lambda m: [_c("email_opens_30d", "number", ">=", _n(m[1])), _c("email_clicks_30d", "number", "==", 0)],
     "opened {email_opens_30d} emails without clicking", False),
    (r"opened (?:our )?(?:last )?" + N + r" emails?",
     lambda m: [_c("email_opens_30d", "number", ">=", _n(m[1]))], "opened {email_opens_30d} emails in 30 days", False),
    (r"clicked (?:on )?(?:an |our |a )?(?:email|link)",
     lambda m: [_c("email_clicks_30d", "number", ">=", 1)], "clicked an email in the last 30 days", False),
    (r"registered (?:for the webinar )?but (?:missed|did not attend|didn't attend|did not join)",
     lambda m: [_c("webinar_registered_30d", "yes_no", "yes", None), _c("webinar_attended_30d", "yes_no", "no", None)],
     "registered but missed the webinar", False),
    (r"attended (?:the |a |our )?(?:\w+ )?webinar",
     lambda m: [_c("webinar_attended_30d", "yes_no", "yes", None)], "attended the webinar {days_since_webinar} days ago", False),
    (r"(?:never had|not (?:yet )?received|has not had|have not had) (?:the |it|our )?(\w+)?",
     lambda m: [], "", False),  # handled with the content theme below
    (r"(?:new to|added to|joined) (?:the )?target list",
     lambda m: [_c("new_in_target", "yes_no", "yes", None)], "added to the target list {days_since_added} days ago", False),
    (r"procedures (?:rise|grow|are up|increase)[^.,;]*?" + N + r"\s*%",
     lambda m: [_c("account_type", "text", "==", "endoscopy_unit"), _c("unit_procedure_volume_qoq_pct", "number", ">=", _n(m[1]))],
     "Unit {unit_id} procedures up {unit_procedure_volume_qoq_pct}%", False),
    (r"procedures (?:drop|fall|decline|are down)[^.,;]*?" + N + r"\s*%",
     lambda m: [_c("account_type", "text", "==", "endoscopy_unit"), _c("unit_procedure_volume_qoq_pct", "number", "<=", -_n(m[1]))],
     "Unit {unit_id} procedures down {unit_procedure_volume_qoq_pct}%", True),
    (r"dispensing (?:rises|grows|is up|increases)[^.,;]*?" + N + r"\s*%",
     lambda m: [_c("account_type", "text", "==", "pharmacy"), _c("pharmacy_dispensing_qoq_pct", "number", ">=", _n(m[1]))],
     "Pharmacy dispensing up {pharmacy_dispensing_qoq_pct}%", False),
    (r"(?:moved|stepped|slipped) back",
     lambda m: [_c("stage_regressed", "yes_no", "yes", None)], "moved back from {prev_stage} to {stage}", True),
]
PEOPLE = [
    (r"\bgps?\b|general practitioners?", _c("specialty", "text", "==", "gp")),
    (r"gastroenterologists?", _c("specialty", "text", "==", "gastroenterology")),
    (r"hepatologists?", _c("specialty", "text", "==", "hepatology")),
    (r"paediatric prescribers?|prescribe for children", _c("paediatric_prescriber", "yes_no", "yes", None)),
    (r"care[- ]home", _c("care_home_prescriber", "yes_no", "yes", None)),
    (r"endoscopy nurses?", _c("hcp_role", "text", "==", "endoscopy_nurse")),
    (r"\btier a\b|high[- ]potential", _c("tier", "text", "==", "A")),
    (r"\btier b\b", _c("tier", "text", "==", "B")),
    (r"\btier c\b", _c("tier", "text", "==", "C")),
    (r"\bunaware\b|\bcuriosity\b", _c("stage", "text", "==", "curiosity")),
    (r"(?<!un)\baware\b|considering|\bconsideration\b", _c("stage", "text", "==", "consideration")),
    (r"occasional (?:\w+ )?(?:users?|prescribers?)|trying it|\bexperience stage\b", _c("stage", "text", "==", "experience")),
    (r"regular (?:\w+ )?(?:users?|prescribers?)|loyal", _c("stage", "text", "==", "loyalty")),
    (r"advocates?\b", _c("stage", "text", "==", "advocacy")),
]
CHANNELS = [(r"remote call|video call|phone call|\bcall\b", "remote_call"), (r"rep email|email from the rep", "rep_email"),
            (r"account visit|kam visit", "kam_visit"), (r"kam brief|brief the kam|account brief|\bkam\b", "kam_brief"),
            (r"rep visit|\bvisit\b|\bsee them\b", "rep_visit"), (r"webinar", "webinar"), (r"\bemail\b|\bsend\b", "marketing_email")]
THEMES = [(r"efficacy", "efficacy"), (r"patient case|case study", "patient_case"), (r"dosing for nurs|nursing", "dosing_nursing"),
          (r"dosing|dose", "dosing"), (r"real[- ]world|\brwe\b", "real_world_evidence"), (r"cost|economic|budget", "economic_evidence"),
          (r"recording|slides from", "event_follow_up"), (r"safety|tolerab", "safety"), (r"peer|colleague", "peer_experience"),
          (r"cleansing|preparation quality", "cleansing_quality"), (r"formulary|access", "access"),
          (r"trial|clinical evidence|study data", "clinical_evidence"), (r"guideline", "guideline_update"),
          (r"paediatric", "paediatric"), (r"patient instruction", "patient_instructions"), (r"introduc", "introduction")]
BRANDS = [(r"movicol", "Movicol"), (r"plenvu|moviprep|bowel prep|endoscopy unit", "Plenvu_Moviprep"), (r"xifaxan|hepatic", "Xifaxan")]
MARKETS = [(r"\buk\b|united kingdom|britain|england", "UK"), (r"\bde\b|germany|german", "DE")]
UNSUPPORTED = [(r"competitor'?s? (?:symposium|event|meeting)", "competitor event attendance"),
               (r"social media|linkedin|twitter", "social media activity"), (r"patient complaint", "patient complaints")]
CHANNEL_WORDS = {"rep_visit": "rep visit", "remote_call": "remote call", "rep_email": "rep email", "marketing_email": "email",
                 "webinar": "webinar invitation", "kam_brief": "KAM brief", "kam_visit": "account visit"}
DEFAULT_THEME = {"webinar": "clinical_evidence", "kam_brief": "dosing_nursing", "remote_call": "clinical_evidence"}


def _first(pairs, text):
    for pat, val in pairs:
        if re.search(pat, text):
            return val
    return None


def parse(text: str) -> dict:
    """A typed sentence as a rule studio form, with what was recognised and what was not."""
    t = " " + text.lower().strip() + " "
    conds, reasons, recognised, risk = [], [], [], False
    for pat, build, reason, is_risk in SIGNALS:
        m = re.search(pat, t)
        if m and build(m):
            conds += build(m)
            reasons.append(reason)
            recognised.append(m.group(0).strip())
            risk = risk or is_risk
            t = t.replace(m.group(0), " ")
    for pat, cond in PEOPLE:
        m = re.search(pat, t)
        if m and not any(c["column"] == cond["column"] for c in conds):
            conds.append(cond)
            recognised.append(m.group(0).strip())
    # Split the sentence at the action verb so the content theme is read from the action part.
    act = re.split(r"\b(?:send|invite|have the rep|brief|book|schedule|offer)\b", t, maxsplit=1)
    action_part = act[1] if len(act) > 1 else t
    channel = _first(CHANNELS, action_part) or _first(CHANNELS, t)
    if re.search(r"\binvite\b", t) and "webinar" in t:
        channel = "webinar"
    theme = _first(THEMES, action_part) or DEFAULT_THEME.get(channel or "")
    if re.search(r"never had|not (?:yet )?received|has not had|have not had|who have never", t) and theme:
        conds.append({"column": "__theme__", "kind": "theme", "op": "no", "value": theme})
        reasons.append(f"has not received the {theme.replace('_', ' ')} asset")
    brand = _first(BRANDS, " " + text.lower() + " ")
    if brand is None and theme == "paediatric":
        brand = "Movicol"
    markets = [v for p, v in MARKETS if re.search(p, " " + text.lower() + " ")]
    if re.search(r"both markets|all markets", text.lower()):
        markets = ["UK", "DE"]
    timing = "within_10_working_days" if re.search(r"within (?:10|ten) (?:working )?days|within two weeks", t) else \
        "next_month" if "next month" in t else "this_week"
    reason = "; ".join(r for r in reasons if r)
    if reason:
        reason = reason[0].upper() + reason[1:]
        if channel:
            full = reason + f": {CHANNEL_WORDS.get(channel, channel)}" + (f", {theme.replace('_', ' ')}" if theme else "")
            reason = full if len(full) <= 140 else reason + f": {CHANNEL_WORDS.get(channel, channel)}"
    unsupported = [label for pat, label in UNSUPPORTED if re.search(pat, text.lower())]
    form = {"brand": brand or "", "markets": markets, "trigger_type": "risk" if risk else "opportunity", "family": "",
            "channel": channel or "", "content_theme": theme or "", "timing": timing, "priority": 70 if risk else 60,
            "reason_template": reason[:140], "note": f"Written as: {text.strip()}",
            "conditions": conds or [{"column": "", "kind": "", "op": "", "value": ""}]}
    return {"form": form, "recognised": recognised, "unsupported": unsupported}


# Ready-made prompts for the rule studio (each parses to a complete or nearly complete form).
EXAMPLES = [
    "If a Movicol brick drops more than 8% and the GP has not seen a rep in two months, send a rep visit with the efficacy asset",
    "If a Movicol GP in the UK opened two emails but never clicked, send a rep email with the patient case",
    "If a Movicol GP in both markets clicked an email and has had no rep visit for 30 days, book a remote call with the trial data",
    "If a Plenvu endoscopy unit in the UK sees procedures rise 15% in a quarter, brief the KAM with the dosing for nursing pack",
    "If a gastroenterologist in Germany attended the Plenvu webinar, have the rep visit with dosing within 10 working days",
    "If a regular Movicol prescriber in the UK has not responded for six weeks and the brick drops 5%, send a rep visit with real world evidence",
    "Send the paediatric asset to paediatric prescribers in the UK who have never had it",
    "If a Xifaxan hepatologist in both markets registered but missed the webinar, send the recording by email",
]
