// Doctor and rep view: the pilot told through one doctor and one rep, each next to a control counterpart chosen by
// a fixed rule (not hand-picked), with the whole comparable group shown so one pair never stands alone.
import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { api, num, words } from "../api";
import { Badge, Button, Card, Message } from "../ui";
import { ladderOf } from "../ladder.js";

const STAGES = ["curiosity", "consideration", "experience", "loyalty", "advocacy"];
const ROWS = ["visit", "remote call", "rep email", "marketing email", "webinar"];
const ARM = { test: ["Test · engine", "accent"], control: ["Control · today's plan", "neutral"] };

export default function Stories({ pilot, go }) {
  const [tab, setTab] = useState("doctor");
  const done = pilot?.completed_weeks ?? 0;
  return (
    <div className="space-y-6">
      <header>
        <div className="kicker mb-2">One doctor, one rep</div>
        <h1 className="text-2xl font-semibold">Doctor and rep view</h1>
        <p className="mt-1 max-w-3xl text-[var(--ink-2)]">
          The pilot through the eyes of one doctor and one rep, each next to a control counterpart picked by a fixed rule,
          and the whole comparable group alongside, so the story is never just one well-chosen pair.
        </p>
      </header>
      {done === 0 ? (
        <Message>Run the pilot first (Feedback or Results screen): the stories are built from what happened week by week.
          <span className="ml-2"><Button kind="secondary" onClick={() => go("results")}>Go to Results →</Button></span></Message>
      ) : (<>
        <div className="flex rounded-full border border-[var(--axis)] p-0.5 text-sm w-fit">
          {[["doctor", "A doctor's journey"], ["rep", "A rep's weeks"]].map(([k, l]) => (
            <button key={k} type="button" onClick={() => setTab(k)}
              className={`btn-pill px-4 py-1.5 transition ${tab === k ? "bg-[var(--accent)] text-white" : "text-[var(--ink-2)] hover:text-[var(--ink)]"}`}>{l}</button>
          ))}
        </div>
        <AnimatePresence mode="wait">
          <motion.div key={tab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }} className="space-y-6">
            {tab === "doctor" ? <DoctorTab done={done} /> : <RepTab done={done} />}
          </motion.div>
        </AnimatePresence>
      </>)}
    </div>
  );
}

// ------------------------------------------------------------------------------------------- doctor

function DoctorTab({ done }) {
  const [list, setList] = useState([]);
  const [id, setId] = useState(null);
  const [typed, setTyped] = useState("");
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const [who, setWho] = useState("doctor");
  useEffect(() => {
    api("/story/doctors").then((l) => { setList(l); setId((cur) => cur || (l.find((x) => x.id === "DE-H01143") || l[0])?.id); });
  }, [done]);
  useEffect(() => {
    if (!id) return;
    setD(null); setErr(null); setWho("doctor");
    api(`/story/doctor/${id}`).then(setD).catch((e) => setErr(e.message));
  }, [id, done]);

  return (<>
    <Card title="Pick a doctor" subtitle="Test doctors who moved forward after the engine moved a touch to them, or type any doctor's id.">
      <div className="flex flex-wrap items-center gap-2">
        {list.slice(0, 8).map((x) => (
          <button key={x.id} type="button" onClick={() => setId(x.id)}
            className={`btn-pill border px-3 py-1.5 text-sm ${id === x.id ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--axis)] text-[var(--ink-2)] hover:text-[var(--ink)]"}`}>
            {x.name} <span className="text-xs text-[var(--muted)]">+{x.stages_moved} stages</span>
          </button>
        ))}
        <form onSubmit={(e) => { e.preventDefault(); if (typed.trim()) setId(typed.trim().toUpperCase()); }} className="flex gap-2">
          <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="e.g. DE-H00017"
            className="w-36 rounded-full border border-[var(--axis)] bg-transparent px-3 py-1.5 text-sm outline-none focus:border-[var(--accent)]" aria-label="Doctor id" />
          <Button kind="secondary" type="submit">Show</Button>
        </form>
      </div>
    </Card>
    {err && <Message tone="bad">{err}</Message>}
    {!d ? (!err && <p className="text-sm text-[var(--muted)]">Building the journey…</p>) : (<>
      <div className="grid gap-6 xl:grid-cols-2">
        <JourneyCard p={d.doctor} />
        {d.comparison ? <JourneyCard p={d.comparison} rule={d.comparison.rule} /> : <Card><p className="text-sm text-[var(--muted)]">No comparable doctor in the other arm.</p></Card>}
      </div>
      <PeerCard peers={d.peers} />
      <Card title="What happened, and why" subtitle="Every touch in the pilot, newest last. Green ring: the content matched the doctor's stage. Filled: they responded."
        actions={d.comparison && (
          <div className="flex rounded-full border border-[var(--axis)] p-0.5 text-xs">
            {[["doctor", d.doctor.name], ["comparison", d.comparison.name]].map(([k, l]) => (
              <button key={k} type="button" onClick={() => setWho(k)} className={`btn-pill px-3 py-1 ${who === k ? "bg-[var(--chip)] text-[var(--ink)]" : "text-[var(--ink-2)]"}`}>{l}</button>
            ))}
          </div>)}>
        <EventList p={who === "doctor" ? d.doctor : d.comparison} />
      </Card>
    </>)}
  </>);
}

