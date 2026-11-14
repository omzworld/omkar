# Next best action engine for Norgine omnichannel: build brief

This repository builds a working MVP of a next best action engine for pharma omnichannel marketing in Europe,
on synthetic data shaped like Norgine's. Read this file first in every session. The specification pack in
`spec/` is the authority on rules, constraints, schemas, data design and return assumptions; code follows it.

## What the tool does, in one paragraph
Each week the engine builds a feature table (one row per physician or account), runs three engines in order,
delivers the result, simulates responses, and records everything. The rules engine raises triggers (risk or
opportunity) with a one-line reason. The constraints engine returns allowed, delayed or blocked for each trigger,
naming the constraint. The optimisation engine scores allowed options by expected return (chance of response ×
value of response − cost of touch, with decay), keeps the best per physician, fills rep and agency capacity by
return per slot, substitutes a cheaper channel when capacity is full, and emits a ranked list with reasons for
everything not sent. Delivery writes Veeva CRM suggestion payloads, key account manager briefs and agency files.
Feedback simulates responses and dismissals from hidden behaviour clusters and feeds them into next week's signals.
Three additions: marketers write new rules in plain language and test them on last week's data before approval;
a discovery module finds risks and opportunities the rules missed, capped at 10% of what is sent each week; and
reps receive a weekly talk track rather than a list of suggestions.

## Agreed MVP scope and build decisions
The MVP is for a client pitch and is narrower than the full brief below. `docs/decisions.md` records the agreed
scope (what is in, simplified or deferred) and every decision that changes or adds to the spec. Read it after this file.
The person building this has not coded for 15 years but knows SQL and object-oriented ideas: explain changes in
those terms, prefer DuckDB SQL where it reads naturally, and end each step with something they can run and see.
Environment: create the virtualenv with `make setup` (uv); DuckDB 2.x is installed.

## Architecture
- Python 3.11 package `nba/` with modules: `data` (load Parquet via DuckDB), `synth` (generator), `features`,
  `rules`, `constraints`, `optimiser`, `delivery`, `feedback`, `measure`, `runner`, `api` (FastAPI), plus
  `author` (plain-language rule drafting, validation and quick impact test), `discover` (machine learning
  detectors for risks and opportunities), and `llm` (one thin client for the Anthropic API, used by `author`
  and by `delivery` for talk tracks).
- Language model calls go through `nba/llm.py` using the Anthropic API with the key in `ANTHROPIC_API_KEY`.
  Model name in `config.yaml`. Every call has a structured input, a JSON or constrained output, a retry, and a
  template fallback so the engine still runs without a key. Calls are logged with inputs and outputs for audit.
- Every trigger carries `origin`: `rule` or `discovery`. Discovery triggers pass through the same constraints and
  optimiser; the optimiser enforces the 10% cap per market on sent items (see `spec/assumptions/return_assumptions.yaml`).
- Rules are YAML (`spec/rules/rules_catalogue.yaml`). Conditions are expressions evaluated by a small safe
  evaluator over the feature table: Python-like syntax, `and/or/not`, comparisons, `in`, and the theme functions
  listed in `spec/schemas/feature_columns.md`. No `eval` on raw strings; parse with `ast` and whitelist nodes.
- Parameters in `{braces}` inside a condition or reason are filled from the rule's `parameters` block, which the
  rule studio can edit. Reason templates may also reference feature columns.
- Constraints are CSV tables in `spec/constraints/`. Return assumptions are `spec/assumptions/return_assumptions.yaml`.
- Data lives as Parquet under `data/` (generated) and is queried with DuckDB. Field names as in `spec/schemas/datasets.yaml`.
- Frontend: React + Vite + Tailwind in `web/`, six screens, calling the FastAPI at `/api`.
- One command runs everything: `make demo` = generate data, run 26 weeks, start API and web.

## Conventions
- Plain language in every user-facing string. No jargon labels. Every number on screen says what it measures.
- Every engine output row carries `rule_ids`, `constraint_id`, `chance_tier`, and a human-readable `reason`.
- Hidden cluster propensities are used only in `synth` and `feedback`. They must never be read by `features`,
  `rules`, `constraints` or `optimiser`. A test asserts this.
