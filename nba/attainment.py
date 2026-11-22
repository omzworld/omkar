"""Planned against delivered contacts: did each doctor get the visits their call plan set?

Contacts are rep visits and remote calls. The target is the call plan each arm follows: in test territories the
engine's quarterly plan (`call_plan`, pro rata for the weeks run); in control territories today's call plan, the
visit frequency by tier that reps already work to (`history_simulation.rep_call_plan`). Reported by potential band
(the quarter-1 segmentation), with the distribution of contacts per doctor (0, 1, 2, 3-4, 5, 6+) and by rep.
Only active, promotable physicians count, as in the rest of the measurement.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from nba import data, measure, spec

BUCKETS = [(0, 0, "0"), (1, 1, "1"), (2, 2, "2"), (3, 4, "3-4"), (5, 5, "5"), (6, 10_000, "6+")]
BANDS = ["high", "medium", "low"]


def per_doctor(data_dir: Path | None = None) -> pd.DataFrame:
    """One row per physician: arm, potential band, rep, planned and delivered contacts over the pilot so far."""
    start, end, weeks = measure._window(data_dir)
    if weeks == 0:
        return pd.DataFrame()
    con = data.connect(data_dir)
    docs = con.execute("""
        select a.id as account_id, a.territory_id, tv.pilot_arm as arm, tv.rep_user_id as rep
        from account_vod a join territory_vod tv on tv.id = a.territory_id join hcp_master_opendata m on m.onekey_id = a.onekey_id
        where a.account_type = 'hcp' and a.status = 'active' and not m.no_promo_flag and a.hcp_role <> 'medical_only_contact'
          and tv.pilot_arm in ('test', 'control')""").df().set_index("account_id")
    q_end = min(end, start + pd.Timedelta(weeks=spec.assumptions()["planning"]["cycle_weeks"]))
    v = con.execute("""select c.account_id, count(*) as n, count(*) filter (where c.call_date < $q) as q1
                       from call2_vod c join user_vod u on u.id = c.user_id
                       where c.status = 'submitted' and u.role = 'rep' and c.call_date >= $s and c.call_date < $e group by 1""",
                    {"s": start.date(), "e": end.date(), "q": q_end.date()}).df().set_index("account_id")
    visits = v.n
    seg = data.read_table("hcp_segment", data_dir)
    seg = seg[seg.cycle == 1].set_index("account_id") if len(seg) else pd.DataFrame(columns=["potential_band", "current_tier"])
    feats_tier = seg.current_tier if "current_tier" in seg else pd.Series(dtype=object)
    docs["band"] = docs.index.map(seg.potential_band) if len(seg) else None
    docs["tier"] = docs.index.map(feats_tier)
    docs["delivered"] = docs.index.map(visits).fillna(0).astype(int)
    docs["delivered_q1"] = docs.index.map(v.q1).fillna(0).astype(int)        # contacts in the first quarter

    # Test target: the engine's plan, each cycle pro rata for the weeks of it that have run.
    cyc = spec.assumptions()["planning"]["cycle_weeks"]
    cp = data.read_table("call_plan", data_dir)
    target = pd.Series(0.0, index=docs.index)
    if len(cp):
        cp = cp[cp.channel.isin(["rep_visit", "remote_call"])]
        for c, g in cp.groupby("cycle"):
            share = min(max(weeks - (int(c) - 1) * cyc, 0), cyc) / cyc
            target = target.add(g.groupby("account_id").final_touches.sum().reindex(docs.index).fillna(0) * share, fill_value=0)
    # Control target: today's call plan, visits a month by tier, for the weeks run.
    per_month = spec.design()["history_simulation"]["rep_call_plan"]
    ctrl = docs.tier.map(per_month).fillna(0).astype(float) * weeks / 4.345
    docs["planned"] = np.where(docs.arm == "test", target.reindex(docs.index).fillna(0), ctrl).round(1)
    docs["met"] = docs.delivered >= np.floor(docs.planned + 0.5) - 0          # at least the rounded target
    docs["shortfall"] = (np.floor(docs.planned + 0.5) - docs.delivered).clip(lower=0)
    return docs.reset_index()


def report(data_dir: Path | None = None) -> dict:
    d = per_doctor(data_dir)
    if d.empty:
        return {"weeks": 0}
    _, _, weeks = measure._window(data_dir)
    d = d[d.planned > 0.5]                                     # doctors with at least one contact planned

    def bucket(n):
        return next(lbl for lo, hi, lbl in BUCKETS if lo <= n <= hi)
    d = d.assign(bucket=d.delivered_q1.map(bucket))             # contacts in a quarter, as in the CRM chart
    rows = []
    for (arm, band), g in d.groupby(["arm", "band"]):
        rows.append({"arm": arm, "band": band, "doctors": int(len(g)), "planned": round(float(g.planned.sum())),
                     "delivered": int(g.delivered.sum()),
                     "attainment_pct": round(100 * g.delivered.sum() / max(g.planned.sum(), 1), 0),
                     "met_pct": round(100 * g.met.mean(), 0), "below_target": int((~g.met).sum()),
                     "missed_contacts": int(g.shortfall.sum())})
    dist = (d.groupby(["arm", "band", "bucket"]).size().rename("doctors").reset_index())
    dist["pct"] = (100 * dist.doctors / dist.groupby(["arm", "band"]).doctors.transform("sum")).round(0)
    reps = []
    for (rep, arm), g in d.groupby(["rep", "arm"]):
        hi = g[g.band == "high"]
        reps.append({"rep": rep, "arm": arm, "doctors": int(len(g)), "planned": round(float(g.planned.sum())),
                     "delivered": int(g.delivered.sum()), "attainment_pct": round(100 * g.delivered.sum() / max(g.planned.sum(), 1), 0),
                     "met_pct": round(100 * g.met.mean(), 0), "high_potential_below_target": int((~hi.met).sum())})
    return {"weeks": weeks, "by_band": rows, "distribution": dist.to_dict("records"),
            "buckets": [b[2] for b in BUCKETS], "by_rep": sorted(reps, key=lambda r: (r["arm"], -r["high_potential_below_target"])),
            "definition": "Contacts are rep visits and remote calls. Target: the engine's quarterly plan in test territories; "
                          "today's call plan (visits a month by tier) in control. Met = at least the target, rounded. "
                          "The distribution counts contacts in the first quarter of the pilot."}
