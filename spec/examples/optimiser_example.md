# Optimiser hand-calculated example (used as a test fixture)

One rep, three visit slots this week. Five allowed triggers. Costs from return_assumptions.yaml: rep_visit 150, rep_email 10.

| Physician | Trigger | Chance | Value | Cost | Expected return | Result |
|---|---|---|---|---|---|---|
| Dr A | Brick decline, efficacy visit | 0.50 | 900 | 150 | 300 | Visit, slot 1 |
| Dr B | Webinar attended, dosing visit | 0.55 | 700 | 150 | 235 | Visit, slot 2 |
| Dr C | New in target brick, intro visit | 0.40 | 600 | 150 | 90 | Visit, slot 3 |
| Dr D | No contact 60 days, efficacy visit | 0.30 | 500 | 150 | 0 | Substituted: rep email 0.25 × 500 − 10 = 115 |
| Dr E | Low-tier, intro visit | 0.20 | 300 | 150 | −90 | Not sent: negative return |

Rules applied in order: score, keep best per physician, fill slots by return per slot, substitute cheaper channel,
drop non-positive. Expected outputs: 3 visits, 1 rep email, 1 dropped with reason "expected return not positive".
