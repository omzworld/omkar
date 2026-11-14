"""Feature table: one row per account per run week, with every account-level column in feature_columns.md.

Week 1 is the pilot start in synthetic_design.yaml; week N is N-1 weeks later. The table only uses data
from before that date. Each build is saved under data/snapshots/ so the quick impact test and the audit
trail can replay exactly what the engine saw.

Columns with no source in the synthetic data (formulary, tenders, waiting lists, ...) are present with a
neutral value (blank or False), so rules that use them simply do not fire. See docs/decisions.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from nba import columns, data, spec
from nba.features import market, touches
from nba.rules.expr import Context
from nba.segments import BRAND, assign_tier, specialty_weight

NO_SOURCE_FALSE = ["hcp_on_leave", "on_named_list", "medical_inquiry_30d", "survey_response_30d",
                   "referral_to_hepatology_flag", "quota_pressure_flag", "otc_switch_signal", "nhs_waiting_list_signal",
                   "readmission_signal", "screening_programme_expansion", "new_endoscopist_joined",
                   "discharge_pathway_project", "treatment_centre_flag", "patient_identified_signal",
                   "hub_enrolment_pending", "msl_contact_completed"]
NO_SOURCE_BLANK = ["survey_interest", "referral_volume_qoq_pct", "formulary_status_changed",
                   "days_since_formulary_change", "formulary_review_days", "guideline_update_days_ago",
                   "tender_window_days", "reimbursement_decision_days", "unit_quality_audit_due_days",
                   "patient_organisation_event_days", "rule_accept_rate_30d", "rule_triggers_30d",
                   "propensity_to_move_8w", "look_alike_similarity"]
COUNTS_ZERO = ["touches_30d", "touches_month", "touches_ignored_consecutive", "rep_visits_90d", "email_sent_30d",
               "email_opens_30d", "email_clicks_30d", "emails_ignored_consecutive", "webinar_invites_30d",
               "same_theme_touches_7d", "portal_visits_30d", "media_impressions_30d", "dismissals_30d",
               "touches_delta_4w", "engagement_delta_4w", "samples_ytd"]
FLAGS_FALSE = ["email_sent_14d", "email_opened_14d", "unsubscribe_30d", "webinar_registered_30d",
               "webinar_attended_30d", "event_registered", "consent_email", "consent_double_opt_in",
               "consent_remote", "consent_digital_tracking", "opt_out_any", "last_touch_responded"]
HOLIDAY_WEEKS = {"UK": ["2026-12-21", "2026-12-28", "2027-03-22", "2027-03-29", "2027-05-03"],
                 "DE": ["2026-12-21", "2026-12-28", "2027-03-22", "2027-03-29", "2027-05-10"]}


@dataclass
class Features:
    week: int
    as_of: pd.Timestamp
    table: pd.DataFrame       # one row per account
    themes: pd.DataFrame      # one row per (hcp_id, theme) received
    variants: pd.DataFrame    # approved asset variants per (market, theme, channel)

    def context(self) -> Context:
        return Context(themes=self.themes, variants=self.variants)


def as_of(week: int) -> pd.Timestamp:
    return pd.Timestamp(spec.design()["clock"]["pilot_start"]) + pd.Timedelta(weeks=week - 1)


def _accounts(con) -> pd.DataFrame:
    return con.execute("""
        select a.id as hcp_id, a.market, a.account_type, a.hcp_type, a.hcp_role, a.specialty_1_vod as specialty,
               a.primary_parent_id, a.brick_id, a.territory_id, a.language as hcp_language, a.status as hcp_status,
               m.practice_type, m.practice_size, m.year_of_birth, m.no_promo_flag, m.prescriber as hcp_prescriber,
               m.paediatric_prescriber, m.care_home_prescriber, m.expert_status,
               ad.rural_flag, ad.postal_address_verified,
               t.pilot_arm, t.vacant as territory_vacant, t.rep_user_id, t.kam_user_id,
               h.unit_tier as own_unit_tier, h.liver_unit_flag as own_liver_unit,
               ph.hco_type as parent_type, ph.unit_tier as parent_unit_tier, ph.liver_unit_flag as parent_liver_unit
        from account_vod a
        left join hcp_master_opendata m on m.onekey_id = a.onekey_id
        left join address_vod ad on ad.account_id = a.id and ad."primary"
        left join territory_vod t on t.id = a.territory_id
        left join hco_master_opendata h on h.hco_id = a.id
        left join hco_master_opendata ph on ph.hco_id = a.primary_parent_id
        order by a.id
    """).df()


def _brand(f: pd.DataFrame) -> pd.Series:
    hco = np.select([f.account_type == "endoscopy_unit", (f.account_type == "hospital") & f.own_liver_unit.fillna(False),
                     f.account_type == "hospital", f.account_type.isin(["pharmacy", "practice"])],
                    ["Plenvu_Moviprep", "Xifaxan", "Plenvu_Moviprep", "Movicol"], default=None)
    return f.specialty.map(BRAND).fillna(pd.Series(hco, index=f.index))


def _tiers(f: pd.DataFrame, potential: pd.Series) -> np.ndarray:
    """Tier from brick potential x specialty weight x practice size; organisations use their unit tier."""
    is_hcp = f.account_type == "hcp"
    score = f.brick_id.map(potential).fillna(100) * f.specialty.map(specialty_weight()).fillna(0.6) \
        * np.log1p(f.practice_size.fillna(1))
    tier = pd.Series(f.own_unit_tier.fillna("C").to_numpy(), index=f.index)
    hcps = f[is_hcp].assign(score=score[is_hcp])
    tier[is_hcp] = assign_tier(hcps, "score")
    return tier.to_numpy()


def _channel_lean(f: pd.DataFrame) -> np.ndarray:
    """Digital or rep, from the physician's own response history relative to their market; default if thin."""
    email_rate = f.email_responses_total / f.emails_total.where(f.emails_total >= 5)
    visit_rate = f.visit_responses_total / f.visits_total.where(f.visits_total >= 3)
    e_idx = email_rate / email_rate.groupby(f.market).transform("mean")
    v_idx = visit_rate / visit_rate.groupby(f.market).transform("mean")
    lean = np.where(e_idx - v_idx > 0.3, "digital", np.where(v_idx - e_idx > 0.3, "rep", "default"))
    return np.where(e_idx.isna() | v_idx.isna(), "default", lean)