function JourneyCard({ p, rule }) {
  const [label, tone] = ARM[p.arm] || [p.arm, "neutral"];
  const color = p.arm === "test" ? "var(--accent)" : "var(--series-2)";
  return (
    <Card title={p.name} subtitle={`${words(p.specialty)} · ${p.market} · ${p.segment_q1 || "no segment"} · rep ${p.rep || "–"}`}
      actions={<Badge tone={tone}>{label}</Badge>}>
      <div className="grid grid-cols-4 gap-2">
        <Kpi label="Touches in the pilot" value={num(p.touches)} />
        <Kpi label="Matched to their stage" value={p.matched_pct == null ? "–" : `${num(p.matched_pct)}%`} tone={p.matched_pct >= 50 ? "good" : null} />
        <Kpi label="Responses" value={num(p.responses)} />
        <Kpi label="Journey" value={p.stages_moved > 0 ? `+${p.stages_moved}` : `${p.stages_moved ?? 0}`} note={`${ladderOf(p.stage_start)} → ${ladderOf(p.stage_end)}`} tone={p.stages_moved > 0 ? "good" : null} />
      </div>
      <JourneyChart p={p} color={color} />
      {rule && <p className="mt-2 text-xs text-[var(--muted)]">Compared with {rule}.</p>}
    </Card>
  );
}

function Kpi({ label, value, note, tone }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-black/20 p-2.5">
      <div className="text-[11px] leading-tight text-[var(--ink-2)]">{label}</div>
      <div className={`display tabular mt-1 text-xl font-bold ${tone === "good" ? "text-[var(--good-ink)]" : ""}`}>{value}</div>
      {note && <div className="text-[11px] text-[var(--muted)]">{note}</div>}
    </div>
  );
}

