"""Touch history, events, journey stage and theme history, as DuckDB SQL.

Every query looks only at what happened before the run date (`as_of`), so a feature never sees the future.
Each function returns a DataFrame keyed by account_id (or hcp_id + theme for the theme history).
"""
from __future__ import annotations

import duckdb
import pandas as pd

# One row per touch on any channel, with whether the physician responded.
TOUCH_LOG = """
create or replace temp view touch_log as
with t as (
    select c.account_id, c.call_date::timestamp as ts,
           case when c.call_type = 'remote' then 'remote_call' when u.role = 'kam' then 'kam_visit'
                else 'rep_visit' end as channel,
           nullif(split_part(c.key_message_ids, ':', 1), '') as document_id,
           c.next_step <> 'none' as responded, false as clicked, false as unsubscribed,
           false as registered, c.next_step, null as event_type
    from call2_vod c join user_vod u on u.id = c.user_id
    where c.status = 'submitted'
    union all
    select s.account_id, s.email_sent_date, 'rep_email', s.approved_document_id,
           coalesce(a.opened, false), coalesce(a.clicked, false), coalesce(a.unsub, false), false, null, null
    from sent_email_vod s
    left join (select sent_email_id, bool_or(event_type = 'open') as opened, bool_or(event_type = 'click') as clicked,
                      bool_or(event_type = 'unsubscribe') as unsub
               from email_activity_vod group by 1) a on a.sent_email_id = s.id
    where s.status = 'sent'
    union all
    select account_id, sent_datetime, 'marketing_email', approved_document_id, opened, clicked, unsubscribed,
           false, null, null
    from agency_email
    union all
    select account_id, event_date::timestamp, case when event_type = 'webinar' then 'webinar' else 'event' end,
           null, attended, false, false, registered, null, event_type
    from event_attendee_vod
)
select t.*, d.content_theme as theme
from t left join promomats_document d on d.document_id = t.document_id
"""

TOUCH_FEATURES = """
with t as (select * from touch_log where ts < $as_of and channel <> 'kam_visit'),
lastresp as (
    select account_id, max(ts) filter (where responded) as last_resp_ts,
           max(ts) filter (where responded and channel in ('rep_email', 'marketing_email')) as last_email_resp_ts,
           arg_max(theme, ts) as last_theme
    from t group by 1
)
select t.account_id,
    date_diff('day', max(t.ts), $as_of)                                              as days_since_last_touch,
    arg_max(t.channel, t.ts)                                                         as last_touch_channel,
    arg_max(t.theme, t.ts)                                                           as last_touch_theme,
    arg_max(t.responded, t.ts)                                                       as last_touch_responded,
    count(*) filter (where t.ts >= $as_of - interval 30 day)                         as touches_30d,
    count(*) filter (where t.ts >= date_trunc('month', $as_of::timestamp))           as touches_month,
    count(*) filter (where t.ts > coalesce(l.last_resp_ts, '1900-01-01'))            as touches_ignored_consecutive,
    date_diff('day', max(t.ts) filter (where t.channel = 'rep_visit'), $as_of)      as days_since_rep_visit,
    count(*) filter (where t.channel = 'rep_visit' and t.ts >= $as_of - interval 90 day) as rep_visits_90d,
    date_diff('day', max(t.ts) filter (where t.channel = 'rep_visit'), $as_of)      as rep_visit_completed_days_ago,
    arg_max(t.next_step, t.ts) filter (where t.channel = 'rep_visit')               as rep_visit_next_step,
    date_diff('day', max(t.ts) filter (where t.channel in ('rep_email', 'marketing_email')), $as_of)
                                                                                     as days_since_last_email,
    count(*) filter (where t.channel in ('rep_email', 'marketing_email') and t.ts >= $as_of - interval 30 day)
                                                                                     as email_sent_30d,
    count(*) filter (where t.channel in ('rep_email', 'marketing_email') and t.responded
                     and t.ts >= $as_of - interval 30 day)                           as email_opens_30d,
    count(*) filter (where t.channel in ('rep_email', 'marketing_email') and t.clicked
                     and t.ts >= $as_of - interval 30 day)                           as email_clicks_30d,
    count(*) filter (where t.channel in ('rep_email', 'marketing_email')
                     and t.ts > coalesce(l.last_email_resp_ts, '1900-01-01'))       as emails_ignored_consecutive,
    coalesce(bool_or(t.channel in ('rep_email', 'marketing_email') and t.ts >= $as_of - interval 14 day), false)
                                                                                     as email_sent_14d,
    coalesce(bool_or(t.channel in ('rep_email', 'marketing_email') and t.responded
                     and t.ts >= $as_of - interval 14 day), false)                   as email_opened_14d,
    coalesce(bool_or(t.unsubscribed and t.ts >= $as_of - interval 30 day), false)    as unsubscribe_30d,
    count(*) filter (where t.channel = 'webinar' and t.ts >= $as_of - interval 30 day) as webinar_invites_30d,
    coalesce(bool_or(t.channel = 'webinar' and t.registered and t.ts >= $as_of - interval 30 day), false)
                                                                                     as webinar_registered_30d,
    coalesce(bool_or(t.channel = 'webinar' and t.responded and t.ts >= $as_of - interval 30 day), false)
                                                                                     as webinar_attended_30d,
    date_diff('day', max(t.ts) filter (where t.channel = 'webinar' and t.responded), $as_of) as days_since_webinar,
    count(*) filter (where t.ts >= $as_of - interval 7 day and t.theme = l.last_theme) as same_theme_touches_7d,
    count(*) filter (where t.ts >= $as_of - interval 28 day)
      - count(*) filter (where t.ts >= $as_of - interval 56 day and t.ts < $as_of - interval 28 day) as touches_delta_4w,
    (count(*) filter (where t.responded and t.ts >= $as_of - interval 28 day)
      + count(*) filter (where t.clicked and t.ts >= $as_of - interval 28 day))
      - (count(*) filter (where t.responded and t.ts >= $as_of - interval 56 day and t.ts < $as_of - interval 28 day)
      + count(*) filter (where t.clicked and t.ts >= $as_of - interval 56 day and t.ts < $as_of - interval 28 day))
                                                                                     as engagement_delta_4w,
    count(*) filter (where t.channel in ('rep_email', 'marketing_email'))            as emails_total,
    count(*) filter (where t.channel in ('rep_email', 'marketing_email') and t.responded) as email_responses_total,
    count(*) filter (where t.channel = 'rep_visit')                                  as visits_total,
    count(*) filter (where t.channel = 'rep_visit' and t.responded)                  as visit_responses_total
from t join lastresp l using (account_id)
group by t.account_id
"""

