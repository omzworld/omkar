"""The rules catalogue: load rules, fill in their parameters, and lint them.

A rule's condition may contain parameters in braces, e.g. `brick_volume_qoq_pct <= -{decline_pct}`. The
values come from the rule's `parameters` block; the rule studio can override them without editing the YAML.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from nba import columns, spec
from nba.rules.expr import Condition, ConditionError

PLACEHOLDER = re.compile(r"\{(\w+)\}")
TRIGGER_TYPES = ("risk", "opportunity")
# Actions that a later engine resolves into a concrete channel or theme.
ACTION_CHANNELS = {"next_best", "alternate_channel", "as_chosen", "block", "delay", "prefer", "downgrade",
                   "capacity", "drop", "floor", "adjust", "propose"}


@dataclass
class Rule:
    id: str
    family: str
    engine: str
    brand: str
    markets: list
    trigger_type: str
    enabled: bool
    condition_template: str
    channel: str
    content_theme: str
    timing: str
    priority: int
    reason_template: str
    parameters: dict = field(default_factory=dict)
    owner: str = ""
    notes: str = ""

    @classmethod
    def from_record(cls, r: dict) -> "Rule":
        a = r["action"]
        return cls(id=r["id"], family=r["family"], engine=r["engine"], brand=r["brand"], markets=list(r["markets"]),
                   trigger_type=r["trigger_type"], enabled=bool(r["enabled_at_launch"]),
                   condition_template=r["condition"], channel=a["channel"], content_theme=a["content_theme"],
                   timing=a["timing"], priority=int(r["priority"]), reason_template=r["reason_template"],
                   parameters=dict(r.get("parameters") or {}), owner=r.get("owner", ""), notes=r.get("notes", ""))

    @property
    def raises_triggers(self) -> bool:
        return self.engine == "rules" and self.trigger_type in TRIGGER_TYPES

    def with_parameters(self, **overrides) -> "Rule":
        unknown = set(overrides) - set(self.parameters)
        if unknown:
            raise KeyError(f"{self.id} has no parameter {sorted(unknown)}; it has {sorted(self.parameters)}")
        return Rule(**{**self.__dict__, "parameters": {**self.parameters, **overrides}})

    @property
    def condition_text(self) -> str:
        """The condition with parameter values filled in."""
        def fill(m):
            name = m.group(1)
            if name not in self.parameters:
                raise ConditionError(f"{self.id}: parameter {{{name}}} has no value in the parameters block")
            v = self.parameters[name]
            return repr(v) if isinstance(v, str) else str(v)
        return PLACEHOLDER.sub(fill, self.condition_template)

    def condition(self) -> Condition:
        return Condition(self.condition_text)


def load(enabled_only: bool = False) -> list[Rule]:
    rules = [Rule.from_record(r) for r in spec.catalogue()["rules"]]
    return [r for r in rules if r.enabled] if enabled_only else rules


def by_id() -> dict[str, Rule]:
    return {r.id: r for r in load()}


def lint(rules: list[Rule] | None = None) -> list[str]:
    """Every problem in the catalogue, as plain sentences. Empty list = clean."""
    rules = load() if rules is None else rules
    known = columns.all_columns()
    account_cols = set(columns.account_columns())
    funcs = columns.functions()
    values = columns.allowed_values()
    cat = spec.catalogue()
    brands, markets = set(cat["brand_codes"]), set(cat["markets"])
    problems = []
    seen = set()
    for r in rules:
        where = f"{r.id} ({r.family})"
        if r.id in seen:
            problems.append(f"{where}: duplicate rule id")
        seen.add(r.id)
        if r.brand not in brands:
            problems.append(f"{where}: unknown brand '{r.brand}'")
        if set(r.markets) - markets:
            problems.append(f"{where}: unknown market {sorted(set(r.markets) - markets)}")
        try:
            cond = r.condition()
        except ConditionError as e:
            problems.append(f"{where}: {e}")
            continue
        for col in sorted(cond.columns() - known):
            problems.append(f"{where}: column '{col}' is not in feature_columns.md")
        for fn in sorted(cond.functions() - funcs):
            problems.append(f"{where}: function '{fn}' is not a theme function")
        if r.raises_triggers:
            for col in sorted(cond.columns() - account_cols - columns.PER_RULE):
                if col in known:
                    problems.append(f"{where}: trigger rule uses candidate-level column '{col}', "
                                    "which does not exist until a channel is chosen")
            if r.channel not in values["channel"] and r.channel not in ACTION_CHANNELS:
                problems.append(f"{where}: unknown action channel '{r.channel}'")
        for col, vals in cond.text_comparisons():
            allowed = values.get(col)
            if allowed:
                for v in vals:
                    if v not in allowed:
                        problems.append(f"{where}: '{v}' is not a value of {col} (allowed: {', '.join(allowed)})")
        for name in PLACEHOLDER.findall(r.reason_template):
            if name not in r.parameters and name not in known and name not in funcs and name not in ("rule_id", "market"):
                problems.append(f"{where}: reason mentions '{{{name}}}', which is neither a parameter nor a column")
    return problems


def table(rules: list[Rule] | None = None) -> pd.DataFrame:
    rules = load() if rules is None else rules
    return pd.DataFrame([{"rule_id": r.id, "family": r.family, "engine": r.engine, "brand": r.brand,
                          "trigger_type": r.trigger_type, "enabled": r.enabled, "channel": r.channel,
                          "content_theme": r.content_theme, "condition": r.condition_text,
                          "reason_template": r.reason_template} for r in rules])