// Stage over time as a step line; each touch as a mark on its channel's row. Green ring = matched content;
// filled = responded. Week 0 is the pilot start.
function JourneyChart({ p, color }) {
  const W = 620, L = 104, R = 12, T = 12, SH = 110, RH = 15, H = T + SH + 18 + ROWS.length * RH + 16;
  const w0 = -8, w1 = 26;
  const x = (w) => L + ((w - w0) * (W - L - R)) / (w1 - w0);
  const y = (s) => T + SH - (STAGES.indexOf(s) * SH) / (STAGES.length - 1);
  const pts = p.stages.filter((s) => s.week >= w0);
  const path = pts.map((s, i) => `${i ? "L" : "M"} ${x(s.week)} ${y(s.stage)}${i < pts.length - 1 ? ` H ${x(pts[i + 1].week)}` : ""}`).join(" ");
  const rowY = (label) => T + SH + 18 + ROWS.indexOf(label) * RH + RH / 2;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-4 w-full" role="img" aria-label={`Journey of ${p.name}`}>
      {STAGES.map((s) => (
        <g key={s}><line x1={L} x2={W - R} y1={y(s)} y2={y(s)} stroke="var(--line)" /><text x={L - 6} y={y(s) + 4} textAnchor="end" fontSize="10.5" fill="var(--muted)">{ladderOf(s)}</text></g>
      ))}
      <line x1={x(0.5)} x2={x(0.5)} y1={T - 4} y2={H - 14} stroke="var(--axis)" strokeDasharray="3 4" />
      <text x={x(0.5) + 4} y={T + 4} fontSize="10" fill="var(--muted)">pilot starts</text>
      <motion.path d={path} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round"
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.2 }} style={{ filter: `drop-shadow(0 0 5px ${color})` }} />
      {ROWS.map((r) => <text key={r} x={L - 6} y={rowY(r) + 3.5} textAnchor="end" fontSize="10" fill="var(--muted)">{r}</text>)}
      {p.touches_list.filter((t) => t.week >= w0).map((t, i) => {
        const cx = x(t.week - 0.5 + ((new Date(t.date).getDay() + 6) % 7) / 7), cy = rowY(t.label);
        return (
          <g key={i}>
            <title>{`${t.date}: ${t.label}${t.theme ? `, ${words(t.theme)}` : ""}${t.content_stage ? ` (${t.content_stage} content)` : ""}; doctor at ${t.stage}; ${t.matched ? "matched" : "not matched"}; ${t.responded ? "responded" : "no response"}${t.origin ? ` · ${t.origin}` : ""}${t.why ? ` · ${t.why}` : ""}`}</title>
            <circle cx={cx} cy={cy} r="4.6" fill={t.responded ? (t.matched ? "var(--good)" : "var(--ink-2)") : "transparent"}
              stroke={t.matched ? "var(--good)" : "var(--axis)"} strokeWidth="1.6" />
            {t.origin === "moved in" && <circle cx={cx} cy={cy} r="7.5" fill="none" stroke="var(--accent-2)" strokeWidth="1" />}
          </g>
        );
      })}
      <text x={L} y={H - 2} fontSize="10" fill="var(--muted)">8 weeks before the pilot</text>
      <text x={W - R} y={H - 2} textAnchor="end" fontSize="10" fill="var(--muted)">week 26</text>
    </svg>
  );
}