def _segment(f: pd.DataFrame) -> np.ndarray:
    lean = np.where(f.channel_lean == "digital", "digital_lean", "rep_lean")
    hcp = np.select([f.tier == "A", f.tier == "B"], ["high_potential_" + lean, "mid_potential_" + lean],
                    "low_potential_any")
    return np.select([f.account_type == "endoscopy_unit", f.account_type == "hospital", f.account_type == "pharmacy",
                      f.account_type == "hcp"], ["endoscopy_unit", "hospital_account", "pharmacy", hcp],
                     "low_potential_any")


def build(week: int, data_dir: Path | None = None, save: bool = True) -> Features:
    when = as_of(week)
    con = data.connect(data_dir)
    f = _accounts(con)
    t = touches.build(con, when)
    m = market.build(con, when)

    for part in [t["touches"], t["media"], t["events"], t["stages"], m["consent"], m["unsubs"], m["feedback"]]:
        f = f.merge(part.rename(columns={"account_id": "hcp_id"}), on="hcp_id", how="left")
    f = f.merge(m["bricks"], on="brick_id", how="left")
    is_unit = f.account_type.isin(["endoscopy_unit", "hospital"])
    f["unit_id"] = np.where(is_unit, f.hcp_id, np.where(f.parent_type.isin(["endoscopy_unit", "hospital"]),
                                                        f.primary_parent_id, None))
    f = f.merge(m["units"], on="unit_id", how="left")
    kam = t["kam"].set_index("account_id").days_since_kam_visit
    f["days_since_kam_visit"] = f.hcp_id.map(kam).fillna(f.primary_parent_id.map(kam))
    f["unit_tier"] = f.own_unit_tier.fillna(f.parent_unit_tier)
    f["liver_unit_flag"] = f.own_liver_unit.fillna(f.parent_liver_unit).fillna(False).astype(bool)

    # identity and placement
    lang = {mk: c["language"] for mk, c in spec.design()["markets"].items()}
    f["market_language"] = f.market.map(lang)
    age = (when.year - f.year_of_birth).astype(float)
    f["age_band"] = pd.cut(age, [0, 40, 55, 200], right=False, labels=["under_40", "40_to_54", "55_plus"]).astype(object)
    f["brand"] = _brand(f)
    potential = m["bricks"].set_index("brick_id").brick_potential_index
    f["tier"] = _tiers(f, potential)
    earlier = {d: _tiers(f, m[f"potential_{d}d_ago"].set_index("brick_id").potential) for d in (30, 60, 90)}
    hcp_ab = (f.account_type == "hcp") & f.tier.isin(["A", "B"])
    f["new_in_target"] = hcp_ab & (earlier[90] == "C")
    f["days_since_added"] = np.where(f.new_in_target, np.select(
        [earlier[30] == "C", earlier[60] == "C"], [15, 45], 75), np.nan)
    f["channel_lean"] = _channel_lean(f)
    f["segment"] = _segment(f)
    cad = spec.constraint_table("cadence").set_index("segment")
    for col in columns.groups()["cadence limits"]:
        f[col] = f.segment.map(cad[col])

    # consent, eligibility, events, market and account signals
    f["is_public_holiday_week"] = f.market.map(lambda mk: when.strftime("%Y-%m-%d") in HOLIDAY_WEEKS.get(mk, []))
    stage_q = t["stage_last_qtr"].set_index("account_id").stage_last_qtr
    f["prescribed_last_qtr"] = (f.brand == "Xifaxan") & f.hcp_id.map(stage_q).isin(["experience", "loyalty", "advocacy"])
    f["advocacy_candidate"] = f.stage.isin(["loyalty", "advocacy"]) & f.ever_attended.fillna(False).astype(bool)
    f["procedure_volume_delta_4w"] = f.unit_procedure_volume_qoq_pct
    f["consent_delta_4w"] = f.consent_gained_4w.fillna(0) - f.unsubscribes_4w.fillna(0)

    # field and feedback
    cap = con.execute("select user_id, visit_slots_open from rep_capacity where week = $w",
                      {"w": when.date()}).df().set_index("user_id").visit_slots_open
    f["rep_capacity_slots_week"] = f.rep_user_id.map(cap)
    f["kam_capacity_week"] = f.kam_user_id.map(cap)
    f["week_of_month"] = (when.day - 1) // 7 + 1

    for col in NO_SOURCE_FALSE:
        f[col] = False
    for col in NO_SOURCE_BLANK:
        f[col] = np.nan
    for col in COUNTS_ZERO:
        f[col] = f.get(col, pd.Series(0, index=f.index)).fillna(0).astype(int)
    for col in FLAGS_FALSE:
        f[col] = f[col].astype("boolean").fillna(False).astype(bool)
    f["stage_regressed"] = f.stage_regressed.astype("boolean").fillna(False).astype(bool)
    f["no_promo_flag"] = f.no_promo_flag.astype("boolean").fillna(False).astype(bool)

    keep = columns.account_columns()
    missing = [c for c in keep if c not in f.columns]
    if missing:
        raise RuntimeError(f"feature builder does not produce: {missing}")
    table = f[keep].copy()
    table.insert(1, "run_week", when)
    variants = con.execute("""
        select market, product as brand, content_theme, channel, count(*) as n from promomats_document
        where status = 'approved' and approval_date < $w and expiration_date > $w group by all
    """, {"w": when.date()}).df()
    feats = Features(week, when, table, t["themes"], variants)
    if save:
        save_snapshot(feats, data_dir)
    return feats


def _snap_dir(data_dir: Path | None) -> Path:
    return (Path(data_dir) if data_dir else spec.data_dir()) / "snapshots"


def save_snapshot(feats: Features, data_dir: Path | None = None) -> None:
    d = _snap_dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    feats.table.to_parquet(d / f"features_w{feats.week:02d}.parquet", index=False)
    feats.themes.to_parquet(d / f"themes_w{feats.week:02d}.parquet", index=False)
    feats.variants.to_parquet(d / f"variants_w{feats.week:02d}.parquet", index=False)


def load_snapshot(week: int, data_dir: Path | None = None) -> Features:
    d = _snap_dir(data_dir)
    return Features(week, as_of(week), pd.read_parquet(d / f"features_w{week:02d}.parquet"),
                    pd.read_parquet(d / f"themes_w{week:02d}.parquet"),
                    pd.read_parquet(d / f"variants_w{week:02d}.parquet"))
