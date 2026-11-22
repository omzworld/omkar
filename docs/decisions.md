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

## Rolling brick trends instead of a single quarter-on-quarter reading (15 Nov 2026)

- Brick sales are monthly (IQVIA), and the brick rules compared the last complete quarter with the quarter before.
  One bad quarter was enough to raise a trigger, the value jumped at quarter boundaries, and consecutive quarters mix
  in seasonality. In the synthetic data 76% of bricks flagged "down 8% or more" recovered the next quarter.
- New feature columns (in `feature_columns.md`, built in `nba/features/market.py`): `brick_volume_r3m_pct` (last 3
  complete months against the 3 before, recomputed every month), `brick_volume_r3m_yoy_pct` (against the same 3
  months a year earlier), `brick_units_r3m`, `brick_r3m_months_declining` / `_growing` (how many of the last 3
  monthly readings agree), `brick_competitor_share_r3m_change` and `brick_share_months_rising`.
- R075, R076, R077, R078 and the loyal-prescriber decline rule now need the rolling change past their threshold,
  confirmed in at least `confirm_months` (2) of the last 3 readings, in a brick selling at least `min_units` (100)
  units in 3 months. Both are rule parameters the rule studio can change. The quarter-on-quarter columns are still
  built (talk tracks and readiness no longer use them). Changed in `gen_rules.py`, catalogue regenerated.
- Year-on-year is not a condition: the synthetic market grows about 11% a year, so requiring "below last year" left
  3 bricks of 198 flagged at week 8. It is shown instead, as a 12-month trend line beside any reason about a brick
  (`/api/bricks/trend`), with the 3-month average drawn over the monthly points.
- Bricks flagged "down 8%" at week 8: 37 under the quarterly reading, 13 under the rolling, confirmed rule.
- Fixed in passing: the talk track's "most common dismiss reason" used DuckDB `mode()`, which picks any of tied
  values, so a replay could differ. Ties are now broken alphabetically.

## Competitor campaigns in the simulator, so brick declines mean something (15 Nov 2026)

- Simulated brick sales came only from physicians' journey stages plus random monthly noise, so a brick decline
  carried no information about which physicians to reach; no brick rule could earn lift, and switching to rolling
  trends moved the 26-week lift from +1.9 to 0.0 points without either version being right.
