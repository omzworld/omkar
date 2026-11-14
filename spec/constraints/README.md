# Constraint tables

Owned by compliance (consent_rules, country_code) and brand (cadence) and field operations (capacity).
Each file is versioned with a date suffix in production; the engine loads the latest approved version.

Verdict order in the constraints engine:
1. Block rules (consent, country code, no-promotion, asset status) are evaluated first; a block stops evaluation.
2. Delay rules (cadence, caps, capacity) are evaluated next; the latest release date among them becomes the delay date.
3. Anything else is allowed.

Every verdict records the rule id that produced it, so the weekly summary can show blocked demand by constraint.
