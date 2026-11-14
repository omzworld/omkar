"""Simulate 24 months of today's multi-channel plan, week by week, to create the baseline history.

Today's plan (from synthetic_design.yaml, history_simulation): reps visit by tier, the agency sends a
monthly email calendar that ignores who responds, one webinar a quarter, a few congresses, and paid media.
Each touch picks an approved asset at random (no sequencing), so the history contains the inefficiency
the engine is meant to fix. Responses and stage moves come from the hidden behaviour model.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nba.synth.behaviour import ANY_STAGE, STAGE_INDEX, Behaviour

CHANNELS = ["marketing_email", "rep_email", "rep_visit", "remote_call", "webinar", "paid_media", "portal", "direct_mail"]
WEEKS_PER_MONTH = 52 / 12
REP_EMAIL_PER_MONTH = 0.4          # not in the design file; reps send a few approved emails today
CLICK_GIVEN_OPEN = 0.35
UNSUBSCRIBE_PER_EMAIL = 0.0008
# (week of the two-year history, event type, who is invited, share invited)
EVENTS = [(20, "congress", "primary", 0.10), (72, "congress", "primary", 0.10),
          (30, "endoscopy_congress", "endoscopy", 0.40), (82, "endoscopy_congress", "endoscopy", 0.40),
          (45, "hepatology_congress", "hepatology", 0.50), (97, "hepatology_congress", "hepatology", 0.50),
          (55, "speaker_programme", "experts", 1.0), (60, "advisory_board", "experts", 0.5)]
AUDIENCE = {"primary": ["gp", "internal_medicine", "paediatrics"], "endoscopy": ["gastroenterology", "endoscopy_nurse"],
            "hepatology": ["hepatology"]}


class History:
    def __init__(self, rng: np.random.Generator, design: dict, world: dict, docs: pd.DataFrame):
        self.rng, self.design = rng, design
        h = world["hcp"]
        self.h, self.n = h, len(h)
        self.start = pd.Timestamp(design["clock"]["history_start"])
        self.n_weeks = (pd.Timestamp(design["clock"]["history_end"]) - self.start).days // 7
        self.beh = Behaviour(design, h.cluster.to_numpy(), h.market.to_numpy(), CHANNELS)
        self.stage = h.stage0.to_numpy().astype(int).copy()

        c = world["consent"].set_index(["account_id", "channel"])
        def granted(ch):
            return (c.xs(ch, level="channel").reindex(h.id)["status"] == "granted").to_numpy().copy()
        email = c.xs("marketing_email", level="channel").reindex(h.id)
        self.email_active = granted("marketing_email")
        self.email_since = pd.to_datetime(email["captured_date"]).to_numpy()
        self.double_ok = ((h.market != "DE").to_numpy() | (email["consent_type"] == "double_opt_in").to_numpy())
        self.remote_ok, self.digital_ok = granted("remote_call"), granted("paid_media")
        self.unsub_week = np.full(self.n, -1)

        self.eligible = ((h.status == "active") & ~h.no_promo_flag & (h.hcp_role != "medical_only_contact")).to_numpy()
        terr = world["territories"].set_index("id")
        self.rep = h.territory_id.map(terr.rep_user_id).to_numpy()
        self.has_rep = pd.notna(self.rep)
        plan = design["history_simulation"]["rep_call_plan"]
        self.visit_p = h.tier.map(plan).to_numpy() / WEEKS_PER_MONTH

        # Asset pools by (market, brand, channel); in-review assets were never used.
        d = docs[docs.status != "in_review"].reset_index(drop=True)
        self.docs = d
        themes = sorted(d.content_theme.unique())
        self.theme_idx = {t: i for i, t in enumerate(themes)}
        self.doc_theme = d.content_theme.map(self.theme_idx).to_numpy()
        self.doc_stage = d.journey_stage.map(lambda s: STAGE_INDEX.get(s, ANY_STAGE)).to_numpy()
        self.pools = {k: g.index.to_numpy() for k, g in d.groupby(["market", "product", "channel"])}
        self.group = list(zip(h.market, h.brand))
        self.gkey = pd.factorize(pd.Series(self.group))[0]
        self.gkey_label = dict(zip(self.gkey, self.group))
        self.access = self.theme_idx.get("access", -1)

        self.last_theme_week = np.full((self.n, len(themes)), -999)
        self.last_touch_week = -rng.integers(0, 8, self.n)
        self.ever_attended = np.zeros(self.n, bool)
        self.rows = {k: [] for k in ["call2_vod", "sent_email_vod", "agency_email",
                                      "agency_media", "event_attendee_vod", "hcp_stage_weekly"]}
        self.world = world

    # ---------------------------------------------------------------- helpers
    def _touch(self, w, idx, channel):
        """Pick an asset for each touched physician, decide who responds, update memory."""
        sel_all, doc_all, resp_all = [], [], []
        for g in np.unique(self.gkey[idx]):
            sel = idx[self.gkey[idx] == g]
            pool = self.pools.get((*self.gkey_label[g], channel))
            if pool is None or len(sel) == 0:
                continue
            docs = pool[self.rng.integers(len(pool), size=len(sel))]
            theme = self.doc_theme[docs]
            repeated = self.last_theme_week[sel, theme] >= w - 4
            p = self.beh.response_prob(sel, channel, self.stage[sel], self.doc_stage[docs], repeated)
            resp = self.rng.random(len(sel)) < p
            self.last_theme_week[sel, theme] = w
            self.last_touch_week[sel] = w
            on_seq = self.doc_stage[docs] == self.stage[sel]
            self.responded[sel[resp & on_seq]] = True   # only stage-appropriate content moves the journey
            self.access_landed[sel[resp & (theme == self.access)]] = True
            sel_all.append(sel), doc_all.append(docs), resp_all.append(resp)
        if not sel_all:
            return np.array([], int), np.array([], int), np.array([], bool)
        return np.concatenate(sel_all), np.concatenate(doc_all), np.concatenate(resp_all)

    def _days(self, k, hi=5):
        return pd.to_timedelta(self.rng.integers(0, hi, k), unit="D")

    # ---------------------------------------------------------------- channels
    def _rep_calls(self, w, date):
        rng, n = self.rng, self.n
        visit = self.eligible & self.has_rep & (rng.random(n) < self.visit_p)
        remote = visit & self.remote_ok & (rng.random(n) < 0.15)
        cancelled = visit & (rng.random(n) < 0.04)
        for channel, mask, ctype in [("rep_visit", visit & ~remote & ~cancelled, "face_to_face"),
                                     ("remote_call", visit & remote & ~cancelled, "remote")]:
            sel, docs, resp = self._touch(w, np.flatnonzero(mask), channel)
            step = np.where(resp, rng.choice(["send_material", "follow_up_call"], len(sel)), "none")
            ids = self.docs.document_id.to_numpy()[docs]
            self.rows["call2_vod"].append(pd.DataFrame({
                "account_id": self.h.id.to_numpy()[sel], "user_id": self.rep[sel], "call_date": date + self._days(len(sel)),
                "call_type": ctype, "status": "submitted", "product": self.h.brand.to_numpy()[sel],
                "key_message_ids": [f"{d}:KM1|{d}:KM2" for d in ids], "next_step": step}))
        c = np.flatnonzero(cancelled)
        self.rows["call2_vod"].append(pd.DataFrame({
            "account_id": self.h.id.to_numpy()[c], "user_id": self.rep[c], "call_date": date + self._days(len(c)),
            "call_type": "face_to_face", "status": "cancelled", "product": self.h.brand.to_numpy()[c], "next_step": "none"}))

    def _emails(self, w, date):
        rng, n = self.rng, self.n
        email_ok = self.eligible & self.email_active & (self.email_since <= np.datetime64(date))
        rep_mask = email_ok & self.has_rep & (rng.random(n) < REP_EMAIL_PER_MONTH / WEEKS_PER_MONTH)
        mkt_mask = email_ok & self.double_ok & (rng.random(n) < self.design["history_simulation"][
            "marketing_email_per_month_if_consent"] / WEEKS_PER_MONTH)
        for channel, mask in [("rep_email", rep_mask), ("marketing_email", mkt_mask)]:
            bounced = mask & (rng.random(n) < 0.02) if channel == "rep_email" else np.zeros(n, bool)
            sel, docs, opened = self._touch(w, np.flatnonzero(mask & ~bounced), channel)
            clicked = opened & (rng.random(len(sel)) < CLICK_GIVEN_OPEN)
            unsub = rng.random(len(sel)) < UNSUBSCRIBE_PER_EMAIL
            self.email_active[sel[unsub]] = False
            self.unsub_week[sel[unsub]] = w
            sent = date + self._days(len(sel)) + pd.to_timedelta(rng.integers(7, 18, len(sel)), unit="h")
            acc, doc_ids = self.h.id.to_numpy()[sel], self.docs.document_id.to_numpy()[docs]
            if channel == "marketing_email":
                self.rows["agency_email"].append(pd.DataFrame({
                    "campaign_id": [f"{m}-CMP{w + 1:03d}" for m in self.h.market.to_numpy()[sel]], "account_id": acc,
                    "market": self.h.market.to_numpy()[sel], "approved_document_id": doc_ids, "sent_datetime": sent,
                    "opened": opened, "clicked": clicked, "unsubscribed": unsub}))
                continue
            b = np.flatnonzero(bounced)
            self.rows["sent_email_vod"].append(pd.DataFrame({
                "account_id": np.concatenate([acc, self.h.id.to_numpy()[b]]),
                "user_id": np.concatenate([self.rep[sel], self.rep[b]]),
                "email_sent_date": np.concatenate([sent, date + self._days(len(b))]),
                "approved_document_id": np.concatenate([doc_ids, [None] * len(b)]),
                "status": ["sent"] * len(sel) + ["bounced"] * len(b), "_resp": np.concatenate([opened, np.zeros(len(b), bool)]),
                "_click": np.concatenate([clicked, np.zeros(len(b), bool)]),
                "_unsub": np.concatenate([unsub, np.zeros(len(b), bool)])}))

    def _media(self, w, date):
        rng, n = self.rng, self.n
        ok = self.eligible & self.digital_ok
        impressions = np.where(ok, rng.poisson(self.design["history_simulation"]["paid_media_impressions_per_month"]
                                               / WEEKS_PER_MONTH, n), 0)
        clicks = rng.binomial(impressions, self.beh.base[:, self.beh.ch["paid_media"]])
        visits = np.where(ok & (rng.random(n) < self.beh.base[:, self.beh.ch["portal"]] * 0.5),
                          1 + rng.poisson(0.5, n), 0)
        active = (impressions > 0) | (visits > 0)
        engaged = (clicks > 0) | (visits > 0)
        # paid media and portal engagement do not move the journey on their own
        self.last_touch_week[engaged] = w
        idx = np.flatnonzero(active)
        themes = np.array(sorted(self.theme_idx))
        viewed = np.where(visits[idx] > 0, themes[rng.integers(len(themes), size=len(idx))], None)
        self.rows["agency_media"].append(pd.DataFrame({
            "account_id": self.h.id.to_numpy()[idx], "market": self.h.market.to_numpy()[idx], "week": date,
            "impressions": impressions[idx], "clicks": clicks[idx], "portal_visits": visits[idx],
            "portal_content_viewed": viewed}))

    def _events(self, w, date):
        rng, n, h = self.rng, self.n, self.h
        invited_sets = []
        if w % 13 == 6:  # one webinar per quarter per market, invitation by email
            ok = self.eligible & self.email_active & (self.email_since <= np.datetime64(date))
            invited_sets.append(("webinar", ok, 1.0))
        for wk, etype, audience, share in EVENTS:
            if wk == w:
                who = (h.expert_status == "key_people").to_numpy() if audience == "experts" \
                    else h.specialty.isin(AUDIENCE[audience]).to_numpy()
                invited_sets.append((etype, self.eligible & who & (rng.random(n) < share), 0.8))
        for etype, mask, factor in invited_sets:
            idx = np.flatnonzero(mask)
            p = np.clip(self.beh.base[idx, self.beh.ch["webinar"]] * factor + (0.1 if etype != "webinar" else 0), 0, 0.9)
            attended = rng.random(len(idx)) < p
            registered = attended | (rng.random(len(idx)) < 0.12)
            self.responded[idx[attended]] = True
            self.ever_attended[idx[attended]] = True
            self.last_touch_week[idx] = w
            markets = h.market.to_numpy()[idx]
            self.rows["event_attendee_vod"].append(pd.DataFrame({
                "event_id": [f"{m}-{etype.upper()[:3]}-{w + 1:03d}" for m in markets], "account_id": h.id.to_numpy()[idx],
                "event_type": etype, "event_date": date + pd.Timedelta(days=3), "registered": registered,
                "attended": attended}))

    def _kam_calls(self, date):
        hcos = self.world["hcos"]
        units = hcos[hcos.hco_type.isin(["endoscopy_unit", "hospital"])]
        p = units.unit_tier.map({"A": 1.0, "B": 0.5, "C": 0.2}).to_numpy() / WEEKS_PER_MONTH
        u = units[self.rng.random(len(units)) < p]
        terr = self.world["bricks"].set_index("brick_id").territory_id
        kam = u.brick_id.map(terr).map(self.world["territories"].set_index("id").kam_user_id)
        product = np.where(u.hco_type == "endoscopy_unit", "Plenvu_Moviprep",
                           np.where(u.liver_unit_flag, "Xifaxan", "Movicol"))
        self.rows["call2_vod"].append(pd.DataFrame({
            "account_id": u.hco_id.to_numpy(), "user_id": kam.to_numpy(), "call_date": date + self._days(len(u)),
            "call_type": "face_to_face", "status": "submitted", "product": product,
            "next_step": self.rng.choice(["none", "send_material", "follow_up_call"], len(u), p=[0.5, 0.25, 0.25])}))

    # ---------------------------------------------------------------- main loop
    def run(self) -> dict:
        for w in range(self.n_weeks):
            date = self.start + pd.Timedelta(weeks=w)
            self.responded = np.zeros(self.n, bool)
            self.access_landed = np.zeros(self.n, bool)
            self._rep_calls(w, date)
            self._emails(w, date)
            self._media(w, date)
            self._events(w, date)
            self._kam_calls(date)
            self.stage = self.beh.move_stages(self.rng, self.stage, self.responded, self.access_landed,
                                              self.ever_attended, w - self.last_touch_week)
            self.rows["hcp_stage_weekly"].append(pd.DataFrame({"account_id": self.h.id.to_numpy(), "week": date,
                                                               "stage": self.stage}))
        return self._tables()

    def _tables(self) -> dict:
        from nba.synth.behaviour import STAGES
        out = {k: pd.concat(v, ignore_index=True) for k, v in self.rows.items()}
        calls = out["call2_vod"].sort_values(["call_date", "account_id"], kind="stable").reset_index(drop=True)
        calls.insert(0, "id", [f"CALL{i + 1:07d}" for i in range(len(calls))])
        out["call2_vod"] = calls
        se = out.pop("sent_email_vod").sort_values(["email_sent_date", "account_id"], kind="stable").reset_index(drop=True)
        se.insert(0, "id", [f"SE{i + 1:07d}" for i in range(len(se))])
        acts = []
        for kind, col, hours in [("open", "_resp", 3), ("click", "_click", 5), ("unsubscribe", "_unsub", 6)]:
            s = se[se[col]]
            acts.append(pd.DataFrame({"sent_email_id": s.id, "event_type": kind,
                                      "event_datetime": s.email_sent_date + pd.Timedelta(hours=hours)}))
        act = pd.concat(acts, ignore_index=True).sort_values(["event_datetime", "sent_email_id"], kind="stable")
        act.insert(0, "id", [f"EA{i + 1:07d}" for i in range(len(act))])
        out["email_activity_vod"] = act.reset_index(drop=True)
        out["sent_email_vod"] = se.drop(columns=["_resp", "_click", "_unsub"])
        ev = out["event_attendee_vod"]
        ev.insert(0, "id", [f"EVA{i + 1:07d}" for i in range(len(ev))])
        out["hcp_stage_weekly"]["stage"] = np.array(STAGES)[out["hcp_stage_weekly"]["stage"].to_numpy()]
        out["final_stage"] = pd.Series(self.stage, index=self.h.id)
        out["unsubscribed"] = self.h.id.to_numpy()[self.unsub_week >= 0]
        return out
