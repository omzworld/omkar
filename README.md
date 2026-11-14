# Next best action engine: pharma omnichannel MVP

A working demo of a next best action engine for pharma omnichannel marketing in Europe, on synthetic data.
The build brief is `CLAUDE.md`; the business specification is in `spec/`; decisions made during the build
are in `docs/decisions.md`.

## Status

| Step | What | Status |
|---|---|---|
| 1 | Project setup, schemas, synthetic data generator, data readiness report | Done |
| 2 | Feature table and rules engine | Done |
| 3 | Constraints and optimiser | Next |
| 4 | Delivery, talk tracks, feedback simulator, 26-week runner | |
| 5 | Measurement, return model, API, web screens | |
| 6 | Plain-language rule writing and quick impact test | |
| 7 | Discovery (change detection) with the 10% cap | |

## Run it

You need Python 3.11 or later and [uv](https://docs.astral.sh/uv/).

```bash
make setup
```

```bash
make synth
```

```bash
make readiness
```

```bash
make test
```

Then, for a pilot week:

```bash
.venv/bin/nba features --week 1
```

```bash
.venv/bin/nba triggers --week 1 --set R075.decline_pct=6
```

```bash
.venv/bin/nba lint
```

`make synth` writes about 550,000 rows across 25 tables to `data/` in a few seconds. `make readiness` prints the
data readiness report (demo scene 1) and saves it to `data/readiness.json`. `nba features` builds the
week's feature table (one row per account, 133 columns) and saves a snapshot. `nba triggers` runs the enabled
rules and shows what fired and why; `--set` previews a threshold change (demo scene 2). `nba lint` checks every
rule in the catalogue.

## Look at the data with SQL

Every table is a Parquet file you can query with DuckDB:

```bash
.venv/bin/python -c "from nba import data; print(data.connect().execute('select market, specialty_1_vod, count(*) n from account_vod where account_type = \'hcp\' group by all order by 1, 3 desc').df())"
```

## Layout

```
nba/            the engine (Python package)
  spec.py       reads spec/ and config.yaml
  schema.py     table definitions from spec/schemas/datasets.yaml, used to validate every write
  data.py       read and write Parquet, DuckDB connection with one view per table
  segments.py   tier A/B/C assignment
  synth/        synthetic data generator (entities, content, 24-month history, sales, behaviour model)
  readiness.py  data readiness report (DuckDB SQL)
  columns.py    the column dictionary, read from spec/schemas/feature_columns.md
  features/     the weekly feature table (touch history, market signals, consent) in DuckDB SQL
  rules/        expr.py (safe condition evaluator), catalogue.py (load, parameters, linter), engine.py (triggers)
  cli.py        the `nba` command
spec/           business specification (authority for rules, constraints, schemas, assumptions)
tests/          automated tests (pytest)
docs/           build decisions
data/           generated data (not in Git)
```
