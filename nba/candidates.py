"""Turn triggers into candidate actions: one concrete channel, theme and approved asset each.

A trigger says "Dr A needs a rep visit about the next theme". A candidate says "Dr A, rep visit, dosing, asset
UK-MOV-0042". Three things get resolved here:
- channel: `next_best` becomes one candidate per main channel, and the optimiser keeps the best one;
- theme: `next_theme` follows the content sequence rules (R063-R066), and a theme ignored twice moves on (R070);
- asset: an approved PromoMats asset for the brand, market, theme and channel (or the best available, so that
  the constraints engine can say why it cannot be used).
Each candidate also gets the candidate-level columns from feature_columns.md that the constraints engine and the
optimiser need.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nba import data
from nba.features import Features
from nba.rules.catalogue import load

NEXT_BEST_CHANNELS = ["rep_visit", "rep_email", "marketing_email"]
THEME_SEQUENCE = ["introduction", "efficacy", "patient_case", "dosing", "real_world_evidence", "peer_experience"]
STAGE_DEFAULT_THEME = {"curiosity": "efficacy", "consideration": "patient_case", "experience": "dosing",
                       "loyalty": "real_world_evidence", "advocacy": "peer_experience"}
FOLLOW_LAST_THEME = {"same_theme", "as_discussed", "as_requested"}
# Rep-delivered channels that can fall back to a rep email when the rep has no slot left.
SUBSTITUTE = {"rep_visit": "rep_email", "remote_call": "rep_email", "kam_visit": "kam_brief"}
STATUS_ORDER = {"approved": 0, "in_review": 1, "expired": 2, "withdrawn": 3}


def _expand(triggers: pd.DataFrame) -> pd.DataFrame:
    """One row per trigger, except next_best triggers, which become one row per main channel."""
    nb = triggers.channel == "next_best"
    expanded = triggers[nb].drop(columns="channel").merge(pd.DataFrame({"channel": NEXT_BEST_CHANNELS}), how="cross")
    out = pd.concat([triggers[~nb], expanded], ignore_index=True)
    out["candidate_id"] = out.trigger_id + "-" + out.channel
    return out


def _sequence_rules():
    return [r for r in load(enabled_only=True) if r.family == "content_sequence"]


def resolve_themes(c: pd.DataFrame, feats: Features) -> pd.Series:
    """The content theme for each candidate, following the content sequence rules."""
    theme = c.content_theme.copy()
    follow = theme.isin(FOLLOW_LAST_THEME)
    theme[follow] = c.loc[follow, "last_touch_theme"].fillna("efficacy")
    nxt = theme == "next_theme"
    if nxt.any():
        chosen = c.loc[nxt, "stage"].map(STAGE_DEFAULT_THEME).fillna("efficacy")
        ctx = feats.context()
        for rule in _sequence_rules():            # later rules refine earlier ones (R065 after R064)
            if rule.content_theme in ("next_theme", "same_theme", "best_variant"):
                continue
            fires = rule.condition().evaluate(c[nxt].assign(content_theme=chosen), ctx)
            chosen[fires] = rule.content_theme
        theme[nxt] = chosen
    # R070-style rules: a theme ignored twice moves on to the next theme in the sequence.
    ctx = feats.context()
    for rule in _sequence_rules():
        if rule.content_theme == "next_theme":
            moved = rule.condition().evaluate(c.assign(content_theme=theme), ctx) & theme.isin(THEME_SEQUENCE[:-1])
            theme[moved] = theme[moved].map(lambda t: THEME_SEQUENCE[THEME_SEQUENCE.index(t) + 1])
    return theme


def _assets(c: pd.DataFrame, as_of: pd.Timestamp, data_dir) -> pd.DataFrame:
    """Best available asset per candidate: approved and in date first, then whatever exists."""
    docs = data.read_table("promomats_document", data_dir)
    docs = docs[pd.to_datetime(docs.approval_date) < as_of].copy()
    docs["rank"] = docs.status.map(STATUS_ORDER).astype(int) * 2 + (pd.to_datetime(docs.expiration_date) <= as_of).astype(int)
    docs = docs.sort_values(["rank", "document_id"]).drop_duplicates(["market", "product", "content_theme", "channel"])
    docs = docs.rename(columns={"product": "brand", "document_id": "asset_id", "status": "asset_status",
                                "market": "asset_market", "language": "asset_language"})
    out = c.merge(docs[["asset_market", "brand", "content_theme", "channel", "asset_id", "asset_status",
                        "asset_language", "expiration_date", "key_messages"]],
                  left_on=["market", "brand", "content_theme", "channel"],
                  right_on=["asset_market", "brand", "content_theme", "channel"], how="left")
    out["days_to_asset_expiry"] = (pd.to_datetime(out.expiration_date) - as_of).dt.days
    return out.drop(columns="expiration_date")


def _plan_asset_fallback(c: pd.DataFrame, as_of: pd.Timestamp, data_dir) -> pd.DataFrame:
    """A planned touch whose chosen theme has no approved, in-date asset in the physician's language uses the next
    theme in the content sequence that has one, rather than being blocked week after week."""
    if "origin" not in c or not (c.origin == "plan").any():
        return c
    bad = (c.origin == "plan") & ((c.asset_status != "approved") | (c.days_to_asset_expiry <= 0)
                                  | (c.asset_language.notna() & (c.asset_language != c.hcp_language)))
    if not bad.any():
        return c
    docs = data.read_table("promomats_document", data_dir)
    docs = docs[(docs.status == "approved") & (pd.to_datetime(docs.approval_date) < as_of)
                & (pd.to_datetime(docs.expiration_date) > as_of)].sort_values("document_id")
    order = {t: i for i, t in enumerate(THEME_SEQUENCE)}
    c = c.copy()
    for i in c.index[bad]:
        r = c.loc[i]
        opts = docs[(docs.market == r.market) & (docs["product"] == r.brand) & (docs.channel == r.channel)
                    & (docs.language == r.hcp_language)]
        if opts.empty:
            continue
        start = order.get(r.content_theme, 0)
        # Content for the physician's own stage first (only that moves them, as the history shows), then the
        # next theme in the sequence.
        opts = opts.assign(o=opts.content_theme.map(lambda t: (order.get(t, 99) - start) % 100),
                           off=(opts.journey_stage != r.stage).astype(int))
        pick = opts.sort_values(["off", "o", "document_id"]).iloc[0]
        c.loc[i, ["content_theme", "asset_id", "asset_status", "asset_market", "asset_language", "key_messages"]] = \
            [pick.content_theme, pick.document_id, "approved", pick.market, pick.language, pick.key_messages]
        c.loc[i, "days_to_asset_expiry"] = (pd.to_datetime(pick.expiration_date) - as_of).days
    return c


def _history(c: pd.DataFrame, feats: Features) -> pd.DataFrame:
    """The physician's and the segment's touches and response rate on the candidate's channel."""
    cs = feats.channel_stats
    own = c[["hcp_id", "channel"]].merge(cs, on=["hcp_id", "channel"], how="left")
    seg = cs.merge(feats.table[["hcp_id", "market", "specialty"]], on="hcp_id") \
        .groupby(["market", "specialty", "channel"])[["touches", "responses"]].sum().reset_index()
    seg_c = c[["market", "specialty", "channel"]].merge(seg, on=["market", "specialty", "channel"], how="left")
    c = c.copy()
    c["hcp_touch_count_channel"] = own.touches.fillna(0).astype(int).to_numpy()
    c["hcp_response_rate_channel"] = (own.responses / own.touches).round(3).to_numpy()
    c["touches_this_month_channel"] = own.touches_this_month.fillna(0).astype(int).to_numpy()
    c["segment_touch_count_channel"] = seg_c.touches.fillna(0).astype(int).to_numpy()
    c["segment_response_rate_channel"] = (seg_c.responses / seg_c.touches).round(3).to_numpy()
    return c


