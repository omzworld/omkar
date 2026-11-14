"""The column dictionary: which columns a rule may use, read from spec/schemas/feature_columns.md.

Each section of that file becomes a group. Three groups are special:
- "theme functions" lists functions, not columns;
- "candidate-level columns" are built per candidate action by the constraints/optimiser step;
- every other group is built by nba.features, one row per account per week.
"""
from __future__ import annotations

import re
from functools import lru_cache

from nba import spec

CANDIDATE = "candidate-level columns"
FUNCTIONS = "theme functions"
DISCOVERY_WRITTEN = {"propensity_to_move_8w", "look_alike_similarity"}   # written back by discover, not features
PER_RULE = {"rule_accept_rate_30d", "rule_triggers_30d"}                 # one value per rule, built by feedback

# Allowed values for columns compared with text in rule conditions, so the linter can catch typos.
VALUES = {
    "tier": ["A", "B", "C"], "unit_tier": ["A", "B", "C"],
    "channel_lean": ["digital", "rep", "default"],
    "age_band": ["under_40", "40_to_54", "55_plus"],
    "stage": ["curiosity", "consideration", "experience", "loyalty", "advocacy"],
    "prev_stage": ["curiosity", "consideration", "experience", "loyalty", "advocacy"],
    "trigger_type": ["risk", "opportunity"],
    "hcp_status": ["active", "inactive"],
    "asset_status": ["approved", "expired", "withdrawn", "in_review"],
    "formulary_status_changed": ["added", "removed", "restricted", "none"],
    "survey_interest": ["access", "efficacy", "dosing", "safety", "none"],
}
FROM_DATASETS = {  # column -> (table, field) whose list of values applies
    "account_type": ("account_vod", "account_type"), "hcp_type": ("account_vod", "hcp_type"),
    "hcp_role": ("account_vod", "hcp_role"), "specialty": ("account_vod", "specialty_1_vod"),
    "practice_type": ("hcp_master_opendata", "practice_type"), "expert_status": ("hcp_master_opendata", "expert_status"),
    "rep_visit_next_step": ("call2_vod", "next_step"), "last_dismiss_reason": ("suggestion_vod", "dismiss_reason"),
    "event_type": ("event_attendee_vod", "event_type"),
}


@lru_cache
def groups() -> dict[str, list[str]]:
    """{section title (lower case): [names in order]}."""
    text = (spec.SPEC / "schemas" / "feature_columns.md").read_text(encoding="utf-8")
    out, current = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            current = re.sub(r"\s*\(.*\)\s*$", "", line[3:]).strip().lower()
            out[current] = []
            continue
        if current is None or not line.strip():
            continue
        clean = re.sub(r"\([^()]*\)", "", line)            # drop notes in brackets, incl. function arguments
        clean = re.sub(r"->\s*\w+", "", clean)             # drop return types of functions
        for item in re.split(r"[,;]", clean):
            words = item.split()
            if words and re.fullmatch(r"[a-z_][a-z0-9_]*", words[0]) and words[0] not in out[current]:
                out[current].append(words[0])
    return out


def functions() -> set[str]:
    return set(groups()[FUNCTIONS])


def candidate_columns() -> list[str]:
    return groups()[CANDIDATE]


def account_columns() -> list[str]:
    """Columns nba.features builds: everything except functions and candidate-level columns."""
    seen = []
    for g, names in groups().items():
        if g in (FUNCTIONS, CANDIDATE):
            continue
        seen += [n for n in names if n not in seen]
    return seen


def all_columns() -> set[str]:
    return set(account_columns()) | set(candidate_columns())


@lru_cache
def allowed_values() -> dict[str, list]:
    vals = dict(VALUES)
    for col, (table, field) in FROM_DATASETS.items():
        decl = spec.datasets()[table]["fields"][field]
        vals[col] = decl["values"]
    channels = sorted(set(spec.constraint_table("country_code").channel) | {"kam_visit", "msl", "social", "speaker_programme", "advisory_board"})
    vals["channel"] = vals["last_touch_channel"] = channels
    return vals
