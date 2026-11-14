"""Learning from the field: acceptance by rule, and the engine's proposals (feedback rule R134).

R134 flags a rule whose suggestions reps accepted less than 40% of the time in the last 30 days, with at least
20 suggestions. For a rule with a numeric threshold, the proposal tightens it by a quarter, in the direction that
makes the rule fire less often (for example "at least 7 days" becomes "at least 9 days"). The brand team approves
a proposal in the feedback screen, which saves it as a new rule version.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd

from nba import data, spec
from nba.rules import versions
from nba.rules.catalogue import by_id

TIGHTEN = 1.25


def acceptance_by_rule(data_dir: Path | None = None, upto: pd.Timestamp | None = None,
                       days: int | None = None) -> pd.DataFrame:
    """Suggestions, accepted, dismissed and acceptance rate per rule (optionally only the last `days`)."""
    s = data.read_table("suggestion_vod", data_dir)
    if s.empty:
        return pd.DataFrame(columns=["rule_id", "suggestions", "accepted", "dismissed", "acceptance_rate",
                                     "top_dismiss_reason"])
    s["suggested_date"] = pd.to_datetime(s.suggested_date)
    upto = upto or s.suggested_date.max()
    s = s[s.suggested_date <= upto]
    if days:
        s = s[s.suggested_date > upto - pd.Timedelta(days=days)]
    s = s.assign(rule_id=s.rule_ids.str.split("|")).explode("rule_id")
    g = s.groupby("rule_id").agg(suggestions=("id", "size"),
                                 accepted=("status", lambda x: int((x == "accepted").sum())),
                                 dismissed=("status", lambda x: int((x == "dismissed").sum())),
                                 top_dismiss_reason=("dismiss_reason", lambda x: x.dropna().mode().iloc[0]
                                                     if x.notna().any() else None))
    g["acceptance_rate"] = (g.accepted / g.suggestions).round(3)
    return g.reset_index()


def triggers_by_rule(data_dir: Path | None = None, upto: pd.Timestamp | None = None, days: int = 30) -> pd.Series:
    """Triggers raised per rule in the saved weekly runs (test territories)."""
    root = Path(data_dir) if data_dir else spec.data_dir()
    files = sorted((root / "runs").glob("week_*/triggers.parquet"))
    if not files:
        return pd.Series(dtype=int)
    t = pd.concat([pd.read_parquet(f, columns=["rule_id", "run_week"]) for f in files])
    t["run_week"] = pd.to_datetime(t.run_week)
    upto = upto or t.run_week.max()
    t = t[(t.run_week <= upto) & (t.run_week > upto - pd.Timedelta(days=days))]
    return t.groupby("rule_id").size()


def _tightened(rule, overrides: dict) -> dict:
    """New parameter values that make the rule fire less often."""
    params = {**rule.parameters, **overrides.get(rule.id, {})}
    out = {}
    for name, value in params.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        m = re.search(r"(>=|>|<=|<)\s*(-?)\{" + name + r"\}", rule.condition_template)
        if not m:
            continue
        op, minus = m.groups()
        raises = op.startswith(">") or minus == "-"          # bigger number = stricter
        new = value * TIGHTEN if raises else value / TIGHTEN
        new = math.ceil(new) if raises else math.floor(new)
        if isinstance(value, float):
            new = round(value * TIGHTEN if raises else value / TIGHTEN, 2)
        if new != value:
            out[name] = new
    return out


def proposals(data_dir: Path | None = None, upto: pd.Timestamp | None = None) -> pd.DataFrame:
    """Rules the engine proposes to change, with the proposed parameters and the reason."""
    r134 = by_id()["R134"]
    acc = acceptance_by_rule(data_dir, upto, days=30)
    cols = ["rule_id", "family", "triggers", "suggestions", "acceptance_rate", "top_dismiss_reason", "current", "proposed",
            "reason", "condition"]
    if acc.empty or not r134.enabled:
        return pd.DataFrame(columns=cols)
    table = acc.rename(columns={"acceptance_rate": "rule_accept_rate_30d"})
    table["rule_triggers_30d"] = table.rule_id.map(triggers_by_rule(data_dir, upto, days=30)).fillna(0).astype(int)
    flagged = table[r134.condition().evaluate(table)]
    overrides = versions.current_overrides(data_dir)
    rules = by_id()
    rows = []
    for _, f in flagged.iterrows():
        rule = rules.get(f.rule_id)
        if rule is None:
            continue
        current = {**rule.parameters, **overrides.get(rule.id, {})}
        new = _tightened(rule, overrides)
        rate = f.rule_accept_rate_30d
        rows.append({"rule_id": rule.id, "family": rule.family, "suggestions": int(f.suggestions),
                     "triggers": int(f.rule_triggers_30d),
                     "acceptance_rate": rate, "top_dismiss_reason": f.top_dismiss_reason,
                     "current": {k: current[k] for k in new} or current, "proposed": new,
                     "reason": f"Rule {rule.id}: {int(f.rule_triggers_30d)} triggers in 30 days, reps accepted "
                               f"{rate:.0%} of its {int(f.suggestions)} suggestions"
                               + (f", most dismissals '{f.top_dismiss_reason.replace('_', ' ')}'"
                                  if f.top_dismiss_reason else "")
                               + (": propose " + ", ".join(f"{k} {current[k]} -> {v}" for k, v in new.items())
                                  if new else ": propose pausing the rule until the brand team reviews it"),
                     "condition": rule.condition_template})
    return pd.DataFrame(rows, columns=cols)


def approve(rule_id: str, data_dir: Path | None = None) -> dict:
    """Save the proposal as a new rule version: tightened parameters, or paused if it has none to tighten."""
    p = proposals(data_dir)
    row = p[p.rule_id == rule_id]
    if row.empty:
        raise KeyError(f"No proposal for {rule_id}")
    r = row.iloc[0]
    return versions.save(rule_id, r.proposed or {}, note=r.reason, data_dir=data_dir, pause=not r.proposed)
