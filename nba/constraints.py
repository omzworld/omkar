"""The constraints engine: allowed, delayed or blocked for every candidate action, naming the constraint.

Order (spec/constraints/README.md):
1. Block rules first: consent, country code, no-promotion, asset status. The highest-priority block wins and
   evaluation stops for that candidate.
2. Delay rules next: cadence, caps. All that apply are recorded; the one with the latest release date is named.
3. Anything else is allowed.

Two sources of constraints, one verdict:
- the constraint rules in the catalogue (engine: constraints), which hold the logic and the brand-editable numbers;
- the compliance tables consent_rules.csv and country_code.csv, which hold per market and channel requirements.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nba import spec
from nba.features import Features
from nba.rules.catalogue import Rule, load
from nba.rules.engine import reasons

CONSENT_COLUMN = {"email_opt_in": "consent_email", "double_opt_in": "consent_double_opt_in",
                  "remote_call_opt_in": "consent_remote", "digital_tracking": "consent_digital_tracking"}


def constraint_rules(overrides: dict | None = None) -> list[Rule]:
    overrides = overrides or {}
    rules = [r for r in load(enabled_only=True) if r.engine == "constraints"]
    rules = [r.with_parameters(**overrides[r.id]) if r.id in overrides else r for r in rules]
    return sorted(rules, key=lambda r: (-r.priority, r.id))


def _csv_checks(c: pd.DataFrame) -> list[tuple[str, str, pd.Series, pd.Series]]:
    """(constraint_id, kind, fires, reason) from the compliance tables."""
    consent = spec.constraint_table("consent_rules")
    consent = consent[consent.consent_required.astype(str).str.lower() == "true"]
    need = c[["market", "channel"]].merge(consent, on=["market", "channel"], how="left")
    ok = pd.Series(True, index=c.index)
    for ctype, col in CONSENT_COLUMN.items():
        rows = (need.consent_type == ctype).to_numpy()
        ok[rows] = c.loc[rows, col].astype(bool)
    consent_fail = ~ok
    consent_reason = "Blocked: " + need.channel.str.replace("_", " ") + " needs " \
        + need.consent_type.fillna("").str.replace("_", " ") + " consent in " + c.market

    country = spec.constraint_table("country_code")
    cc = c[["market", "channel"]].merge(country, on=["market", "channel"], how="left")
    not_allowed = (cc.allowed.astype(str).str.lower() == "false").to_numpy()
    cap = cc.max_touches_per_month.to_numpy()
    over_cap = (cap > 0) & (c.touches_this_month_channel.to_numpy() >= cap)
    return [
        ("consent_rules.csv", "block", pd.Series(consent_fail.to_numpy(), index=c.index), consent_reason),
        ("country_code.csv", "block", pd.Series(not_allowed, index=c.index),
         "Blocked: " + c.channel.str.replace("_", " ") + " is not allowed in " + c.market),
        ("country_code.csv", "delay", pd.Series(over_cap, index=c.index),
         "Delayed: " + c.channel.str.replace("_", " ") + " monthly limit of " + pd.Series(cap, index=c.index)
         .fillna(0).astype(int).astype(str) + " reached in " + c.market),
    ]


def evaluate(c: pd.DataFrame, feats: Features, overrides: dict | None = None) -> pd.DataFrame:
    """Add verdict, constraint_id, constraint_reason, delayed_until and all_constraints to each candidate."""
    if c.empty:
        return c
    ctx = feats.context()
    n = len(c)
    verdict = np.full(n, "allowed", dtype=object)
    cid = np.full(n, None, dtype=object)
    why = np.full(n, None, dtype=object)
    release = np.full(n, pd.NaT, dtype=object)
    hits = [[] for _ in range(n)]
    next_week = feats.as_of + pd.Timedelta(days=7)
    next_month = (feats.as_of + pd.offsets.MonthBegin(1)).normalize()

    checks = []
    for rule in constraint_rules(overrides):
        kind = "block" if rule.channel == "block" else "delay"
        scope = c.market.isin(rule.markets)
        fires = pd.Series(False, index=c.index)
        if scope.any():
            fires[scope] = rule.condition().evaluate(c[scope], ctx)
        checks.append((rule.id, kind, fires, rule, rule.priority))
    for constraint_id, kind, fires, reason in _csv_checks(c):
        checks.append((constraint_id, kind, fires, reason, 100 if kind == "block" else 90))

    for kind in ("block", "delay"):
        for constraint_id, k, fires, source, _prio in sorted((x for x in checks if x[1] == kind), key=lambda x: -x[4]):
            idx = np.flatnonzero(fires.to_numpy())
            if not len(idx):
                continue
            text = reasons(source, c.iloc[idx]) if isinstance(source, Rule) else list(source.iloc[idx])
            until = next_month if isinstance(source, Rule) and source.timing == "next_month" else next_week
            for i, t in zip(idx, text):
                hits[i].append(constraint_id)
                if kind == "block" and verdict[i] != "blocked":
                    verdict[i], cid[i], why[i] = "blocked", constraint_id, t
                elif kind == "delay" and verdict[i] == "allowed":
                    verdict[i], cid[i], why[i], release[i] = "delayed", constraint_id, t, until
                elif kind == "delay" and verdict[i] == "delayed" and until > release[i]:
                    cid[i], why[i], release[i] = constraint_id, t, until

    out = c.copy()
    out["verdict"], out["constraint_id"], out["constraint_reason"] = verdict, cid, why
    out["delayed_until"] = pd.to_datetime(pd.Series(release, index=c.index))
    out["all_constraints"] = ["|".join(h) for h in hits]
    return out


def substitute_allowed(c: pd.DataFrame, feats: Features, overrides: dict | None = None) -> pd.Series:
    """Would the substitute channel (e.g. a rep email instead of a visit) pass the constraints?"""
    has = c.substitute_channel.notna()
    ok = pd.Series(False, index=c.index)
    if not has.any():
        return ok
    sub = c[has].copy()
    sub["channel"] = sub.substitute_channel
    from nba.candidates import _assets   # same asset choice as a normal candidate on that channel
    sub = _assets(sub.drop(columns=["asset_market", "asset_id", "asset_status", "asset_language", "key_messages",
                                    "days_to_asset_expiry"]), feats.as_of, None).set_index(sub.index)
    sub["touches_this_month_channel"] = 0
    ok[has] = evaluate(sub, feats, overrides).verdict.eq("allowed").to_numpy()
    return ok


def summary(c: pd.DataFrame) -> pd.DataFrame:
    """Blocked and delayed demand by constraint, with an example reason (demo scene 3)."""
    held = c[c.verdict != "allowed"]
    g = held.groupby(["verdict", "constraint_id"]).agg(candidates=("candidate_id", "size"),
                                                       physicians=("hcp_id", "nunique"),
                                                       example=("constraint_reason", "first")).reset_index()
    return g.sort_values(["verdict", "candidates"], ascending=[True, False])