- Added competitor campaigns (`competitor_pushes` in `synthetic_design.yaml`, `nba/synth/behaviour.py`): each month
  each brick has a 3% chance that a campaign starts, lasting 4 to 8 months with a quiet spell after. While it runs,
  a physician in the brick with no response to Norgine (visit, email or event) in the last 8 weeks slips back one
  journey stage with a 25% chance a month. Fewer units follow, and the competitor takes them (its sales fill the
  brick's slowly growing total). A recent response protects; a touch alone does not. The schedule is hidden
  (`data/hidden/competitor_push.parquet`); the engine never reads it.
- Calibration: at 10% a month campaign bricks averaged -1.1% over 3 months against +3.3% otherwise, too faint to
  matter; at 25% they average -6.8% against +3.1%. Over the history, 33% of the rolling, confirmed decline flags
  fall in a live campaign, against 23% of the quarterly flags, from fewer flags (458 against 690); chance is 11%.
  Rolling flags catch about a third of campaign months. The rule still misses some and raises some false alarms.
- Reproducibility fix found by the replay test: "the latest touch" (channel, theme, response, next step), the latest
  event and the latest dismiss reason used DuckDB `arg_max` on the date alone, which picks any of tied rows when two
  happen on the same day. They now order by date, then channel, asset and outcome. Five replays are identical.

## Baseline segmentation and plan, budget-neutral weekly reallocation (15 Nov 2026)

- The pilot's test territories had today's plan switched off and the engine filling reps' spare slots only, so test
  ran on about half the touches of control. Replaced by a plan-based model (`nba/plan.py`, `nba/reallocate.py`):
  - Each quarter (`planning.cycle_weeks` = 13): segment every active physician on potential (`nba.segments.potential`),
    adoption (stage) and responsiveness (own 12-month response rate, shrunk to the market average with 10 touches'
    weight). Potential bands use today's tier shares (20/35/45) with a 5-point margin before a physician moves, so a
    move reflects a real difference (510 of 2,968 in quarter 1 against today's tiers; 23 between quarters 1 and 2).
  - Recommend touches per segment: last year's touches per market, channel and pilot arm (each arm keeps its own
    total, so test neither lends nor borrows budget), shifted towards the segment where the next touch is worth most
    (value x responsiveness, 0.75 frequency decay), each segment within +/-20% of last year. Within a segment, last
    year's pattern blended 50/50 with value; high-potential physicians visited last year keep 2 visits a quarter.
    Channels are planned only where allowed (email consent, German double opt-in, remote consent, UK visits to
    prescribers, no medical-only contacts). Email channels follow the consented list: newly eligible physicians
    join at their segment's frequency for the rest of the quarter (`plan.top_up_lists`).
  - Reps' adjustments (`rep_plan_input`, from the CRM: must see, no access, prefers digital, left the practice) apply
    on top. New tables `hcp_segment`, `call_plan`, `segment_budget`, written each cycle.
  - Each week the due touches (an even schedule) are the reps' plan, carried out without needing acceptance. Trigger
    candidates may take the slot of the weakest planned touch of the same rep and channel if worth at least EUR 5
    more; the moved touch is not rescheduled, so the total holds. At most 20% of a rep's planned touches a quarter,
    accruing week by week. Protected: a physician already moved once on that channel this quarter, a high-potential
    physician at the visit floor, a segment running more than 10% behind its plan. Hard blocks drop a planned
    touch and its slot goes to the best eligible trigger; cadence delays do not hold planned touches (the plan is
    already spaced). A rep can decline a change; the planned touch then goes ahead.
  - The rules-to-score dial is now plan-to-reallocate: 0 follows the plan, 1 reallocates up to the cap.
  - R135 (no touch in 14 days) switched off: the plan covers every physician. R136 added, "defend the brick":
    sustained brick decline, a committed prescriber silent for 42 days, best channel.
- Results now show the equal-spend check (spend per physician test vs control within 5%, and test against its own
  planned budget) and what was reallocated by segment. The return model no longer counts a touch-cost saving.
- First 26-week result (seed 2026): spend per physician EUR 637 test against EUR 665 control (-4.2%, within the
  band); test spent 3.9% under its own plan (blocked touches not made up); touches per physician -7.5% (control's
  unmanaged email programme and visits drift a few percent above last year). 9.5% of planned touches moved.
  Brick lift -2.4 points; physicians moving up a stage 11.4% test against 14.7% control. Across the design
  iterations the lift ranged from -3.3 to -0.9 points on the same seed, so the 26-week lift is noisy at this size;
  the allocation favours late-stage, high-value physicians while the simulator moves early-stage physicians more
  easily. Calibration of stage values and the reallocation's targets is the next step, not a simulator change.
- Data folder: `NBA_DATA_DIR` overrides config.yaml's data_dir. Inside OneDrive the weekly rewrites caused a sync
  conflict that replaced a table with an empty older copy; outside it the 26-week pilot takes 86 seconds instead
  of more than 10 minutes. Table discovery now ignores files that are not valid table names (conflict copies).

## Learned response value and stage-matched content (15 Nov 2026)

- The 26-week lift was negative (-2.4 points) and test physicians moved up a stage less often than control on every
  seed tried. Rather than change the simulated market, the engine was changed to learn from its own history what a
  response is worth (`nba/learn.py`), using only public tables (weekly stages, touches, responses, asset journey
  stages):
  - The history shows a response moves a physician up a stage only when the content matches their journey stage:
    19.9% of matched responses moved a stage, 0.6% of unmatched; 70% of responses were to unmatched content.
  - Per stage, the engine learns the move rate for matched and unmatched content (e.g. consideration 29% vs 6%,
    loyalty 6% vs 2%) and the weekly slip rate of physicians silent for 8 weeks against recently responsive ones.
  - Value of a response (`optimiser.value`) = learned move chance x value of the next stage move + learned
    protection over 8 weeks x value of the current stage, instead of assuming every response moves a physician up.
    The quarterly plan uses the same value, so allocation and weekly moves agree.
- R065 (consideration + patient case received -> dosing) and R070 (theme ignored twice -> next theme) switched off
  at launch: both move content ahead of the physician's stage, which the history shows does not move physicians.
  They stay in the catalogue; the brand team can switch them back on in the rule studio.
- A planned touch whose asset is missing falls back to content for the physician's own stage first.
- Slots freed by blocked planned touches go to the best remaining candidate even with a low expected return (the
  budget is committed); swaps that displace a planned touch must still beat it.
- Spend per physician now counts touches to the same population it divides by (active, promotable, not
  medical-only), in both arms.
- Talk track wording "last 3 months against the 3 before" put numbers in the prose that the grounding check could
  not find in the brief; spelled out.
- Evaluation across synthetic markets (seeds), same simulator: before, lift -2.4 / +2.4 / -1.1 points (seeds 2026 /
  11 / 42, mean -0.4); after learning the response value, +3.4 / +8.9 / +4.9 (mean +5.7), with physicians moving up
  a stage roughly twice as often in test (28-29%) as in control (13-16%). The spread across seeds is large, so the
  pitch should quote a range, not one number.

## Doctor and rep view (15 Nov 2026)

- New screen 8 (`web/src/screens/Stories.jsx`, `nba/story.py`, `/api/story/*`): the pilot told through one doctor
  and one rep, read from the public tables and run outputs; nothing is written.
- Doctor: weekly journey stage and every touch (content, the content's journey stage, whether it matched the
  doctor's stage at the time, response, and in test territories whether it was planned or moved in, with the
  reason). A week's stage is recorded after that week's touches, so a touch is matched against the stage from the
  week before. Showcase picker: test doctors who moved 1-2 stages after the engine moved a touch to them.
- Comparisons use fixed rules, not hand-picking: the doctor's counterpart is the opposite-arm doctor with the same
  market, quarter-1 segment, starting stage and specialty and the closest number of touches; the rep's counterpart
  is the opposite-arm rep in the same market with the closest number of doctors. The whole peer group is shown in
  both arms so a single pair never stands alone.
- On the demo market (seed 2026, 26 weeks): Dr Q. Zimmer (DE-H01143, test) 14 touches, 79% stage-matched,
  consideration -> loyalty; counterpart Dr O. Wolf (DE-H00005, control) 14 touches, 21% matched, still at
  consideration. Peer group (23 each): 48% moved up in test against 35% in control, on 7.5 against 10.1 touches.
  DE-REP24 (test) against DE-REP23 (control), 43 doctors each: 92 against 109 visits, 90% against 23% of visits
  stage-matched, 33% against 21% of their doctors moved up.

## Changes from the Norgine analyst session (Raj's notes): the top three

1. Planned against actual contacts by potential (`nba/attainment.py`, `/api/attainment`, a card on Results and return).
   - Contacts are rep visits plus remote calls.
   - Test target: the engine's quarterly plan for that doctor. Control target: today's call plan (visits a month by tier).
   - A doctor "got their plan" when delivered ≥ planned, rounded.
   - The card also shows the contacts-per-doctor distribution for the first quarter (0, 1, 2, 3-4, 5, 6+), matching the CRM chart Raj showed.
   - Seed 2026: control got its plan for 48% of high-potential and 36% of medium-potential doctors, while low-potential doctors were over-served (146% of plan). Test was 73–79% in every band.
2. My territory this week (`nba/territory.py`, `/api/territory/{rep}`, new screen 5). One page per rep, one row per doctor:
   - segment and ZS potential
   - ladder position now, against what the profile says
   - concern and barrier, and the profile's age
   - last contact
   - quarter plan progress
   - this week's action and why
   - lead content (stage-matched) and supporting material for the concern
   - headroom
3. Norgine segmentation language and inputs.
   - New table `account_profile_vod`, the rep-entered Veeva profile:
     - message segment, barrier, competitor, sentiment, influence, plan member, decision maker
     - ZS potential
     - belief, preference and usage ladders
     - date last updated
     - About 15% of attitudinal fields are left blank, and about a quarter of profiles are over a year old.
   - Journey stages are shown in the brand's ladder words: curiosity = unaware, consideration = aware, experience = occasional use, loyalty = regular use, advocacy = advocate.
   - `planning.potential_source` chooses between the computed potential (default) and ZS. Segment & plan shows how far they agree (54% on seed 2026).
   - Concern-based content is supporting material only; the lead content stays stage-matched, because that is what the learned odds show moves doctors.

## Rule studio upgrade (summary first, plain words, 54 trigger rules with playbooks, talk-track cards, incentive)

- **Summary first.** `nba/rule_summary.py` and `/api/rules/summary` count rules by type (risks, opportunities,
  guardrails, cadence, channel choice, content order, capacity and feedback) and report what each rule did in the
  last four weeks:
  - risks and opportunities: doctors picked out, and doctors acted on (moved into the plan)
  - guardrails and cadence: actions blocked or delayed
  - The studio now lists the whole catalogue grouped by family, with an expandable detail for each rule.
- **Plain words.** `nba/author_parse.py` is a phrase parser with no language model; `author.parse` had been
  deferred for lack of a key.
  - It turns a sentence into the rule form; `author.validate` then lists what is missing.
  - The five spec examples in `spec/authoring/examples.md` are tests, and so are eight ready-made prompts shown as chips.
  - When a model key exists, the parser stays as the fallback and the output is the same form.
- **More rules switched on.**
  - 22 catalogue rules switched on, plus 4 new rules (R137 to R140):
    - R137: email click → remote call
    - R138: webinar recording within 3 days
    - R139: an occasional user gone quiet
    - R140: a loyal prescriber invited to share their experience
  - 54 trigger rules on (was 28); 90 of 140 rules on overall.
  - The source remains `spec/rules/gen_rules.py`.
  - Seed 2026: lift +3.3 points (was +2.5). Spend −5.1% against control (was −5.6%); 1.8% under the plan budget.
- **Playbooks.** `spec/rules/playbooks.yaml` and `nba/playbook.py` turn "channel + theme" into a precise action:
  - email: sender, approved template, subject line, send window, follow-up steps, 7-day quiet period. The send
    window is learned from the doctor's own opens (weekday and part of day, 3+ opens), else their market and
    specialty, else the market default.
  - visit or call:
    - objective: the next rung of the adoption ladder
    - slide order: stage opener, then the theme, then a slide for the profile's barrier
    - the question to ask and the objection handler
    - leave-behind: a sample only for Movicol, prescribers and under the 4-a-year limit
    - follow-up within 48 hours, and a profile refresh if it is over a year old
  - Slide titles and subject lines are illustrative until they come from the MLR-approved documents.
- **Talk track as cards.** Last week at a glance; one card per doctor (why now, what to show, ask, objection,
  leave-behind, then); the bricks; and why these were chosen. The prose version is one click away, and the
  grounding check is unchanged.
- **Simulated incentive tracker.** `nba/incentive.py`, with weights and targets under `incentive` in the assumptions.
  - Measures: planned contacts done (40%), Movicol growth in the rep's bricks against a 12% target (40%), and
    suggestions acted on (20%).
  - Payout: nothing below 75% achievement, 100% at 100% achievement, capped at 150%.
  - It also shows the rep's rank in their market and what would move the payout. Not Norgine's real scheme.

## Look and feel: Omnisense, Genpact branding, light and dark themes

- The platform is called **Omnisense**: browser title, sidebar, home page and favicon.
  - The product mark: a ring of signals around a centre, with a Genpact Sunset Orange dot for the next best action.
- **Genpact logo:** the official mark taken from the Genpact deck template (paths unchanged), drawn in the current
  text colour so it reads on both themes. It appears in the sidebar ("by Genpact"), the sidebar footer ("Powered by") and on home.
- **Dark theme:** unchanged, and the default.
- **Light theme:** the Genpact brand palette.
  - Morning White and Sunrise Cream surfaces, Midnight Black text.
  - Sunset Orange as the working colour: buttons, bars, the test series.
  - Genpact Coral for labels and the control series.
  - Text in the accent colour uses a deeper orange, because Sunset Orange is too light for small text on white.
- The switch sits in the sidebar header and is remembered per browser. All screens read colour tokens: hard-coded
  colours in charts and maps were moved to the tokens, so both themes apply everywhere.