def build(triggers: pd.DataFrame, feats: Features, data_dir=None) -> pd.DataFrame:
    """Candidate actions with every column the constraints engine and the optimiser read."""
    if triggers.empty:
        return pd.DataFrame()
    c = _expand(triggers)
    trigger_cols = ["candidate_id", "trigger_id", "hcp_id", "rule_id", "rule_ids", "family", "trigger_type", "channel",
                    "content_theme", "timing", "priority", "reason", "origin"]
    c = c[trigger_cols].merge(feats.table, on="hcp_id", how="left")
    c["content_theme"] = resolve_themes(c, feats)
    c = _assets(c, feats.as_of, data_dir)
    c = _plan_asset_fallback(c, feats.as_of, data_dir)
    # Same theme already received in the last 7 days, on any channel (recomputed for the candidate's theme).
    days = feats.context().theme_received_days_ago(c, c.content_theme)
    c["same_theme_touches_7d"] = (days <= 7).astype(int)
    c = _history(c, feats)
    terr = data.read_table("territory_vod", data_dir).set_index("id")
    c["rep_user_id"] = c.territory_id.map(terr.rep_user_id)
    c["kam_user_id"] = c.territory_id.map(terr.kam_user_id)
    c["substitute_channel"] = c.channel.map(SUBSTITUTE)
    c["detector"], c["discovery_score"], c["explanation"] = None, np.nan, None
    c["weeks_waiting"] = 0
    return c.reset_index(drop=True)
