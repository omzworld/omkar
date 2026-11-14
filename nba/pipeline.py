"""One weekly run of the engine: features -> rules -> candidates -> constraints -> optimiser -> summary.

Outputs are saved under data/runs/week_NN/ so later steps (delivery, feedback, the web screens) read them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from nba import candidates, constraints, features, optimiser, spec
from nba.rules import engine


@dataclass
class WeekResult:
    week: int
    feats: features.Features
    triggers: pd.DataFrame
    decisions: pd.DataFrame      # one row per candidate: verdict, scores, status, reasons
    dial: float

    @property
    def sent(self) -> pd.DataFrame:
        return self.decisions[self.decisions.status.isin(["sent", "substituted"])]


def run_week(week: int, overrides: dict | None = None, dial: float = 1.0, data_dir: Path | None = None,
             rebuild_features: bool = False, save: bool = True) -> WeekResult:
    try:
        feats = features.build(week, data_dir) if rebuild_features else features.load_snapshot(week, data_dir)
    except FileNotFoundError:
        feats = features.build(week, data_dir)
    triggers = engine.raise_triggers(feats, overrides)
    c = candidates.build(triggers, feats, data_dir)
    c = constraints.evaluate(c, feats, overrides)
    c["substitute_allowed"] = constraints.substitute_allowed(c, feats, overrides)
    c = optimiser.score(c, feats, data_dir)
    c = optimiser.select(c, optimiser.capacity(feats.as_of, data_dir), dial=dial)
    result = WeekResult(week, feats, triggers, c, dial)
    if save:
        d = (Path(data_dir) if data_dir else spec.data_dir()) / "runs" / f"week_{week:02d}"
        d.mkdir(parents=True, exist_ok=True)
        triggers.to_parquet(d / "triggers.parquet", index=False)
        out = c.drop(columns=["resource"]).astype({"all_constraints": str})
        out.to_parquet(d / "decisions.parquet", index=False)
    return result


def _reason_group(text: str | None) -> str:
    if not text:
        return ""
    for key, label in [("another action", "a better action for the same physician"),
                       ("slots left", "capacity full"), ("vacant", "vacant territory"),
                       ("not positive", "expected return not positive"), ("sent as", "substituted")]:
        if key in text:
            return label
    return "held by a constraint"


def summary(r: WeekResult) -> dict[str, pd.DataFrame | dict]:
    d = r.decisions
    sent = r.sent
    headline = {
        "week": r.week, "run date": f"{r.feats.as_of:%d %b %Y}", "rules-to-score dial": r.dial,
        "triggers raised": len(r.triggers), "physicians and accounts with a trigger": r.triggers.hcp_id.nunique(),
        "candidate actions": len(d), "allowed": int((d.verdict == "allowed").sum()),
        "delayed": int((d.verdict == "delayed").sum()), "blocked": int((d.verdict == "blocked").sum()),
        "actions sent": len(sent), "of which substituted to a cheaper channel": int((d.status == "substituted").sum()),
        "total expected return (EUR)": round(float(sent.final_return.sum()), 0),
        "total cost of touches sent (EUR)": round(float(sent.final_channel.map(
            spec.assumptions()["touch_cost"]).sum()), 0),
    }
    by_channel = sent.groupby("final_channel").agg(sent=("candidate_id", "size"),
                                                   expected_return_eur=("final_return", "sum"),
                                                   average_chance=("probability_of_response", "mean")).round(2)
    not_sent = d[(d.status == "not_sent") & (d.verdict == "allowed")]
    why = not_sent.not_sent_reason.map(_reason_group).value_counts().rename_axis("reason").reset_index(name="candidates")
    by_rule = d.groupby("rule_id").agg(candidates=("candidate_id", "size"),
                                       allowed=("verdict", lambda v: int((v == "allowed").sum())),
                                       sent=("status", lambda s: int(s.isin(["sent", "substituted"]).sum())),
                                       expected_return_eur=("final_return", "sum")).round(0).reset_index()
    return {"headline": headline, "constraints": constraints.summary(d), "by_channel": by_channel.reset_index(),
            "not_sent": why, "by_rule": by_rule, "chance_tiers": sent.chance_tier.value_counts().to_dict()}


def top_list(r: WeekResult, n: int = 15) -> pd.DataFrame:
    """The ranked list: what is sent, highest expected return first, with reasons."""
    s = r.sent.sort_values("final_return", ascending=False)
    return s[["hcp_id", "territory_id", "final_channel", "content_theme", "asset_id", "probability_of_response",
              "chance_tier", "value_of_response", "final_return", "rule_ids", "reason"]].head(n)
