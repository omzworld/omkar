// My territory this week: the rep's single page. One row per doctor joins segment, ladder position, concern, last
// contact, progress against the quarter's plan, this week's action and why, and the content to use.
import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { api, num, words } from "../api";
import { Badge, Button, Card, Message, Stat } from "../ui";
import { LADDER_LABEL } from "../ladder.js";

const FILTERS = [["actions", "This week's actions"], ["engine", "Changes from the engine"], ["behind", "Behind plan"],
  ["headroom", "Headroom"], ["profile", "Profile to update"], ["all", "Everyone"]];

export default function MyTerritory({ pilot, go }) {
  const done = pilot?.completed_weeks ?? 0;
  const [reps, setReps] = useState([]);
  const [user, setUser] = useState(null);
  const [week, setWeek] = useState(null);
  const [p, setP] = useState(null);
  const [err, setErr] = useState(null);
  const [filter, setFilter] = useState("actions");
  const [open, setOpen] = useState(null);
  useEffect(() => { api("/territory/reps").then((r) => { setReps(r); setUser((u) => u || (r.find((x) => x.rep === "DE-REP24") || r[0])?.rep); }); }, []);
  useEffect(() => {
    if (!user || !done) return;
    setErr(null);
    api(`/territory/${user}${week ? `?week=${week}` : ""}`).then((x) => { setP(x); if (!week) setWeek(x.week); }).catch((e) => setErr(e.message));
  }, [user, week, done]);

  const rows = useMemo(() => {
    if (!p) return [];
    const f = {
      actions: (r) => r.has_own_action, engine: (r) => r.actions.some((a) => a.kind === "moved in by the engine"),
      behind: (r) => r.behind, headroom: (r) => r.headroom, profile: (r) => r.profile_stale || r.profile_out_of_date, all: () => true,
    }[filter];
    return p.rows.filter(f);
  }, [p, filter]);

  if (!done) return (
    <div className="space-y-6"><Header />
      <Message>Run the pilot first (Feedback or Results screen): the page shows a real week of the plan.
        <span className="ml-2"><Button kind="secondary" onClick={() => go("results")}>Go to Results →</Button></span></Message>
    </div>);
  const s = p?.summary;

  return (
    <div className="space-y-6">
      <Header />
      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <label className="text-sm"><span className="text-[var(--ink-2)]">Rep</span>
            <select className="mt-1 block rounded-full border border-[var(--axis)] bg-[var(--raised)] px-3 py-2 text-sm" value={user || ""}
              onChange={(e) => { setUser(e.target.value); setOpen(null); }} aria-label="Rep">
              {reps.map((r) => <option key={r.rep} value={r.rep}>{r.rep} · {r.name}</option>)}
            </select></label>
          <label className="text-sm"><span className="text-[var(--ink-2)]">Week</span>
            <select className="mt-1 block rounded-full border border-[var(--axis)] bg-[var(--raised)] px-3 py-2 text-sm" value={week || ""}
              onChange={(e) => { setWeek(Number(e.target.value)); setOpen(null); }} aria-label="Week">
              {Array.from({ length: done }, (_, i) => <option key={i + 1} value={i + 1}>Week {i + 1}</option>)}
            </select></label>
          {p && <p className="pb-2 text-sm text-[var(--ink-2)]">{p.territory_name} ({p.territory}) · week of {p.date} · week {s.week_in_quarter} of {s.quarter_weeks} in the quarter</p>}
        </div>
      </Card>
      {err && <Message tone="bad">{err}</Message>}
      {p && (<>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6">
          <Stat label="Doctors" value={num(s.doctors)} note="in the territory" />
          <Stat label="My actions this week" value={num(s.actions_this_week)} note={`${num(s.changes_from_engine)} changed by the engine`} />
          <Stat label="Quarter plan so far" value={`${num(s.quarter_done)} of ${num(s.quarter_planned)}`} note="touches done before this week" />
          <Stat label="Behind plan" value={num(s.behind_plan)} note="doctors short of their pro rata plan" tone={s.behind_plan ? "bad" : "good"} />
          <Stat label="Headroom" value={num(s.headroom)} note="good potential, not yet regular users" />
          <Stat label="Profiles to update" value={num(s.stale_profiles + s.profiles_out_of_date)} note={`${num(s.stale_profiles)} over a year old, ${num(s.profiles_out_of_date)} out of step`} />
        </div>

        <Card title="My doctors" subtitle="Everything about each doctor on one line: click a row for the detail. Ladder: where engagement data puts them now; the profile is what was last entered in the CRM."
          actions={<div className="flex flex-wrap gap-1">{FILTERS.map(([k, l]) => (
            <button key={k} type="button" onClick={() => setFilter(k)}
              className={`btn-pill border px-3 py-1 text-xs ${filter === k ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--ink)]" : "border-[var(--axis)] text-[var(--ink-2)]"}`}>{l}</button>))}</div>}>
          <div className="overflow-auto rounded-xl border border-[var(--line)]">
            <table className="w-full min-w-[980px] text-sm">
              <thead className="sticky top-0 z-10 bg-[var(--raised)] text-left text-xs text-[var(--ink-2)]">
                <tr>{["Doctor", "Segment", "Ladder now", "Concern", "Last contact", "Quarter plan", "This week", "Content to use"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody>
                {rows.map((r) => (<>
                  <tr key={r.id} onClick={() => setOpen(open === r.id ? null : r.id)} className={`cursor-pointer border-t border-[var(--line)] align-top transition hover:bg-[var(--accent-soft)] ${open === r.id ? "bg-[var(--chip)]" : ""}`}>
                    <td className="px-3 py-2"><div className="font-medium">{r.name}</div><div className="text-xs text-[var(--muted)]">{words(r.specialty)} · {r.id}</div></td>
                    <td className="px-3 py-2"><div>{r.segment || "–"}</div><div className="text-xs text-[var(--muted)]">ZS potential: {r.zs_potential || "not recorded"}</div></td>
                    <td className="px-3 py-2">
                      <div className="font-medium">{LADDER_LABEL[r.ladder_now] || "–"}</div>
                      {r.profile_out_of_date && <Badge tone="bad">profile says {LADDER_LABEL[r.profile_ladder]}</Badge>}
                      {r.headroom && <div className="mt-1"><Badge tone="good">headroom</Badge></div>}
                    </td>
                    <td className="px-3 py-2"><div>{r.concern ? words(r.concern) : <span className="text-[var(--muted)]">not recorded</span>}</div>
                      <div className="text-xs text-[var(--muted)]">{r.barrier && r.barrier !== "none" ? `barrier: ${words(r.barrier)}` : r.barrier === "none" ? "no barrier" : "barrier not recorded"}</div>
                      {r.profile_stale && <div className="text-xs text-[var(--warn)]">profile {Math.round(r.profile_age_days / 30)} months old</div>}</td>
                    <td className="px-3 py-2 tabular"><div>{r.days_since_contact == null ? "–" : `${r.days_since_contact} days ago`}</div><div className="text-xs text-[var(--muted)]">{r.last_channel || ""}</div></td>
                    <td className="px-3 py-2"><Progress p={r.progress} behind={r.behind} /></td>
                    <td className="px-3 py-2">{r.actions.length ? r.actions.map((a, i) => <ActionChip key={i} a={a} />) : <span className="text-xs text-[var(--muted)]">nothing planned</span>}</td>
                    <td className="px-3 py-2"><div>{r.lead_theme ? words(r.lead_theme) : "–"}</div>
                      {r.support_theme && <div className="text-xs text-[var(--accent-2)]">+ {words(r.support_theme)}</div>}</td>
                  </tr>
                  {open === r.id && <tr key={r.id + "-d"}><td colSpan={8} className="border-t border-[var(--line)] bg-black/20 px-4 py-3"><Detail r={r} go={go} /></td></tr>}
                </>))}
                {rows.length === 0 && <tr><td colSpan={8} className="px-3 py-6 text-center text-sm text-[var(--muted)]">No doctors match this filter this week.</td></tr>}
              </tbody>
            </table>
          </div>
        </Card>
        {p.talk_track && (
          <Card title="Monday talk track" subtitle="The same week, written as the rep reads it.">
            <div className="whitespace-pre-line text-sm leading-relaxed text-[var(--ink-2)]">{p.talk_track}</div>
          </Card>
        )}
      </>)}
    </div>
  );
}

function Header() {
  return (
    <header>
      <div className="kicker mb-2">For the rep</div>
      <h1 className="text-2xl font-semibold">My territory this week</h1>
      <p className="mt-1 max-w-3xl text-[var(--ink-2)]">
        One page instead of several dashboards: for every doctor, their segment, where they are on the adoption ladder,
        what they care about, when they were last seen, how the quarter's plan is going, what to do this week and why,
        and which material to use.
      </p>
    </header>
  );
}

function Progress({ p, behind }) {
  const items = Object.entries(p || {});
  if (!items.length) return <span className="text-xs text-[var(--muted)]">no plan</span>;
  return (
    <div className="space-y-0.5">
      {items.map(([ch, v]) => (
        <div key={ch} className="flex items-center gap-2 text-xs">
          <span className="w-24 text-[var(--ink-2)]">{ch}</span>
          <span className="flex gap-0.5">{Array.from({ length: v.planned }, (_, i) => (
            <span key={i} className={`h-2 w-2 rounded-sm ${i < v.done ? "bg-[var(--accent)]" : "bg-[var(--chip)] ring-1 ring-[var(--axis)]"}`} />))}</span>
        </div>
      ))}
      {behind && <Badge tone="bad">behind</Badge>}
    </div>
  );
}

function ActionChip({ a }) {
  const tone = { "moved in by the engine": "good", planned: "neutral", "given to another doctor": "accent", blocked: "bad" }[a.kind] || "neutral";
  return (
    <div className="mb-1">
      <Badge tone={tone}>{a.kind === "moved in by the engine" ? "engine" : a.kind}</Badge>{" "}
      <span className="text-xs">{a.channel}{a.theme ? `, ${words(a.theme)}` : ""}</span>
      {a.rep_decision && <span className={`ml-1 text-xs ${a.rep_decision === "accepted" ? "text-[var(--good-ink)]" : "text-[var(--bad)]"}`}>({a.rep_decision === "dismissed" ? "declined" : a.rep_decision})</span>}
    </div>
  );
}

function Detail({ r, go }) {
  return (
    <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className="grid gap-4 text-sm md:grid-cols-3">
      <div>
        <div className="kicker mb-1 text-[11px]">Why this week</div>
        {r.actions.length ? r.actions.map((a, i) => <p key={i} className="mb-1"><span className="font-medium">{a.channel}:</span> <span className="text-[var(--ink-2)]">{a.why}</span></p>)
          : <p className="text-[var(--muted)]">Nothing planned for this doctor this week.</p>}
      </div>
      <div>
        <div className="kicker mb-1 text-[11px]">Profile</div>
        <p className="text-[var(--ink-2)]">Belief: {r.belief ? words(r.belief) : "not recorded"} · Preference: {r.preference ? words(r.preference) : "not recorded"}</p>
        <p className="text-[var(--ink-2)]">Competitor: {r.competitor || "not recorded"} · Sentiment: {r.sentiment || "not recorded"} · Influence: {r.influence || "–"}</p>
        <p className="mt-1 text-xs text-[var(--muted)]">From {r.profile_source === "survey" ? "a survey agency" : "the rep"}, last confirmed {r.profile_age_days == null ? "never" : `${r.profile_age_days} days ago`}.
          {(r.profile_stale || r.profile_out_of_date) && " Worth confirming at the next visit."}</p>
      </div>
      <div>
        <div className="kicker mb-1 text-[11px]">Content</div>
        <p className="text-[var(--ink-2)]">Lead with: <span className="text-[var(--ink)]">{r.lead_theme ? words(r.lead_theme) : "–"}</span> (matched to their stage, which is what moves doctors).</p>
        {r.support_theme && <p className="mt-1 text-[var(--ink-2)]">For their concern: <span className="text-[var(--accent-2)]">{words(r.support_theme)}</span>{r.support_material ? `: ${r.support_material}` : " (no approved material yet)"}</p>}
        <div className="mt-2"><Button kind="secondary" onClick={() => go("stories")}>See this doctor's journey →</Button></div>
      </div>
    </motion.div>
  );
}
