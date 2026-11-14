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
- Market signals with no source table (formulary, tenders, NHS waiting list, readmissions): rules using them are left
  out of the pitch set unless a simple synthetic signal is added. Step 2.

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

## Step 2: feature table and rules engine

- The pitch rule set is the catalogue's own `enabled_at_launch` trigger rules: 27 rules (engagement 9, Movicol 7,
  bowel preparations 7, Xifaxan 4). Xifaxan is kept because its rules cost nothing extra; KAM briefs are still deferred
  at the delivery step. In week 1, 20 of the 27 fire; the rest need recent webinar or event activity, which starts
  once the weekly runner exists (step 4), or a signal with no source (R093, new endoscopist).
- Fixed a catalogue typo found by the linter: R110 used `hcp_role == 'hospital_pharmacist'`; the value is
  `pharmacist_hospital` (fixed in `rules_catalogue.yaml` and `gen_rules.py`).
- Added to `feature_columns.md`: `brand` (an account's main brand, so brand rules reach only their accounts) and the
  six cadence limits looked up from `cadence.csv` by segment, including `cap_touches_month` used by R016.
- Columns with no source in the synthetic data are present with a neutral value (blank or False) so rules using them
  never fire: formulary, tenders, waiting lists, readmissions, guidelines, surveys, medical inquiries, rare disease
  signals, new endoscopist. Listed in `nba/features/__init__.py`.
- Per-rule columns (`rule_accept_rate_30d`, `rule_triggers_30d`) are blank in the feature table; the feedback step
  computes them per rule.
- `same_theme_touches_7d` in the feature table counts touches in the last 7 days on the physician's latest theme;
  the constraints step recomputes it per candidate theme.
- Definitions chosen where the spec is silent: tier is recomputed weekly from brick potential (trailing 12 months of
  total market units); `new_in_target` = tier A/B now but C 90 days ago; `channel_lean` compares the physician's email
  and visit response rates with their market's average (needs 5 emails and 3 visits, otherwise `default`);
  `touches_ignored_consecutive` counts touches since the last response on any channel, including event invitations;
  `pharmacy_dispensing_qoq_pct` compares the last 3 months with the 3 months before.
- Missing values behave as in SQL: a comparison with a blank is never true, including `!=`.
- One firing and one silent fixture per rule are generated from each condition (`tests/fixtures.py`) rather than
  written by hand, plus hand-written fixtures with realistic values for the demo rules.
- Authoring example 1 ("GP, brick down 8%, no rep visit in two months") matches 107 physicians in 23 territories in
  week 1; `spec/authoring/examples.md` expects 140 to 180 at week 8. Recheck at step 6 once weeks 1 to 8 have run.

## Step 3: constraints and optimiser

- Triggers become candidate actions (`nba/candidates.py`). `next_best` becomes one candidate each for rep visit, rep
  email and marketing email, and the optimiser keeps the best. `next_theme` follows the enabled content sequence rules
  (R063 to R066), with a stage default (curiosity and consideration: efficacy; experience: dosing; loyalty: real-world
  evidence; advocacy: peer experience); a theme ignored twice moves to the next theme (R070). The asset is the first
  approved, in-date PromoMats asset for the market, brand, theme and channel; if none, the best available one, so the
  constraints engine can say why it cannot be used. "Find out why" visits (R041) need no asset.
- Constraints come from both sources, one verdict. The catalogue's constraint rules hold the logic and brand-editable
  numbers; `consent_rules.csv` adds per-channel consent (it catches, for example, rep email in Germany without double
  opt-in, which R010 only checks for marketing email) and `country_code.csv` adds channel bans and monthly caps per
  channel. Blocks first (highest priority wins), then delays. A delay releases next week, or on the 1st of next month
  for rules timed `next_month` (R016).
- The optimiser example's 0.25 chance for the rep email substitute is the physician's own chance on rep email,
  computed the same way as any chance (own history, segment, benchmark).
- Value of response: the yearly stage-move value in `return_assumptions.yaml` for the physician's next move,
  times the new `value_horizon_years` (2), times potential (specialty weight x brick potential x practice size against
  similar practices, capped between 0.25 and 4). Risk triggers use the value of the move into the current stage
  (what could be lost). Transitions missing for a brand use half its smallest value; advocates have a maintenance value
  of half the loyalty-to-advocacy value. Plenvu/Moviprep uses the procedure basis: EUR 9 per point of share x the unit's
  yearly colonoscopies / 100, half for an individual physician; competitor share loss adds EUR 40 per point on risk
  triggers. Added `unit_colonoscopies_qtr` to `feature_columns.md` for this.
- Capacity per week: rep visits and rep emails from `rep_capacity`; remote calls 10 per rep and KAM briefs 8 per KAM
  from `capacity.csv`; marketing email 5,000 per market per send window, two windows a week; webinar 300 seats.
- Selection order reproduces `optimiser_example.md`: drop negative returns, keep the best per physician, fill capacity
  by return, substitute (visit to rep email, KAM visit to KAM brief) when full, drop anything not positive.
- The rules-to-score dial (demo scene 3): rank score = (1 - dial) x rule priority / 100 + dial x expected return /
  largest expected return. At 0 the rules decide and negative returns are kept, as a rules-only engine would; at 1
  expected return decides. Week 1: dial 0 sends 873 actions for EUR 142k expected return and EUR 93k cost; dial 1
  sends 753 for EUR 252k and EUR 78k.
- To watch: R041 ("no response to the last three touches, rep finds out why") is about a third of what is sent in
  week 1. Tighten it (for example 4 touches, or exclude event invitations) if it crowds out other actions in the demo.

## Step 4: delivery, feedback simulator and the 26-week runner

- No language model key is available yet, so talk tracks use the template (`model_name: template`). The grounding
  check still runs on every brief. `nba/llm.py` will be added when a key exists (set `ANTHROPIC_API_KEY` in the
  environment settings); the brief structure stays the same.
- The engine runs only for test territories; control territories (and the one vacant territory) carry on with today's
  plan, simulated exactly as in the 24-month history. Paid media and the quarterly webinar continue in both arms.
- `nba synth` now also saves the simulator's end-of-history state (`data/hidden/simulator.pkl`) and a copy of every
  table (`data/baseline/`). `nba run` restores both, so every run starts from the same place.
- Feedback per week: reps accept suggestions with the probabilities in `synthetic_design.yaml` (0.75 for a visit to a
  rep-led physician, 0.55 otherwise, plus 0.01 a week as trust builds); dismiss reasons follow the design shares.
  Accepted touches get responses from the hidden behaviour model. A rep visit wins email consent from a physician
  without it 5% of the time (15% for an introduction visit). Completed months add brick sales; completed quarters add
  endoscopy procedure volumes. Randomness is seeded by (seed, week).
- Key account manager actions (R090 to R092, R108) are delivered as Veeva suggestions with record type Call; the
  separate key account manager brief document remains deferred. The agency file is written each week.
- Three changes after the first 26-week run showed test territories doing worse than control:
  1. Added rule R135 (engagement_triggers, enabled): "no touch in 14 days: next step in the journey", channel chosen
     by the optimiser. Without it the engine only considered physicians picked out by event-driven triggers, so as
     touches fell, triggers fell too.
  2. Fixed R020: its condition never used its own `gap_after_two_ignored` parameter, so two ignored emails delayed
     email forever. Added `and days_since_last_email < {gap_after_two_ignored}`.
  3. The optimiser now gives a physician their next best action when their best channel has no capacity left
     (substitution still applies to a physician left with nothing).
  Both catalogue changes were made in `gen_rules.py` and the catalogue regenerated.
- Synthetic content: asset journey stages now follow the catalogue's content sequence (efficacy for curiosity, patient
  case for consideration, dosing for experience, real-world evidence for loyalty, peer experience for advocacy), and
  Plenvu/Moviprep gained a patient-case asset. The stage default for `next_theme` at consideration is now patient case.
