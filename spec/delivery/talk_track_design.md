# Rep talk track

One brief per rep per week, under 300 words, replacing the list of suggestions as the rep's view. The Veeva
suggestion records are still written; the talk track references them by title.

## Structured brief (built by delivery.rep_brief before any prose is written)
- territory: name, market, week
- last_week: visits completed, suggestions accepted and dismissed, emails sent and opened, webinar attendance,
  brick trend for the top three bricks (volume and quarter-on-quarter change), any dismissal reason pattern
- suggestions: ranked list from the optimiser, each with physician, account, channel, theme, reason, expected return,
  key_messages from the PromoMats asset, and what to listen for (one line from the rule's family, for example
  "ask what changed in the practice" for a brick-decline risk)
- discovery_note: if any suggestion has origin discovery, one sentence saying so

## Prose (written by the model from the structured brief)
Sections, in order: "Your territory last week", "This week's suggestions", "Why".
- Every number in the prose must appear in the structured brief. The grounding check parses the prose for numbers
  and asserts each is present in the brief; on failure, the template version is used and the failure is logged.
- Key messages are quoted verbatim from the asset. No clinical claim may be written that is not a key message.
- Plain language, no jargon, no exclamation marks, the suggestions in optimiser order.

## Example (synthetic)
Your territory last week. You completed 18 of 25 planned visits. Six suggestions were accepted and two dismissed,
both marked seen recently. Brick NW-14 is down 9% on the prior quarter; NW-07 and NW-22 are flat.

This week's suggestions.
1. Dr Weber, Lindenstrasse practice: visit, efficacy asset. Why: brick NW-14 down 9%, no visit in 64 days.
   Key message: "Movicol achieved X in the Y study." Listen for: what changed in the practice.
2. Dr Okafor: rep email, patient case. Why: opened two efficacy emails, clicked once. Key message: ...
3. Dr Lind: visit, dosing asset. Why: attended the dosing webinar nine days ago.

Why these three. They have the highest expected return of eleven candidates in your territory; four were held
by cadence, two by capacity, two by consent.

## Key account manager brief
Same structure per account: the account's signal (procedure volume, formulary status), the stakeholders, the
suggested sequence, key messages per role.
