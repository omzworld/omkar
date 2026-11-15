# Authoring examples used as test fixtures

| Sentence | Expected record | Expected missing | Expected quick test (synthetic week 8) |
|---|---|---|---|
| If a Movicol brick drops more than 8% and the GP has not seen a rep in two months, send a rep visit with the efficacy asset | family movicol, risk, condition `brick_volume_r3m_pct <= -{decline_pct} and brick_r3m_months_declining >= 2 and days_since_rep_visit >= {gap_days} and specialty == 'gp'` (rolling 3-month trend, confirmed in 2 of the last 3 monthly readings; changed during the build), action rep_visit / efficacy, parameters decline_pct 8, gap_days 60 | markets | matched 140 to 180 physicians; 20 to 30 reps |
| Invite gastroenterologists who opened our last two emails to the next webinar | family engagement_triggers, opportunity, condition `specialty == 'gastroenterology' and email_opens_30d >= 2`, action webinar / clinical_evidence | brand, markets, time window | matched 60 to 90; blocked by webinar cap for some |
| Send the paediatric asset to paediatric prescribers who have never had it | family movicol, opportunity, condition `paediatric_prescriber == True and theme_received('paediatric') == False`, action marketing_email / paediatric | markets | matched 200 to 260; blocked where no email consent |
| Flag physicians who attended a competitor's symposium | unsupported_concepts: competitor event attendance | all | no data for this yet |
| KAM brief when an endoscopy unit's procedures rise 15% in a quarter | family bowel_preparations, opportunity, condition `account_type == 'endoscopy_unit' and unit_procedure_volume_qoq_pct >= {proc_pct}`, action kam_brief / dosing_nursing, proc_pct 15 | markets, brand confirmed as Plenvu_Moviprep | matched 10 to 18 units; 6 to 10 KAMs |

Counts are ranges because the synthetic data is seeded; the test asserts the range.
