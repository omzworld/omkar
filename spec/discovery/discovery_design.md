# Discovery module: risks and opportunities the rules did not cover

Runs after the rules engine each week. Produces `ml_candidate` rows with origin `discovery`. Candidates go through
the same constraints engine and optimiser. The optimiser caps discovery items at 10% of sent items per market,
highest expected return first. No detector may read hidden cluster propensities; a test asserts this.

## Detector 1: change detection
- Input: four-week deltas per physician and per brick: engagement (opens, clicks, attendance), brick volume,
  procedure volume, consent, touches.
- Method: robust z-score of each delta against the physician's own 24-month history and against the segment.
  Score = max absolute z across signals, scaled to 0 to 1.
- Risk when engagement or volume falls sharply with no rule trigger; opportunity when it rises sharply.
- Suggested action: for risk, the rep channel with the current stage's theme; for opportunity, the next theme on
  the physician's best channel.

## Detector 2: propensity to move
- Input: feature table columns plus 24 months of stage history.
- Method: gradient boosting classifier predicting a stage move within eight weeks. Trained once on history, scored
  weekly. Explanations from SHAP values; top three features become the explanation text.
- Opportunity when propensity is above the 90th percentile of the segment and no rule fired for that physician.
- Risk when propensity for physicians in experience or loyalty falls by more than 0.2 over four weeks.

## Detector 3: look-alikes
- Input: physicians who responded to a touch in the last four weeks (responders) and all others.
- Method: nearest neighbours on standardised feature vectors. A non-responder whose five nearest neighbours are
  responders to the same theme, and for whom no rule fired, becomes an opportunity with that theme and channel.

## Scoring and explanation
- Each candidate has a score in 0 to 1. Only candidates above `min_score_to_consider` (0.6) go forward.
- Explanation template: "Found by discovery. {detector}: {feature_1} {direction_1}, {feature_2} {direction_2},
  {feature_3} {direction_3}. Similar physicians moved stage within eight weeks in {pct}% of cases."

## Cap and reporting
- In the optimiser, rule triggers fill first. Discovery items may take up to 10% of sent items per market. Items
  above the cap roll to next week with the reason "discovery cap".
- The weekly summary shows: discovery candidates, passed constraints, selected, share of sent, and acceptance.

## Proposed rules
- When the same detector and the same top feature pattern recur for three weeks with at least 20 candidates and an
  acceptance rate above 40%, the module writes a `proposed_rule` row with a plain-language sentence, for example
  "Physicians whose email opens fell by half in four weeks and who are in experience stage: rep visit with the
  dosing asset." The brand team can accept it as a draft in the rule studio, which hands it to the author module.

## Training in the MVP
- Models are trained on the synthetic 24-month history at `nba synth` time and saved under `models/`.
- Retraining on live data is out of scope for the MVP.