KAM = """
select account_id, date_diff('day', max(ts), $as_of) as days_since_kam_visit
from touch_log where channel = 'kam_visit' and ts < $as_of group by 1
"""

MEDIA = """
select account_id,
    sum(portal_visits) filter (where week >= $as_of - interval 30 day)               as portal_visits_30d,
    arg_max(portal_content_viewed, week) filter (where week >= $as_of - interval 30 day
                                                 and portal_content_viewed is not null) as portal_content_viewed,
    sum(impressions) filter (where week >= $as_of - interval 30 day)                 as media_impressions_30d
from agency_media where week < $as_of group by 1
"""

EVENTS = """
with past as (
    select account_id, arg_max(event_type, event_date) as event_type,
           date_diff('day', max(event_date), $as_of) as event_attended_days_ago
    from event_attendee_vod where attended and event_date < $as_of group by 1
),
upcoming as (
    select account_id, arg_min(event_type, event_date) as upcoming_type,
           date_diff('day', $as_of, min(event_date)) as event_upcoming_days,
           arg_min(registered, event_date) as event_registered
    from event_attendee_vod where event_date >= $as_of group by 1
)
select coalesce(p.account_id, u.account_id) as account_id, coalesce(p.event_type, u.upcoming_type) as event_type,
       u.event_upcoming_days, coalesce(u.event_registered, false) as event_registered, p.event_attended_days_ago
from past p full join upcoming u using (account_id)
"""

STAGES = """
with s as (
    select account_id, week, stage, lag(stage) over (partition by account_id order by week) as before
    from hcp_stage_weekly where week < $as_of
),
summary as (
    select account_id, arg_max(stage, week) as stage, min(week) as first_week,
           max(week) filter (where before is not null and stage <> before) as changed_week,
           arg_max(before, week) filter (where before is not null and stage <> before) as prev_stage
    from s group by 1
),
ranked as (select *, list_position(['curiosity','consideration','experience','loyalty','advocacy'], stage) as i,
                     list_position(['curiosity','consideration','experience','loyalty','advocacy'], prev_stage) as pi
           from summary)
select account_id, stage, prev_stage,
       date_diff('day', coalesce(changed_week, first_week), $as_of) as days_in_stage,
       coalesce(pi > i and date_diff('day', changed_week, $as_of) <= 28, false) as stage_regressed,
       ever_attended
from ranked
left join (select account_id, true as ever_attended from event_attendee_vod
           where attended and event_date < $as_of group by 1) e using (account_id)
"""

# Stage at the end of the last complete quarter (Xifaxan panel proxy).
STAGE_LAST_QUARTER = """
select account_id, arg_max(stage, week) as stage_last_qtr
from hcp_stage_weekly where week < date_trunc('quarter', $as_of::timestamp) group by 1
"""

THEMES = """
with t as (
    select account_id, theme, ts, responded,
           max(case when responded then ts end) over (partition by account_id, theme) as last_resp
    from touch_log where ts < $as_of and theme is not null
)
select account_id as hcp_id, theme, date_diff('day', max(ts), $as_of) as days_ago,
       count(*) filter (where ts > coalesce(last_resp, '1900-01-01')) as ignored_count,
       count(*) as received_count
from t group by 1, 2
"""


def build(con: duckdb.DuckDBPyConnection, as_of: pd.Timestamp) -> dict[str, pd.DataFrame]:
    con.execute(TOUCH_LOG)
    p = {"as_of": as_of.date()}
    return {name: con.execute(sql, p).df() for name, sql in
            [("touches", TOUCH_FEATURES), ("kam", KAM), ("media", MEDIA), ("events", EVENTS),
             ("stages", STAGES), ("stage_last_qtr", STAGE_LAST_QUARTER), ("themes", THEMES)]}
