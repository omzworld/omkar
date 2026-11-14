"""Command line: synth, readiness, features, lint, triggers, week, run."""
from __future__ import annotations

import pandas as pd
import typer

from nba import readiness as readiness_mod
from nba import spec

app = typer.Typer(help="Next best action engine (MVP on synthetic data).", no_args_is_help=True)
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 80)


@app.command()
def synth(seed: int = typer.Option(None, help="Random seed; defaults to the seed in synthetic_design.yaml."),
          scale: float = typer.Option(1.0, help="Share of the full population to generate (1.0 = 3,000 HCPs).")):
    """Generate every synthetic dataset as Parquet under data/."""
    from nba.synth import generate
    counts = generate(seed=seed, scale=scale)
    typer.echo(f"Wrote {len(counts)} tables to {spec.data_dir()} ({sum(counts.values()):,} rows in total).")


@app.command()
def readiness():
    """Print the data readiness report and save it as data/readiness.json."""
    report = readiness_mod.build()
    typer.echo(readiness_mod.render(report))
    typer.echo(f"\nSaved to {readiness_mod.save(report)}")
    raise typer.Exit(0 if readiness_mod.passed(report) else 1)


@app.command()
def features(week: int = typer.Option(1, help="Pilot week (1 = pilot start)."),
             show: str = typer.Option(None, help="An account id to print in full, e.g. UK-H00012.")):
    """Build the feature table for a week, save the snapshot and print a summary."""
    from nba import features as feat
    f = feat.build(week)
    t = f.table
    typer.echo(f"Week {week} (data up to {f.as_of:%d %b %Y}): {len(t):,} accounts x {t.shape[1]} columns. "
               f"Saved under {spec.data_dir() / 'snapshots'}.")
    hcp = t[t.account_type == "hcp"]
    typer.echo("\nPhysicians by tier and journey stage:")
    typer.echo(pd.crosstab(hcp.tier, hcp.stage).reindex(
        columns=["curiosity", "consideration", "experience", "loyalty", "advocacy"]).to_string())
    typer.echo("\nPhysicians by channel lean:  " + ", ".join(f"{k} {v}" for k, v in hcp.channel_lean.value_counts().items()))
    row = t[t.hcp_id == show] if show else hcp.sample(1, random_state=week)
    if len(row):
        typer.echo(f"\nAll columns for {row.hcp_id.iloc[0]}:")
        typer.echo(row.T.to_string(header=False))


@app.command()
def lint():
    """Check every rule in the catalogue: columns exist, values are valid, parameters are filled."""
    from nba.rules import catalogue
    problems = catalogue.lint()
    rules = catalogue.load()
    for p in problems:
        typer.echo(p)
    typer.echo(f"{len(rules)} rules checked, {len(problems)} problems.")
    raise typer.Exit(1 if problems else 0)


def _overrides(items: list[str] | None) -> dict:
    """['R075.decline_pct=6'] -> {'R075': {'decline_pct': 6}}"""
    overrides: dict = {}
    for item in items or []:
        key, value = item.split("=", 1)
        rule_id, param = key.split(".", 1)
        overrides.setdefault(rule_id, {})[param] = float(value) if "." in value else int(value)
    return overrides


@app.command()
def triggers(week: int = typer.Option(1, help="Pilot week."),
             set_: list[str] = typer.Option(None, "--set", help="Override a rule parameter, e.g. R075.decline_pct=6"),
             rule: str = typer.Option(None, help="Show the triggers of one rule, e.g. R075.")):
    """Raise this week's triggers from the enabled rules (uses the saved feature snapshot)."""
    from nba import features as feat
    from nba.rules import engine
    try:
        f = feat.load_snapshot(week)
    except FileNotFoundError:
        f = feat.build(week)
    overrides = _overrides(set_)
    base = engine.raise_triggers(f)
    tr = engine.raise_triggers(f, overrides) if overrides else base
    typer.echo(f"Week {week}: {len(tr):,} triggers from {tr.rule_id.nunique()} rules "
               f"({tr.hcp_id.nunique():,} accounts).\n")
    typer.echo(engine.summary(tr).to_string(index=False))
    for rule_id in overrides:
        d = engine.compare(base, tr, rule_id)
        typer.echo(f"\n{rule_id} with {overrides[rule_id]}: {d['after']} accounts (was {d['before']}), "
                   f"{len(d['added'])} added, {len(d['removed'])} removed.")
        added = tr[(tr.rule_id == rule_id) & tr.hcp_id.isin(d["added"])]
        if len(added):
            typer.echo(added[["hcp_id", "territory_id", "reason"]].head(15).to_string(index=False))
    if rule:
        typer.echo(f"\nTriggers for {rule}:")
        typer.echo(tr[tr.rule_id == rule][["hcp_id", "market", "territory_id", "reason"]].to_string(index=False))


@app.command()
def week(week: int = typer.Option(1, help="Pilot week."),
         dial: float = typer.Option(1.0, help="Rules-to-score dial: 0 = rule priority decides, 1 = expected return decides."),
         set_: list[str] = typer.Option(None, "--set", help="Override a rule parameter, e.g. R075.decline_pct=6"),
         top: int = typer.Option(15, help="How many sent actions to list.")):
    """Run one week: triggers, constraint verdicts, optimiser decisions, with reasons (demo scene 3)."""
    from nba import pipeline
    r = pipeline.run_week(week, _overrides(set_), dial=dial)
    s = pipeline.summary(r)
    typer.echo("WEEKLY RUN SUMMARY\n" + "=" * 40)
    for k, v in s["headline"].items():
        typer.echo(f"{k:<45}{v:,}" if isinstance(v, (int, float)) and not isinstance(v, bool) else f"{k:<45}{v}")
    typer.echo("\n1. Held back by a constraint (candidate actions, physicians, example reason)")
    typer.echo(s["constraints"].to_string(index=False))
    typer.echo("\n2. Sent, by channel (expected return in EUR; average chance of response)")
    typer.echo(s["by_channel"].to_string(index=False))
    typer.echo("\n3. Allowed but not sent, and why")
    typer.echo(s["not_sent"].to_string(index=False))
    typer.echo(f"\n4. Top {top} actions by expected return")
    typer.echo(pipeline.top_list(r, top).to_string(index=False))
    typer.echo("\n5. By rule")
    typer.echo(s["by_rule"].to_string(index=False))
    typer.echo(f"\nSaved to {spec.data_dir() / 'runs' / f'week_{week:02d}'}")


@app.command()
def run(weeks: int = typer.Option(26, help="How many pilot weeks to run."),
        dial: float = typer.Option(1.0, help="Rules-to-score dial (0 = rules decide, 1 = expected return decides)."),
        set_: list[str] = typer.Option(None, "--set", help="Override a rule parameter, e.g. R075.decline_pct=6")):
    """Run the pilot from week 1: engine in test territories, today's plan in control, simulated field feedback."""
    from nba import runner
    out = runner.run(weeks, dial=dial, overrides=_overrides(set_))
    typer.echo(f"\nDone: {weeks} weeks. Outputs under {spec.data_dir() / 'runs'} "
               f"(Veeva payloads, agency files, talk tracks per week).")
    typer.echo(f"Suggestions accepted by reps: {out.accepted.sum():,} of {out.suggestions.sum():,} "
               f"({out.accepted.sum() / max(out.suggestions.sum(), 1):.0%}).")


if __name__ == "__main__":
    app()