function PeerCard({ peers }) {
  const t = peers.by_arm.test, c = peers.by_arm.control;
  if (!t || !c) return null;
  const rows = [["Moved up at least one stage", t.moved_up_pct, c.moved_up_pct, "%"], ["Touches each, on average", t.avg_touches, c.avg_touches, ""],
    ["Touches matched to their stage", t.matched_pct, c.matched_pct, "%"]];
  return (
    <Card title="Not just one pair: every comparable doctor" subtitle={`Doctors with the ${peers.rule}: ${t.doctors} in test territories, ${c.doctors} in control.`}>
      <div className="space-y-3">
        {rows.map(([label, a, b, unit], i) => {
          const max = Math.max(a || 0, b || 0, 1);
          return (
            <div key={label} className="grid grid-cols-[minmax(10rem,14rem)_1fr] items-center gap-3 text-sm">
              <span className="text-[var(--ink-2)]">{label}</span>
              <div className="space-y-1">
                {[[a, "var(--accent)", "test"], [b, "var(--series-2)", "control"]].map(([v, col, nm], j) => (
                  <div key={nm} className="flex items-center gap-2">
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--chip)]">
                      <motion.div className="h-full rounded-full" style={{ background: col }} initial={{ width: 0 }} animate={{ width: `${(100 * (v || 0)) / max}%` }} transition={{ delay: 0.1 * (i + j), duration: 0.7 }} />
                    </div>
                    <span className="tabular w-24 text-right text-xs">{v == null ? "–" : `${num(v, unit ? 0 : 1)}${unit}`} {nm}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function EventList({ p }) {
  const items = useMemo(() => {
    const t = p.touches_list.filter((x) => x.week >= 1).map((x) => ({ ...x, kind: "touch" }));
    const a = (p.moved_away || []).map((x) => ({ ...x, kind: "away" }));
    return [...t, ...a].sort((u, v) => u.week - v.week || (u.kind === "away") - (v.kind === "away"));
  }, [p]);
  const stageChanges = useMemo(() => {
    const out = {};
    p.stages.forEach((s, i) => { if (i && s.stage !== p.stages[i - 1].stage && s.week >= 1) out[s.week] = s.stage; });
    return out;
  }, [p]);
  let lastWeek = 0;
  return (
    <div className="max-h-[30rem] space-y-1.5 overflow-auto pr-1">
      {items.map((e, i) => {
        const shows = [];
        for (let w = lastWeek + 1; w <= e.week; w++) if (stageChanges[w]) shows.push(w);
        lastWeek = Math.max(lastWeek, e.week);
        return (
          <div key={i}>
            {shows.map((w) => (
              <div key={`s${w}`} className="my-2 flex items-center gap-2 text-xs font-semibold text-[var(--good-ink)]">
                <span className="h-px flex-1 bg-[var(--good)]/40" />Moved to {stageChanges[w]} (week {w})<span className="h-px flex-1 bg-[var(--good)]/40" />
              </div>
            ))}
            {e.kind === "away" ? (
              <div className="rounded-xl border border-dashed border-[var(--axis)] px-3 py-2 text-sm text-[var(--ink-2)]">
                <span className="tabular mr-2 text-xs text-[var(--muted)]">{e.date}</span>A planned {e.channel} went to another doctor: {e.why}
              </div>
            ) : (
              <div className="flex flex-wrap items-start gap-x-3 gap-y-1 rounded-xl border border-[var(--line)] bg-black/20 px-3 py-2 text-sm">
                <span className="tabular w-24 text-xs text-[var(--muted)]">{e.date}</span>
                <span className="w-28 font-medium">{e.label}</span>
                <span className="w-36 text-[var(--ink-2)]">{e.theme ? words(e.theme) : "no content"}</span>
                <span className="flex gap-1">
                  <Badge tone={e.matched ? "good" : "neutral"}>{e.matched ? "matched" : e.content_stage ? `${e.content_stage} content` : "–"}</Badge>
                  {e.responded && <Badge tone="good">responded</Badge>}
                  {e.origin && <Badge tone={e.origin === "moved in" ? "accent" : "neutral"}>{e.origin}</Badge>}
                </span>
                {e.why && <span className="basis-full pl-[7.75rem] text-xs text-[var(--muted)]">{e.why}</span>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ------------------------------------------------------------------------------------------- rep

function RepTab({ done }) {
  const [list, setList] = useState([]);
  const [user, setUser] = useState(null);
  const [week, setWeek] = useState(null);
  const [r, setR] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { api("/story/reps").then((l) => { setList(l); setUser((u) => u || (l.find((x) => x.rep === "DE-REP24") || l[0])?.rep); }); }, [done]);
  useEffect(() => {
    if (!user) return;
    setErr(null);
    api(`/story/rep/${user}${week ? `?week=${week}` : ""}`).then((x) => { setR(x); if (!week && x.detail) setWeek(x.detail.week); }).catch((e) => setErr(e.message));
  }, [user, week, done]);
  const pick = (u) => { setUser(u); setWeek(null); setR(null); };

  return (<>
    <Card title="Pick a rep" subtitle="Test reps who acted on the most changes from the engine.">
      <div className="flex flex-wrap gap-2">
        {list.slice(0, 10).map((x) => (
          <button key={x.rep} type="button" onClick={() => pick(x.rep)}
            className={`btn-pill border px-3 py-1.5 text-sm ${user === x.rep ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--axis)] text-[var(--ink-2)] hover:text-[var(--ink)]"}`}>
            {x.rep} <span className="text-xs text-[var(--muted)]">{x.accepted}/{x.changes} accepted</span>
          </button>
        ))}
      </div>
    </Card>
    {err && <Message tone="bad">{err}</Message>}
    {!r ? (!err && <p className="text-sm text-[var(--muted)]">Building the rep's weeks…</p>) : (<>
      <Card title={`${r.rep.rep} against ${r.comparison?.rep || "–"}`} subtitle={`Over the ${r.weeks_run} pilot weeks. The comparison is ${r.comparison_rule}.`}>
        <RepTable a={r.rep} b={r.comparison} />
      </Card>
      <Card title="Week by week" subtitle="Visits each week for both reps; the green bars are the changes the engine made to this rep's plan (visits, calls and rep emails moved in).">
        <RepChart r={r} week={week} setWeek={setWeek} />
      </Card>
      {r.detail && <WeekDetail d={r.detail} weeks={r.weeks_run} week={week} setWeek={setWeek} />}
    </>)}
  </>);
}

function RepTable({ a, b }) {
  const rows = [["Doctors in the territory", "doctors", ""], ["Visits", "visits", ""], ["Visits with content matched to the doctor's stage", "visits_matched_pct", "%"],
    ["Visits ending with a next step", "next_step_pct", "%"], ["Their doctors who moved up a stage", "doctors_moved_up_pct", "%"],
    ["Changes from the engine", "changes", ""], ["… of which the rep accepted", "changes_accepted_pct", "%"]];
  return (
    <div className="overflow-auto rounded-xl border border-[var(--line)]">
      <table className="w-full text-sm">
        <thead className="bg-[var(--raised)]"><tr>
          <th className="px-3 py-2 text-left font-medium text-[var(--ink-2)]"></th>
          <th className="px-3 py-2 text-right font-medium text-[var(--accent)]">{a.rep} · test</th>
          <th className="px-3 py-2 text-right font-medium text-[var(--series-2)]">{b?.rep} · control</th>
        </tr></thead>
        <tbody>{rows.map(([label, k, u]) => (
          <tr key={k} className="border-t border-[var(--line)]">
            <td className="px-3 py-2 text-[var(--ink-2)]">{label}</td>
            <td className="tabular px-3 py-2 text-right font-semibold">{a[k] == null ? "–" : `${num(a[k])}${u}`}</td>
            <td className="tabular px-3 py-2 text-right">{b?.[k] == null ? "–" : `${num(b[k])}${u}`}</td>
          </tr>))}</tbody>
      </table>
    </div>
  );
}

function RepChart({ r, week, setWeek }) {
  const n = r.weeks_run, W = 640, L = 30, R = 10, T = 10, B = 24, H = 170;
  const va = r.rep.visits_by_week || {}, vb = r.comparison?.visits_by_week || {};
  const moved = Object.fromEntries((r.weeks || []).map((w) => [w.week, w.moved_in]));
  const max = Math.max(...Array.from({ length: n }, (_, i) => Math.max(va[i + 1] || 0, vb[i + 1] || 0, moved[i + 1] || 0)), 1);
  const x = (w) => L + ((w - 0.5) * (W - L - R)) / n, y = (v) => T + (H - T - B) * (1 - v / max), bw = (W - L - R) / n * 0.5;
  const line = (m) => Array.from({ length: n }, (_, i) => `${i ? "L" : "M"} ${x(i + 1)} ${y(m[i + 1] || 0)}`).join(" ");
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Visits by week">
        {[0, 0.5, 1].map((f) => <g key={f}><line x1={L} x2={W - R} y1={y(max * f)} y2={y(max * f)} stroke="var(--line)" /><text x={L - 4} y={y(max * f) + 3} textAnchor="end" fontSize="9" fill="var(--muted)">{Math.round(max * f)}</text></g>)}
        {Array.from({ length: n }, (_, i) => i + 1).map((w) => (
          <g key={w} onClick={() => setWeek(w)} style={{ cursor: "pointer" }}>
            <rect x={x(w) - bw / 2} y={y(moved[w] || 0)} width={bw} height={H - B - y(moved[w] || 0)} rx="2" fill={w === week ? "var(--good-ink)" : "var(--good)"} opacity={w === week ? 1 : 0.7} />
            <rect x={x(w) - bw} y={T} width={bw * 2} height={H - T - B} fill="transparent" />
            {(w === 1 || w % 4 === 0) && <text x={x(w)} y={H - 8} textAnchor="middle" fontSize="9" fill="var(--muted)">{w}</text>}
          </g>
        ))}
        <path d={line(vb)} fill="none" stroke="var(--series-2)" strokeWidth="2" />
        <path d={line(va)} fill="none" stroke="var(--accent)" strokeWidth="2.5" />
      </svg>
      <div className="mt-1 flex flex-wrap gap-4 text-xs text-[var(--ink-2)]">
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-[var(--accent)]" />{r.rep.rep} visits</span>
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-[var(--series-2)]" />{r.comparison?.rep} visits</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-[var(--good)]" />changes from the engine (click a week)</span>
      </div>
    </div>
  );
}

function WeekDetail({ d, weeks, week, setWeek }) {
  const tone = { sent: "neutral", moved: "accent", blocked: "bad" };
  return (
    <Card title={`Week ${d.week}: the week of ${d.date}`} subtitle="What the rep saw on Monday: their plan, the engine's changes with the reason, what they decided, and the talk track."
      actions={<select className="rounded-full border border-[var(--axis)] bg-[var(--raised)] px-3 py-1.5 text-sm" value={week || d.week} onChange={(e) => setWeek(Number(e.target.value))} aria-label="Week">
        {Array.from({ length: weeks }, (_, i) => <option key={i + 1} value={i + 1}>Week {i + 1}</option>)}
      </select>}>
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="space-y-4">
          <div>
            <div className="kicker mb-2 text-[11px]">The plan ({d.planned.length})</div>
            <div className="space-y-1">
              {d.planned.map((p, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--line)] bg-black/20 px-3 py-1.5 text-sm">
                  <span className="font-medium">{p.doctor}</span><span className="text-[var(--ink-2)]">{p.channel}, {words(p.theme)}</span>
                  <Badge tone={tone[p.status] || "neutral"}>{p.status === "sent" ? "as planned" : p.status === "moved" ? "given to another doctor" : "blocked"}</Badge>
                </div>
              ))}
              {d.planned.length === 0 && <p className="text-sm text-[var(--muted)]">No planned visits, calls or rep emails this week.</p>}
            </div>
          </div>
          <div>
            <div className="kicker mb-2 text-[11px]">Changes from the engine ({d.changes.length})</div>
            <div className="space-y-1.5">
              {d.changes.map((c, i) => (
                <div key={i} className="rounded-lg border border-[rgba(255,143,122,0.35)] bg-[rgba(255,143,122,0.06)] px-3 py-2 text-sm">
                  <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{c.doctor}</span><span className="text-[var(--ink-2)]">{c.channel}, {words(c.theme)}</span>
                    <Badge tone={c.rep_decision === "accepted" ? "good" : c.rep_decision === "dismissed" ? "bad" : "neutral"}>{c.rep_decision === "dismissed" ? "declined: planned touch went ahead" : c.rep_decision}</Badge></div>
                  <div className="mt-1 text-xs text-[var(--muted)]">{c.why}</div>
                </div>
              ))}
              {d.changes.length === 0 && <p className="text-sm text-[var(--muted)]">No changes this week: the plan went ahead as it was.</p>}
            </div>
          </div>
        </div>
        <div>
          <div className="kicker mb-2 text-[11px]">Monday talk track</div>
          {d.talk_track ? <div className="whitespace-pre-line rounded-xl border border-[var(--line)] bg-black/20 p-4 text-sm leading-relaxed">{d.talk_track}</div>
            : <p className="text-sm text-[var(--muted)]">No talk track this week.</p>}
        </div>
      </div>
    </Card>
  );
}
