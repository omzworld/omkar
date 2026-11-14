"""The rules engine: run every enabled trigger rule over the week's feature table and raise triggers.

A trigger is "this account needs this action, for this reason". It is not yet a decision: the constraints
engine (step 3) then says whether it is allowed, delayed or blocked, and the optimiser decides what is sent.
Think of each rule as a saved WHERE clause; a trigger is one row that matched.
"""
from __future__ import annotations

import pandas as pd

from nba.features import Features
from nba.rules.catalogue import PLACEHOLDER, Rule, load

TRIGGER_COLUMNS = ["trigger_id", "run_week", "hcp_id", "market", "territory_id", "account_type", "brand", "rule_id",
                   "rule_ids", "family", "trigger_type", "channel", "content_theme", "timing", "priority", "reason",
                   "origin"]


def trigger_rules(overrides: dict | None = None, extra: list[Rule] | None = None) -> list[Rule]:
    """Enabled rules that raise triggers, with any parameter overrides from the rule studio applied."""
    overrides = overrides or {}
    rules = [r for r in load(enabled_only=True) + (extra or []) if r.raises_triggers]
    return [r.with_parameters(**overrides[r.id]) if r.id in overrides else r for r in rules]


def applies_to(rule: Rule, table: pd.DataFrame) -> pd.Series:
    """Rows in the rule's markets and, for a brand rule, accounts of that brand."""
    mask = table.market.isin(rule.markets)
    if rule.brand != "all":
        mask &= table.brand == rule.brand
    return mask


def fired(rule: Rule, feats: Features) -> pd.Series:
    """True for each account the rule fires for this week."""
    t = feats.table
    scope = applies_to(rule, t)
    hit = pd.Series(False, index=t.index)
    if scope.any():
        hit[scope] = rule.condition().evaluate(t[scope], feats.context())
    return hit


def _fmt(value, before: str) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "unknown"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        if before.rstrip().endswith(("down", "fell", "dropped")):
            value = abs(value)
        if isinstance(value, float):
            if abs(value) < 1 and value != 0:
                return f"{value:.2f}"
            return f"{value:.1f}".removesuffix(".0")
        return str(value)
    return str(value).replace("_", " ")


def reasons(rule: Rule, rows: pd.DataFrame) -> list[str]:
    """Fill the rule's reason template from its parameters and each row's columns."""
    template = rule.reason_template
    out = []
    for _, row in rows.iterrows():
        def sub(m):
            name = m.group(1)
            before = template[:m.start()]
            if name in rule.parameters:
                return _fmt(rule.parameters[name], before)
            if name == "rule_id":
                return rule.id
            return _fmt(row.get(name), before)
        out.append(PLACEHOLDER.sub(sub, template))
    return out


def raise_triggers(feats: Features, overrides: dict | None = None, extra: list[Rule] | None = None) -> pd.DataFrame:
    t = feats.table
    frames = []
    for rule in trigger_rules(overrides, extra):
        rows = t[fired(rule, feats)]
        if rows.empty:
            continue
        frames.append(pd.DataFrame({
            "trigger_id": [f"W{feats.week:02d}-{rule.id}-{h}" for h in rows.hcp_id],
            "run_week": feats.as_of, "hcp_id": rows.hcp_id.to_numpy(), "market": rows.market.to_numpy(),
            "territory_id": rows.territory_id.to_numpy(), "account_type": rows.account_type.to_numpy(),
            "brand": rows.brand.to_numpy(), "rule_id": rule.id, "rule_ids": rule.id, "family": rule.family,
            "trigger_type": rule.trigger_type, "channel": rule.channel, "content_theme": rule.content_theme,
            "timing": rule.timing, "priority": rule.priority, "reason": reasons(rule, rows), "origin": "rule"}))
    if not frames:
        return pd.DataFrame(columns=TRIGGER_COLUMNS)
    return pd.concat(frames, ignore_index=True)[TRIGGER_COLUMNS]


def summary(triggers: pd.DataFrame) -> pd.DataFrame:
    """Triggers raised per rule and market, with one example reason."""
    rules = {r.id: r for r in trigger_rules()}
    g = triggers.groupby(["rule_id", "market"]).size().unstack(fill_value=0)
    g["total"] = g.sum(axis=1)
    g["family"] = [rules[r].family if r in rules else "" for r in g.index]
    g["action"] = [f"{rules[r].channel} / {rules[r].content_theme}" if r in rules else "" for r in g.index]
    g["example reason"] = triggers.groupby("rule_id").reason.first()
    return g.reset_index()


def compare(before: pd.DataFrame, after: pd.DataFrame, rule_id: str) -> dict:
    """Which accounts a rule change adds or removes."""
    b = set(before.loc[before.rule_id == rule_id, "hcp_id"])
    a = set(after.loc[after.rule_id == rule_id, "hcp_id"])
    return {"before": len(b), "after": len(a), "added": sorted(a - b), "removed": sorted(b - a)}
