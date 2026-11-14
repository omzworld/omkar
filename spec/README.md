# Specification pack: next best action engine for Norgine omnichannel

Drop this folder into the repository as `spec/` and copy `CLAUDE.md` to the repository root.

- CLAUDE.md: build brief for Claude Code; architecture, conventions, five build steps with definitions of done, demo story.
- rules/rules_catalogue.yaml: 134 rules across ten families; each tagged rules, constraints, optimiser or feedback; 65 enabled at launch across all brands (54 for a Movicol-only pilot). rules/gen_rules.py regenerates it.
- constraints/: consent_rules.csv, country_code.csv, cadence.csv, capacity.csv, with a README on verdict order.
- schemas/datasets.yaml: the standard datasets with Veeva field names; feature_columns.md: every column a rule may reference; suggestion_payload.json: the Veeva suggestion shape.
- data/synthetic_design.yaml: markets, brands, specialty mix, hidden behaviour clusters, history simulation, brick sales, pilot arms, feedback simulation.
- assumptions/return_assumptions.yaml: touch costs, stage-move values, risk values, chance tiers, decay, run cost, pilot gates.
- examples/optimiser_example.md: the hand-calculated optimiser case used as a test fixture.

Figures in constraints and assumptions are starting values for the synthetic build. Each is replaced by Norgine's own in the data audit.
