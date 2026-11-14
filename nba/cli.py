"""Command line: `nba synth`, `nba readiness`. More commands arrive with each build step."""
from __future__ import annotations

import typer

from nba import readiness as readiness_mod
from nba import spec

app = typer.Typer(help="Next best action engine (MVP on synthetic data).", no_args_is_help=True)


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


if __name__ == "__main__":
    app()