- Test and control territories are assigned at generation and never changed by the engine.
- Everything is deterministic from `seed`. A rerun with the same seed reproduces every number.
- Tests with pytest. Every rule in the catalogue has a fixture row that fires it and one that does not.
- Keep modules under 400 lines. Prefer pandas or DuckDB SQL over loops.
- Rule drafts: `author.parse(text)` returns a rule record and a list of missing fields; `author.validate(rule)` checks
  every column against `feature_columns.md`; `author.quick_test(rule, week)` runs it on the saved feature snapshot
  of that week. The marketer submits the validated form, never free text.
- Discovery: three detectors in `discover/` (change detection, propensity to move, look-alikes), see
  `spec/discovery/discovery_design.md`. Explanations come from the top three feature contributions; no detector
  may read hidden cluster propensities.
- Talk tracks: `delivery.rep_brief(user_id, week)` builds a structured brief (territory summary, ranked
  suggestions, key messages) then asks the model to write prose under 300 words. A grounding check asserts every
  number in the prose appears in the structured brief; on failure the template version is used.

## Build steps and definition of done
1. Scaffold, schemas, synthetic generator.
   Done when: `nba synth` writes every table in `datasets.yaml` as Parquet; `nba readiness` prints the checks in
   `synthetic_design.yaml` and consent coverage by market matches the cluster rates within 5 points.
2. Feature table and rules engine.
   Done when: `nba features --week 1` builds every column in `feature_columns.md`; `pytest tests/test_rules.py`
   passes with one firing and one silent fixture per rule; a catalogue linter fails on any condition that
   references a missing column.
3. Constraints and optimiser.
   Done when: a crafted week reproduces the hand-calculated example in `spec/examples/optimiser_example.md`;
   blocked and delayed counts by constraint appear in the weekly summary.
4. Delivery with talk tracks, feedback simulator, runner.
   Done when: `nba run --weeks 26` completes; suggestion payloads validate against `spec/schemas/suggestion_payload.json`;
   every rep in a test territory has a `rep_brief` row per week that passes the grounding check; responses and
   dismissals change next week's features; a replay with the same seed is identical except the prose.
5. Measurement, return model, API, six screens.
   Done when: the demo story scenes 1 to 6 run from the web UI without the command line.
6. Plain-language rule authoring and the quick impact test.
   Done when: the five example sentences in `spec/authoring/examples.md` parse to the expected rule records with
   the expected missing fields highlighted; `quick_test` on last week's snapshot returns the counts in
   `spec/authoring/examples.md`; an approved draft appears in the next weekly run.
7. Discovery module with the 10% cap.
   Done when: the three detectors run on the 24-month history and produce candidates with explanations;
   `pytest tests/test_discovery_cap.py` shows discovery items never exceed 10% of sent items per market; recurring
   candidates appear in the rule studio as proposed rules in plain language.

## The demo story (ten minutes)
1. Data readiness: two markets, 3,000 physicians, 24 months of history, consent coverage by market.
2. Rule studio: open the Movicol brick-decline rule, change the threshold from 8% to 6%, see which physicians it
   now affects, save a new version.
3. Weekly run: run week 1; show triggers raised, then the constraints verdicts (blocked demand by constraint),
   then the optimiser list with expected return and the reasons for what was not sent; turn the rules-to-score
   dial and rerun.
4. Delivery: the Veeva suggestion payload for one rep, a key account manager brief for one endoscopy unit, and
   the agency file; nothing is sent.
5. Feedback: run to week 8; acceptance and dismissal by rule; the proposals the engine makes; approve one.
6. Measure and return: run to week 26; test versus control territories, lift, cost per engaged physician, the
   return model with editable assumptions and break-even.
7. Write a rule: type "if a Movicol brick drops more than 8% and the GP has not seen a rep in two months, send a
   rep visit with the efficacy asset"; see the parsed form with the missing market highlighted; fill it; run the
   quick test and see how many reps would have received it last week; approve it.
8. Discovery and the talk track: open week 9; show the discovery triggers, their explanations and the 10% share;
   open one rep's talk track: territory summary, three suggestions, each with the reason and talking points.

## Out of scope for the MVP
Real Veeva connectivity, authentication, multi-user editing, rare disease brands beyond the rules present in
the catalogue, content creation and MLR review automation, retraining the discovery models on live data.
