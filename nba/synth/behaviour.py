"""How a simulated physician responds to a touch, and how their journey stage moves.

This is the 'hidden truth' of the simulation. It is used by the history generator (synth) and,
from step 4, by the feedback simulator. The engine itself never sees these probabilities; it has
to learn what works from the observed responses, exactly as it would with real data.
"""
from __future__ import annotations

import numpy as np

STAGES = ["curiosity", "consideration", "experience", "loyalty", "advocacy"]
STAGE_INDEX = {s: i for i, s in enumerate(STAGES)}
ANY_STAGE = -1


class Behaviour:
    def __init__(self, design: dict, clusters: np.ndarray, markets: np.ndarray, channels: list[str]):
        """clusters/markets: one entry per physician. channels: the channel order used for column indexes."""
        self.design = design
        self.channels = channels
        self.ch = {c: i for i, c in enumerate(channels)}
        cl = design["clusters"]
        adj = design["country_adjustment"]
        # base[i, c] = cluster response rate x country adjustment
        self.base = np.zeros((len(clusters), len(channels)))
        for name, cfg in cl.items():
            rows = clusters == name
            for c, j in self.ch.items():
                self.base[rows, j] = cfg["response_by_channel"].get(c, 0.0)
        for m, factors in adj.items():
            rows = markets == m
            for c, f in factors.items():
                if c in self.ch:
                    self.base[rows, self.ch[c]] *= f
        ce = design["content_effect"]
        self.on_seq, self.off_seq, self.repeat = ce["on_sequence"], ce["off_sequence"], ce["theme_repeat_within_30d"]
        sm = design["stage_model"]
        self.move_p = np.array([sm["move_probability_on_response"].get(s, 0.0) for s in STAGES])
        q = sm["regression_probability_per_quarter_without_touch"]
        self.regress_p_week = 1 - (1 - q) ** (1 / 13)
        self.stall_clusters = {n for n, c in cl.items() if c.get("stall_stage")}
        self.stall_stage = {n: STAGE_INDEX[c["stall_stage"]] for n, c in cl.items() if c.get("stall_stage")}
        self.clusters = clusters

    def response_prob(self, idx: np.ndarray, channel: str, stage: np.ndarray,
                      doc_stage: np.ndarray, repeated: np.ndarray) -> np.ndarray:
        """Chance each touched physician responds. idx: physician rows; stage: their current stage index;
        doc_stage: the asset's journey stage index (-1 = any); repeated: same theme within 30 days."""
        p = self.base[idx, self.ch[channel]].copy()
        seq = np.where(doc_stage == ANY_STAGE, 1.0, np.where(doc_stage == stage, self.on_seq, self.off_seq))
        p *= seq * np.where(repeated, self.repeat, 1.0)
        return np.clip(p, 0, 0.95)

    def move_stages(self, rng: np.random.Generator, stage: np.ndarray, responded: np.ndarray,
                    access_landed: np.ndarray, ever_attended: np.ndarray, weeks_since_touch: np.ndarray) -> np.ndarray:
        """Return the new stage index for every physician after one week. `responded` means a response
        to content that suits the physician's current stage, or attending an event."""
        new = stage.copy()
        up = responded & (rng.random(len(stage)) < self.move_p[stage])
        # The access-blocked cluster stays at its stall stage until an access message lands.
        for name, s in self.stall_stage.items():
            up &= ~((self.clusters == name) & (stage == s) & ~access_landed)
        # Advocacy needs loyalty plus an attended event.
        up &= ~((stage == STAGE_INDEX["loyalty"]) & ~ever_attended)
        up &= stage < len(STAGES) - 1
        new[up] += 1
        down = (weeks_since_touch >= 13) & (rng.random(len(stage)) < self.regress_p_week) & (new > 0) & ~up
        new[down] -= 1
        return new
