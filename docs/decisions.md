# Build decisions

Decisions made during the build that change or add to the spec pack. Newest at the bottom of each section.

## MVP scope for the client pitch (agreed 14 Nov 2026)

| Priority | In the pitch MVP |
|---|---|
| Must have | Synthetic data and readiness, feature table, rules engine (a hand-picked set of rules rather than all 65), constraints engine, optimiser, Veeva suggestion payloads, feedback simulator, 26-week runner, test vs control measurement and return model, web screens for demo scenes 1 to 6 |
| High-impact extras | Plain-language rule writing with the quick impact test (scene 7); rep talk track (scene 8) |
| Simplified | Discovery: change detection only (a statistical detector, no trained model) |
| Deferred to the roadmap | Key account manager briefs, agency files, propensity-to-move and look-alike detectors, proposed rules from discovery, Xifaxan and rare disease rule families |

Open items to settle before the steps that need them:
- Constraints live in two places (33 constraint rules in the catalogue and the CSV tables). Plan: the CSVs hold the
  numbers, the rules hold the logic. Step 3.
- The "rules-to-score dial" in demo scene 3 is not defined in the spec. Step 3.
- Market signals with no source table (formulary, tenders, NHS waiting list, readmissions): rules using them are left
  out of the pitch set unless a simple synthetic signal is added. Step 2.
- `optimiser_example.md` uses a 0.25 response chance for the rep email substitute without saying where it comes from. Step 3.
- R016 references `cap_touches_month`, which comes from `cadence.csv`, not the feature table. Step 2/3.

## Step 1: synthetic data

- Added table `hcp_stage_weekly` to `spec/schemas/datasets.yaml`: the journey stage of each physician each week.
  In real life this comes from brand segmentation; the feature table needs it for `stage`, and discovery needs the history.
- Hidden behaviour clusters are written to `data/hidden/`, outside the public tables. A test checks that no engine
  module reads that folder.
- One brand per physician, by specialty: GP, paediatrics, internal medicine: Movicol; gastroenterology, endoscopy
  nurse, hospital pharmacist: Plenvu/Moviprep; hepatology: Xifaxan.
- Journey moves need stage-appropriate content. A response moves a physician along the journey only when the asset's
  journey stage matches theirs (or they attended an event). Without this, physicians drifted to loyalty and
  advocacy within two years. With it, today's random content calendar moves people slowly, which is the gap the
  engine is meant to close.
- Today's plan includes 0.4 rep emails per month for physicians with consent (not in the design file).
- Germany: 15% of physicians who gave email consent gave single opt-in only, so the double opt-in rule (R010) has
  something to block.
- About 2% of German physicians have English as their language, so the asset-language rule has something to block.
- About 5% of approved assets expire in the first two weeks of the pilot, so the asset-expiry rule has something to block.
- Rep open slots per pilot week are drawn around 10 visits (25 slots minus the existing call plan), so capacity binds sometimes.
- Key messages in content are placeholders marked "replace with MLR-approved text". No clinical claim is invented.
- DuckDB 2.0 removed `fetchone()` on query results; use `con.execute(sql)` rather than `con.sql(sql)`.
