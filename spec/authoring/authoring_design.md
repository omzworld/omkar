# Plain-language rule authoring and quick impact test

## Flow
1. Marketer types one or more sentences in the rule studio.
2. `author.parse(text)` calls the model with: the rule schema, the list of allowed columns from feature_columns.md,
   the allowed channels and content themes, the brand and market codes, and five worked examples. The model returns
   JSON: a rule record plus `missing_fields` and `assumptions_made`.
3. The form shows the record. Missing fields are highlighted in orange with a one-line prompt
   ("Which market?", "How many days is 'recently'?"). Assumptions the model made are shown in grey for confirmation.
4. `author.validate(rule)` checks every column and function in the condition against feature_columns.md and every
   channel, theme, brand and market against the code lists. Unknown concepts return "no data for this yet" with the
   nearest existing column suggested.
5. Quick test: `author.quick_test(rule, week=last_run_week)` evaluates the condition on the feature snapshot of that
   week, runs the constraints engine on the resulting triggers, and reports:
   - physicians and accounts matched
   - triggers allowed, delayed, blocked, by constraint
   - reps and key account managers who would receive at least one, by market and territory
   - how many would have fitted last week's capacity after the optimiser
   - overlap with existing rules (same account, same week, same channel)
6. Status moves draft -> tested -> approved. Approval by the brand lead writes the rule into the catalogue with the
   next free identifier and `enabled_at_launch: true`.

## Prompt contract for parse
- Output only JSON matching `rule_record_schema.json`.
- Never invent a column. If the sentence needs data that has no column, put the concept in `unsupported_concepts`.
- Put every threshold in `parameters` with a name, so the marketer can edit it.
- Write the reason template in the brand team's words, under 140 characters, with the parameters in braces.

## What the test screen says
"Tested on the week of {run_week}. A rule that depends on a monthly signal may show few matches in a quiet week."
