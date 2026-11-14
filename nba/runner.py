"""The pilot runner: `nba run --weeks 26`.

Starts from the end of the 24-month history (the baseline copy written by `nba synth`), then for each week:
features -> rules -> constraints -> optimiser (test territories) -> delivery -> feedback simulation.
Everything is deterministic from the seed, so a replay reproduces every number.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from nba import data, delivery, feedback, features, pipeline, spec


def reset(data_dir: Path | None = None) -> None:
    """Put every table and the simulator back to the end of the history."""
    root = Path(data_dir) if data_dir else spec.data_dir()
    base = root / "baseline"
    if not base.exists():
        raise FileNotFoundError("No baseline found: run `nba synth` first.")
    for p in base.glob("*.parquet"):
        shutil.copy2(p, root / p.name)
    for sub in ("runs", "snapshots"):
        shutil.rmtree(root / sub, ignore_errors=True)
    shutil.copy2(base / data.HIDDEN / "simulator.pkl", root / data.HIDDEN / "simulator.pkl")


def completed_weeks(data_dir: Path | None = None) -> int:
    p = (Path(data_dir) if data_dir else spec.data_dir()) / "runs" / "summary.parquet"
    return int(pd.read_parquet(p).week.max()) if p.exists() else 0


def run(weeks: int, dial: float = 1.0, overrides: dict | None = None, data_dir: Path | None = None,
        log=print, fresh: bool = True, progress=None) -> pd.DataFrame:
    """Run the pilot up to week `weeks`. fresh=True starts again from week 1; fresh=False carries on from the
    last completed week (so 'run to week 8', then 'run to week 26' continues). progress(week) is called each week."""
    root = Path(data_dir) if data_dir else spec.data_dir()
    done = 0 if fresh else completed_weeks(data_dir)
    if done == 0:
        reset(data_dir)
    rows = [] if done == 0 else pd.read_parquet(root / "runs" / "summary.parquet").to_dict("records")
    for week in range(done + 1, weeks + 1):
        features.build(week, data_dir)
        r = pipeline.run_week(week, overrides, dial=dial, data_dir=data_dir)
        sug = delivery.deliver(r, data_dir)
        outcome = feedback.simulate_week(week, r.sent, sug, data_dir)
        h = pipeline.summary(r)["headline"]
        row = {"week": week, "run_date": r.feats.as_of, "triggers": h["triggers raised"], "allowed": h["allowed"],
               "delayed": h["delayed"], "blocked": h["blocked"], "sent": h["actions sent"],
               "expected_return_eur": h["total expected return (EUR)"], **outcome}
        rows.append(row)
        pd.DataFrame(rows).to_parquet(root / "runs" / "summary.parquet", index=False)
        log(f"week {week:2d} ({r.feats.as_of:%d %b %Y}): {row['triggers']:5,} triggers, {row['sent']:4,} sent, "
            f"{row['accepted']:3} accepted / {row['dismissed']:3} dismissed by reps, "
            f"expected return EUR {row['expected_return_eur']:,.0f}")
        if progress:
            progress(week)
    return pd.DataFrame(rows)
