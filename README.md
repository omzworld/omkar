# Next best action engine: pharma omnichannel MVP

A working demo of a next best action engine for pharma omnichannel marketing in Europe, on synthetic data.
The build brief is `CLAUDE.md`; the business specification is in `spec/`; decisions made during the build
are in `docs/decisions.md`.

## Status

| Step | What | Status |
|---|---|---|
| 1 | Project setup, schemas, synthetic data generator, data readiness report | Done |
| 2 | Feature table and rules engine | Done |
| 3 | Constraints and optimiser | Done |
| 4 | Delivery, talk tracks, feedback simulator, 26-week runner | Done |
| 5 | Measurement, return model, API, web screens | Done |
| 6 | Plain-language rule writing and quick impact test | Next |
| 7 | Discovery (change detection) with the 10% cap | |

## Run it

You need Python 3.11 or later, [uv](https://docs.astral.sh/uv/) and Node.js 20 or later.

The demo (all six screens):

```bash
make setup
```

```bash
make demo
```

Then open http://127.0.0.1:8000. `make demo` generates fresh data, builds the web app and starts the engine. Run
the pilot from the Feedback screen (to week 8) and the Results screen (to week 26); no command line needed.

Everything below is the same engine from the command line.

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

```bash
.venv/bin/nba week --week 1 --dial 1
```

```bash
make run
```

`make synth` writes about 550,000 rows across 25 tables to `data/` in a few seconds. `make readiness` prints the
data readiness report (demo scene 1) and saves it to `data/readiness.json`. `nba features` builds the
week's feature table (one row per account, 133 columns) and saves a snapshot. `nba triggers` runs the enabled
rules and shows what fired and why; `--set` previews a threshold change (demo scene 2). `nba lint` checks every
rule in the catalogue. `nba week` runs the whole week (triggers, constraint verdicts, optimiser) and prints what was
held back and why, what is sent by channel, and the top actions by expected return; `--dial 0` shows what a
rules-only engine would send (demo scene 3). `make run` runs the 26-week pilot (under two minutes): the engine
in test territories, today's plan in control territories, and simulated rep and physician responses. Each week's
Veeva suggestion payloads, agency file and rep talk tracks are written to `data/runs/week_NN/`.

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
  candidates.py triggers to candidate actions (channel, theme, asset)
  constraints.py allowed, delayed or blocked, naming the constraint
  optimiser.py  chance, value, cost, expected return; capacity, substitution, the rules-to-score dial
  pipeline.py   one weekly run and its summary
  delivery.py   Veeva suggestion payloads, agency file, rep talk tracks with the grounding check
  feedback.py   the simulated field: reps accept or dismiss, physicians respond (may read hidden clusters)
  runner.py     the 26-week pilot
  measure.py    test vs control, lift, cost per engaged physician, pilot gates, return model
  proposals.py  acceptance by rule and the engine's rule change proposals (R134)
  rules/versions.py  saved rule versions from the rule studio
  api.py        the web API (FastAPI)
web/            the web app (React + Vite + Tailwind): six screens, one per demo scene
  cli.py        the `nba` command
spec/           business specification (authority for rules, constraints, schemas, assumptions)
tests/          automated tests (pytest)
docs/           build decisions
data/           generated data (not in Git)
```
