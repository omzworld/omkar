"""Approved content (Veeva Vault PromoMats) and the IQVIA channel preference lookup.

Key messages are deliberately placeholders. No clinical claim is invented anywhere in the build.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Theme -> journey stage it is designed for ("any" = fits every stage).
THEMES = {
    "Movicol": {"introduction": "curiosity", "first_contact": "curiosity", "efficacy": "consideration",
                "clinical_evidence": "consideration", "guideline_update": "consideration",
                "economic_evidence": "consideration", "patient_case": "experience", "dosing": "experience",
                "paediatric": "experience", "chronic_constipation_elderly": "experience",
                "access": "loyalty", "pharmacy_support": "loyalty", "real_world_evidence": "loyalty",
                "peer_experience": "advocacy", "safety": "any", "event_invite": "any", "event_follow_up": "any"},
    "Plenvu_Moviprep": {"introduction": "curiosity", "first_contact": "curiosity", "efficacy": "consideration",
                        "clinical_evidence": "consideration", "low_volume_prep": "consideration",
                        "economic_evidence": "consideration", "cleansing_quality": "experience",
                        "dosing": "experience", "dosing_nursing": "experience", "patient_instructions": "experience",
                        "capacity_planning": "loyalty", "referral_pathway": "loyalty", "access": "loyalty",
                        "real_world_evidence": "loyalty", "peer_experience": "advocacy", "safety": "any",
                        "event_invite": "any", "event_follow_up": "any"},
    "Xifaxan": {"introduction": "curiosity", "first_contact": "curiosity", "efficacy": "consideration",
                "clinical_evidence": "consideration", "hepatic_encephalopathy_evidence": "consideration",
                "economic_evidence": "consideration", "recurrence_prevention": "experience", "dosing": "experience",
                "patient_case": "experience", "discharge_pathway": "loyalty", "access": "loyalty",
                "real_world_evidence": "loyalty", "peer_experience": "advocacy", "safety": "any",
                "event_invite": "any", "event_follow_up": "any"},
}
BRAND_CODE = {"Movicol": "MOV", "Plenvu_Moviprep": "PLV", "Xifaxan": "XIF"}
CORE_CHANNELS = ["rep_visit", "rep_email", "marketing_email"]
EXTRA_CHANNELS = {"clinical_evidence": ["webinar"], "efficacy": ["remote_call"], "dosing": ["remote_call"],
                  "introduction": ["direct_mail"], "dosing_nursing": ["kam_brief"], "capacity_planning": ["kam_brief"],
                  "cleansing_quality": ["kam_brief"], "discharge_pathway": ["kam_brief"]}
EVENT_ONLY = {"event_invite": ["marketing_email", "rep_email"], "event_follow_up": ["marketing_email", "rep_email"]}
CHANNEL_LABEL = {"rep_visit": "visit aid", "rep_email": "rep email", "marketing_email": "email",
                 "webinar": "webinar deck", "remote_call": "remote call aid", "direct_mail": "letter",
                 "kam_brief": "account brief"}
PREFERENCE_CHANNELS = ["marketing_email", "rep_email", "rep_visit", "remote_call", "webinar", "paid_media",
                       "portal", "direct_mail"]


def documents(rng: np.random.Generator, design: dict) -> pd.DataFrame:
    pilot = pd.Timestamp(design["clock"]["pilot_start"])
    rows = []
    for m, cfg in design["markets"].items():
        counter = {b: 0 for b in THEMES}
        for brand, themes in THEMES.items():
            for theme, stage in themes.items():
                channels = EVENT_ONLY.get(theme, CORE_CHANNELS + EXTRA_CHANNELS.get(theme, []))
                for ch in channels:
                    n_variants = 2 if rng.random() < 0.3 else 1
                    for v in range(1, n_variants + 1):
                        counter[brand] += 1
                        approved = pilot - pd.Timedelta(days=int(rng.integers(30, 700)))
                        status = "approved" if v == 1 else rng.choice(
                            ["approved", "expired", "in_review", "withdrawn"], p=[0.7, 0.12, 0.1, 0.08])
                        expiry = approved + pd.Timedelta(days=730)
                        if status == "approved" and rng.random() < 0.05:   # a few expire early in the pilot
                            expiry = pilot + pd.Timedelta(days=int(rng.integers(1, 14)))
                        if status == "expired":
                            expiry = pilot - pd.Timedelta(days=int(rng.integers(1, 200)))
                        title = theme.replace("_", " ")
                        msgs = "|".join(f"[Placeholder key message {k} for {brand} {title}: replace with "
                                        f"MLR-approved text]" for k in "ABC")
                        rows.append(dict(
                            document_id=f"{m}-{BRAND_CODE[brand]}-{counter[brand]:04d}",
                            name=f"{brand.replace('_', ' / ')} {title} ({CHANNEL_LABEL[ch]}) v{v}",
                            product=brand, content_theme=theme, journey_stage=stage, channel=ch, market=m,
                            language=cfg["language"], status=status, approval_date=approved,
                            expiration_date=expiry, variant_group=f"{m}-{BRAND_CODE[brand]}-{theme}-{ch}",
                            key_messages=msgs))
    return pd.DataFrame(rows)


def channel_preference(rng: np.random.Generator, design: dict) -> pd.DataFrame:
    """Market-level survey benchmark. Built from the population mix (not any physician's cluster),
    with survey noise, so it is a fair stand-in for a bought-in benchmark."""
    clusters = design["clusters"]
    rows = []
    for m in design["markets"]:
        adj = design["country_adjustment"].get(m, {})
        for s in design["specialty_mix"]:
            bench = {}
            for ch in PREFERENCE_CHANNELS:
                rate = sum(c["share"] * c["response_by_channel"].get(ch, 0) for c in clusters.values())
                bench[ch] = rate * adj.get(ch, 1.0) * rng.uniform(0.85, 1.15)
            total = sum(bench.values())
            for ch, b in bench.items():
                rows.append(dict(market=m, specialty=s, channel=ch, preference_share=round(b / total, 3),
                                 response_benchmark=round(b, 3), survey_year=2025))
    return pd.DataFrame(rows)
