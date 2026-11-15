"""What a response is worth at each journey stage, learned from the engine's own history.

Two things a response can buy, estimated per stage from the last 52 weeks of the public tables (weekly journey
stages and every touch with whether the physician responded; the hidden behaviour clusters are never read):

1. Movement: how much more often a physician moves up a stage the week they respond than in a week without a
   response (the uplift, not the raw rate), separately for content that matches their journey stage and content
   that does not. The history is clear that only matched content moves physicians.
2. Protection: how often a physician who has not responded for `SILENT_WEEKS` slips back a stage, against one who
   responded recently. A response restarts that clock, so it is worth the difference over the protected weeks.

The optimiser multiplies the value of a stage move by (1) and adds the value of the current stage times (2),
instead of assuming every response moves a physician up a stage.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from nba import data, spec
from nba.features.touches import TOUCH_LOG

STAGES = ["curiosity", "consideration", "experience", "loyalty", "advocacy"]
SILENT_WEEKS = 8          # weeks without a response after which a physician counts as silent
_CACHE: dict = {}

ODDS = """
-- A week's stage is recorded after that week's touches, so a response and the move it causes share a week:
-- compare each week's stage with the week before. A response counts as matched when the content's journey stage
-- is the physician's stage.
with st as (
    select account_id, date_trunc('week', week)::date as wk, stage,
           list_position(['curiosity','consideration','experience','loyalty','advocacy'], stage) - 1 as s
    from hcp_stage_weekly where week >= $start),
prv as (select account_id, wk, s, lag(s) over (partition by account_id order by wk) as s_prev,
               lag(stage) over (partition by account_id order by wk) as stage_prev from st),
resp as (
    select t.account_id, date_trunc('week', t.ts)::date as wk, bool_or(t.responded) as responded,
           list(d.journey_stage) filter (where t.responded) as stages
    from touch_log t left join promomats_document d on d.document_id = t.document_id
    where t.ts >= $start - interval 70 day and t.channel <> 'kam_visit' group by all),
panel as (
    select p.account_id, p.wk, p.s, p.s_prev, coalesce(r.responded, false) as responded,
           coalesce(list_contains(r.stages, p.stage_prev), false) as matched,
           max(case when r.responded then p.wk end) over (partition by p.account_id order by p.wk
               rows between unbounded preceding and 1 preceding) as last_resp
    from prv p left join resp r using (account_id, wk)
    where p.s_prev is not null)
select s_prev as s,
       avg((s > s_prev)::int) filter (where responded and matched)                          as up_after_matched,
       avg((s > s_prev)::int) filter (where responded and not matched)                      as up_after_unmatched,
       avg((s > s_prev)::int) filter (where responded)                                      as up_after_response,
       avg((s > s_prev)::int) filter (where not responded)                                  as up_without,
       avg((s < s_prev)::int) filter (where not responded and (last_resp is null or wk - last_resp > $silent)) as slip_silent,
       avg((s < s_prev)::int) filter (where not responded and last_resp is not null and wk - last_resp <= $silent) as slip_recent,
       count(*) filter (where responded)                                                    as responses
from panel group by s_prev order by s_prev
"""


def stage_odds(data_dir: Path | None = None) -> pd.DataFrame:
    """Per stage: the uplift in moving up after a response, and the weekly slip rate when silent or recently
    responsive. Learned from the 52 weeks before the latest week in the data; cached until the data changes."""
    root = Path(data_dir) if data_dir else spec.data_dir()
    f = root / "hcp_stage_weekly.parquet"
    key = (str(root), os.path.getmtime(f) if f.exists() else 0)
    if key in _CACHE:
        return _CACHE[key]
    con = data.connect(data_dir)
    con.execute(TOUCH_LOG)
    last = con.execute("select max(week) from hcp_stage_weekly").fetchone()[0]
    start = pd.Timestamp(last) - pd.Timedelta(weeks=52)
    df = con.execute(ODDS, {"start": start.date(), "silent": SILENT_WEEKS * 7}).df()
    df["stage"] = df.s.map(dict(enumerate(STAGES)))
    df["move_uplift"] = (df.up_after_response - df.up_without).clip(lower=0).fillna(0)
    df["move_matched"] = (df.up_after_matched - df.up_without).clip(lower=0).fillna(0)
    df["move_unmatched"] = (df.up_after_unmatched - df.up_without).clip(lower=0).fillna(0)
    df["protection_per_week"] = (df.slip_silent - df.slip_recent).clip(lower=0).fillna(0)
    out = df.set_index("stage")[["move_uplift", "move_matched", "move_unmatched", "protection_per_week", "slip_silent",
                                 "slip_recent", "responses"]]
    out = out.reindex(STAGES).fillna(0)
    _CACHE.clear()
    _CACHE[key] = out
    return out


def response_value_factors(stage: pd.Series, matched: pd.Series | None = None,
                           data_dir: Path | None = None) -> tuple[np.ndarray, np.ndarray]:
    """For each physician's stage: the chance a response moves them up (using what the history shows for content
    that matches their stage, or not, when `matched` is given), and the extra chance of not slipping back over
    the weeks a response protects them."""
    o = stage_odds(data_dir)
    if matched is None:
        move = stage.map(o.move_uplift)
    else:
        move = pd.Series(np.where(matched.to_numpy(dtype=bool), stage.map(o.move_matched), stage.map(o.move_unmatched)),
                         index=stage.index)
    move = move.fillna(0).to_numpy(dtype=float)
    keep = (stage.map(o.protection_per_week).fillna(0) * SILENT_WEEKS).clip(upper=1).to_numpy(dtype=float)
    return move, keep
