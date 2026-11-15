# Feature table columns

One row per account per run week. Built fresh every run from the standard datasets. Every column referenced by a
rule condition must be here; the catalogue test fails if a rule references a missing column.

## Identity and placement
hcp_id, market, account_type, hcp_type, hcp_role, specialty, practice_type, practice_size, rural_flag, age_band,
hcp_language, market_language, brick_id, territory_id, pilot_arm, tier (A, B, C from brick potential and specialty weight),
channel_lean (digital, rep, default), stage, prev_stage, stage_regressed, days_in_stage, segment (cadence.csv key),
tier derived from brick_potential_index and practice_size; new_in_target, days_since_added, on_named_list, expert_status,
brand (the account's main brand; rules with a brand apply only to matching accounts)

## Consent and eligibility
consent_email, consent_double_opt_in, consent_remote, consent_digital_tracking, opt_out_any, no_promo_flag, hcp_status,
hcp_prescriber, postal_address_verified, samples_ytd, hcp_on_leave, is_public_holiday_week

## Touch history
days_since_last_touch, last_touch_channel, last_touch_theme, last_touch_responded, touches_30d, touches_month,
touches_ignored_consecutive, days_since_rep_visit, rep_visits_90d, rep_visit_completed_days_ago, rep_visit_next_step,
days_since_last_email, email_sent_30d, email_opens_30d, email_clicks_30d, emails_ignored_consecutive, email_sent_14d,
email_opened_14d, unsubscribe_30d, webinar_invites_30d, webinar_registered_30d, webinar_attended_30d, days_since_webinar,
portal_visits_30d, portal_content_viewed, media_impressions_30d, same_theme_touches_7d, medical_inquiry_30d,
survey_response_30d, survey_interest, days_since_kam_visit

## Theme functions (evaluated by the rules engine)
theme_received(theme) -> bool, theme_received_days_ago(theme) -> int, theme_ignored_count(theme) -> int,
asset_variant_count(theme, channel) -> int

## Events
event_type, event_upcoming_days, event_registered, event_attended_days_ago

## Market signals
brick_volume_qoq_pct, brick_potential_index, brick_competitor_share_change, pharmacy_dispensing_qoq_pct,
prescribed_last_qtr (Xifaxan panel or brick proxy), referral_volume_qoq_pct, referral_to_hepatology_flag,
formulary_status_changed, days_since_formulary_change, formulary_review_days, quota_pressure_flag, otc_switch_signal,
guideline_update_days_ago, nhs_waiting_list_signal, tender_window_days, readmission_signal, reimbursement_decision_days,
brick_volume_r3m_pct (rolling trend added during the build: last 3 complete months against the 3 before),
brick_volume_r3m_yoy_pct (last 3 complete months against the same 3 months a year earlier),
brick_units_r3m (Movicol units in the last 3 complete months; used to leave out very small bricks),
brick_r3m_months_declining (how many of the last 3 monthly readings of brick_volume_r3m_pct were below zero),
brick_r3m_months_growing (how many of the last 3 monthly readings of brick_volume_r3m_pct were above zero),
brick_competitor_share_r3m_change (competitor share of the brick in the last 3 months minus the 3 before; points),
brick_share_months_rising (how many of the last 3 monthly readings of that share change were above zero)

## Accounts (endoscopy units, hospitals)
unit_id, unit_tier, unit_procedure_volume_qoq_pct, unit_competitor_share_change, inadequate_prep_rate_reported,
unit_quality_audit_due_days, screening_programme_expansion, new_endoscopist_joined, liver_unit_flag,
discharge_pathway_project, treatment_centre_flag, patient_identified_signal, patient_organisation_event_days,
hub_enrolment_pending, msl_contact_completed, advocacy_candidate, care_home_prescriber, paediatric_prescriber,
unit_colonoscopies_qtr (procedures last quarter; added during the build for the Plenvu/Moviprep value of response)

## Cadence limits (looked up from cadence.csv by segment; added during the build)
cap_touches_month, min_gap_days_any, min_gap_days_rep_visit, min_gap_days_email, gap_after_two_ignored_days,
no_same_theme_days

## Field and feedback
rep_capacity_slots_week, kam_capacity_week, territory_vacant, dismissals_30d, last_dismiss_reason, days_since_dismiss,
suggestion_accept_rate_90d, rule_accept_rate_30d, rule_triggers_30d, week_of_month

## Candidate-level columns (one row per candidate action, built by the optimiser)
channel, content_theme, asset_id, asset_status, asset_market, asset_language, days_to_asset_expiry,
hcp_touch_count_channel, hcp_response_rate_channel, segment_touch_count_channel, chance_tier,
probability_of_response, value_of_response, cost_of_touch, decay_factor, expected_return, substitute_return, trigger_type,
origin (rule or discovery), detector, discovery_score, explanation

## Discovery inputs (weekly deltas, built by features for the discover module)
engagement_delta_4w, brick_volume_delta_4w, procedure_volume_delta_4w, consent_delta_4w, touches_delta_4w,
propensity_to_move_8w (written back by discover), look_alike_similarity (written back by discover)