- First read of the 26-week run (full data): Movicol brick units in test territories +8.4% against +6.6% in control
  (about 1.8 points of lift) with roughly half the touches. Average journey progress is lower in test (+0.09 stages
  against +0.13): the engine does well with tier A Movicol physicians but under-serves Plenvu/Moviprep physicians,
  whose value of response is low under the current assumptions. The quarterly pilot gate asks for 4 points of brick
  lift. Calibrate in step 5 (measurement) with the brand and finance assumptions, not by tuning the simulator.

## Step 5: measurement, return model, API and the six screens

- Web app: React + Vite + Tailwind in `web/`, plain JavaScript (no TypeScript) to keep it readable. Charts are small
  hand-written SVG components (no chart library): one axis, thin marks, a legend plus direct end labels, hover
  read-outs. Test territories are blue, control orange (validated for colour-blind separation in light and dark).
  The built app is served by the engine itself (`nba serve`), so the demo is one process on one port.
- Rule studio versions are saved to `data/rule_versions.json` (version 1 is the catalogue, never overwritten); every
  later run uses the latest version. A version can also pause a rule.
- Pilot runs from the screens continue from the last completed week (run to week 8, then on to 26); "Start again"
  restarts from week 1. Saved rule versions apply from the next week run.
- Feedback rule R134 counts `rule_triggers_30d` as triggers raised (as its condition says), not suggestions. Its
  proposal tightens the rule's numeric threshold by a quarter in the direction that makes it fire less; a rule with
  no threshold is proposed for pausing.
- Simulator additions (documented field behaviour, so acceptance differs by rule and the engine has something to
  learn): reps accept suggestions for physicians they visited in the last 30 days at 0.55 times the usual rate and
  usually mark them "seen recently"; suggestions for tier C accounts at 0.6 times, usually "not a priority".
- Measurement: brick lift is the growth of Movicol units in test territories minus control, completed pilot months
  against the same number of months before. Engaged = responded at least once. Cost uses the touch costs in the
  assumptions file.
- Return model inputs on screen: fee per quarter, gross margin (default 70%, an assumption added here), the client's
  real brand sales per quarter (the synthetic market is far too small: about EUR 270k a quarter in test territories,
  against a EUR 180k fee), the lift to use, and whether to count the touch cost saving (only real if reps' freed time
  is redeployed). Break-even shows 0 when the saving alone covers the fee.
- Results after 26 weeks with the demo walkthrough's changes (R075 at 6%, R077 tightened at week 8): brick lift
  +0.7 points; touches per physician 6.1 in test against 12.1 in control; cost per engaged physician EUR 524 against
  EUR 819; but fewer test physicians moved up a stage (10.2% against 14.3%). Pilot gates met: rep acceptance and reach.
  Not met: 4-point lift, 2% monthly consent growth (test 1.2%), EUR 45 cost per engaged physician (unreachable while a
  rep visit costs EUR 150). These are calibration questions for the brand and finance assumptions.

## Step 6 (partial): writing a rule in the rule studio, and the data control center

- No language model key yet, so `author.parse` (typed sentence to rule) is not built. The rule studio's "Create new
  rule" is a guided form instead: brand, markets, conditions picked from the feature table's columns (columns with no
  source are listed but cannot be picked), action, theme, timing, priority and the reason. Every number becomes a
  named parameter, so the new rule can be tuned and versioned like a catalogue rule. `nba/author.py`.
- `author.validate` runs the catalogue linter on the draft and lists missing fields (the market is highlighted, as in
  `spec/authoring/examples.md`). `author.quick_test` runs the draft on the latest completed week's feature snapshot:
  matches, reps and territories, the constraints verdicts by constraint, overlap with other rules, and how many the
  optimiser would send in test territories next to every other rule. Nothing is saved.
- Approved rules get the next free id (R136 onwards) and are saved to `data/custom_rules.json`; `catalogue.load()`
  adds them, so they run from the next pilot week. They can be removed again. `make demo` clears them.
- Authoring example 1 on week 26: 55 GPs matched (UK 40, DE 15), 14 reps, 49 allowed, 3 delayed, 3 blocked; 4 sent.
  Below the 140 to 180 the examples file expects at week 8; recheck against week 8 when step 6 is finished.
- Data control center (`nba/datacatalog.py`, `/api/data/catalog`): every dataset in `datasets.yaml` checked live
  against its Parquet file (rows, fields present, fill rate, date range), 23 joins tested key by key, and the feature
  table's coverage including the signals that have no source yet. The screen says plainly that the values are synthetic.
