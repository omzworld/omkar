// Scene 5: feedback. Run to week 8, watch the loop fill week by week, see what reps accepted and dismissed by
// rule, and approve a change the engine proposes.
import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { api, num, pct, words } from "../api";
import { Badge, Bars, Button, Card, Stat, Table } from "../ui";
import { CountUp } from "../fx.jsx";
import { FeedbackLoop, PilotConsole, Ring } from "../viz.jsx";

const GATE = 45;   // pilot gate: reps accept at least 45% of suggestions

export default function Feedback({ pilot, runPilot }) {
  const [f, setF] = useState(null);
  const [msg, setMsg] = useState(null);
  const [approved, setApproved] = useState({});
  const done = pilot?.completed_weeks ?? 0;
  const running = pilot?.running;

  const load = () => api("/feedback").then(setF).catch(() => setF(null));
  useEffect(() => { load(); }, [done]);   // refreshes after every completed week, also while the pilot runs

  const approve = async (rule) => {
    try {
      const v = await api(`/feedback/proposals/${rule}/approve`, {});
      setApproved((a) => ({ ...a, [rule]: v }));
      setMsg(`Approved: ${rule} is now version ${v.version}${v.paused ? " (paused)" : ""}. It applies from the next week the pilot runs.`);
      setTimeout(load, 1800);
    } catch (e) { setMsg(e.message); }
  };

  const has = f?.weeks > 0;
  const total = has ? f.by_week.reduce((a, w) => a + w.suggestions, 0) : 0;
  const acc = has ? f.by_week.reduce((a, w) => a + w.accepted, 0) : 0;
  const dismissed = has ? f.dismiss_reasons.reduce((a, d) => a + d.count, 0) : 0;
  // The pilot gate is measured over the last four weeks, as on the Results screen.
  const recent = has ? f.by_week.slice(-4) : [];
  const gatePct = recent.length ? (100 * recent.reduce((a, w) => a + w.accepted, 0)) / Math.max(recent.reduce((a, w) => a + w.suggestions, 0), 1) : 0;
  const met = gatePct >= GATE;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Feedback</h1>
        <p className="mt-1 max-w-3xl text-[var(--ink-2)]">
          Reps accept or dismiss each suggestion and say why. The engine reads that back every week, and proposes
          changes to rules the field keeps turning down. Run the pilot and watch the loop fill, week by week.
        </p>
      </header>

      <PilotConsole pilot={pilot} note="Test territories get the engine; control territories keep today's plan. About 4 seconds a week."
        actions={<>
          <Button onClick={() => runPilot(8, done === 0 || done > 8)} disabled={running}>▶ Run to week 8</Button>
          <Button kind="secondary" onClick={() => runPilot(26)} disabled={running || done >= 26}>Carry on to week 26</Button>
          <Button kind="secondary" onClick={() => { if (confirm("Start the pilot again from week 1?")) runPilot(8, true); }} disabled={running}>Start again</Button>
        </>} />

      <AnimatePresence>
        {msg && (
          <motion.div initial={{ opacity: 0, y: -8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0 }}
            className="glass flex items-start justify-between gap-3 rounded-xl border-[var(--good)] px-4 py-3 text-sm shadow-[0_0_30px_-10px_var(--good)]">
            <span><span className="mr-2 text-[var(--good-ink)]">✓</span>{msg}</span>
            <button onClick={() => setMsg(null)} className="text-[var(--muted)] hover:text-[var(--ink)]" aria-label="Close">✕</button>
          </motion.div>
        )}
      </AnimatePresence>

      {!has && (
        <Card>
          <div className="grid items-center gap-6 md:grid-cols-[1fr_auto]">
            <div>
              <h2 className="display text-xl font-semibold">No responses yet</h2>
              <p className="mt-2 max-w-xl text-[var(--ink-2)]">
                Press <strong className="text-[var(--ink)]">Run to week 8</strong>. Each simulated week, reps accept or dismiss what the engine
                suggested, and this screen fills in live: the loop, acceptance against the 45% gate, why reps said no, and the
                rule changes the engine proposes.
              </p>
            </div>
            <div className="opacity-40"><FeedbackLoop sent={0} accepted={1} dismissed={1} proposals={0} weeks={0} /></div>
          </div>
        </Card>
      )}

      {has && (<>
        <div className="grid gap-6 xl:grid-cols-[1.1fr_1fr]">
          <Card title="The feedback loop" subtitle="Every suggestion comes back as accepted or dismissed. Green dots are accepted, red dismissed, in their real proportion.">
            <FeedbackLoop sent={total} accepted={acc} dismissed={dismissed} proposals={f.proposals.length} weeks={f.weeks} />
          </Card>
          <Card title="Are reps taking the suggestions?" subtitle={`Pilot gate: reps accept at least ${GATE}% of suggestions over the last 4 weeks. The white tick marks ${GATE}%.`}>
            <div className="flex flex-wrap items-center justify-center gap-8 py-2">
              <Ring value={gatePct} max={100} size={170} stroke={14} target={GATE} color={met ? "var(--good)" : "var(--bad)"}>
                <div className={`display tabular text-4xl font-semibold ${met ? "text-[var(--good-ink)]" : "text-[var(--bad)]"}`}>
                  <CountUp value={pct(gatePct, 1)} />
                </div>
                <div className="text-xs text-[var(--ink-2)]">accepted,<br />last 4 weeks</div>
              </Ring>
              <div className="space-y-3 text-sm">
                <Kpi label="Suggestions to reps" value={num(total)} note={`over ${f.weeks} weeks`} />
                <Kpi label="Accepted overall" value={pct((100 * acc) / Math.max(total, 1), 0)} note={`${num(acc)} suggestions`} />
                <Kpi label="Gate" value={met ? "Met" : "Not met"} tone={met ? "good" : "bad"} note={`target ${GATE}%`} />
              </div>
            </div>
            <WeekColumns weeks={f.by_week} />
          </Card>
        </div>

        <Card title="What the engine proposes" subtitle="Rule R134: a rule with at least 20 triggers in 30 days whose suggestions reps accepted less than 40% of the time.">
          {f.proposals.length === 0 ? <p className="text-sm text-[var(--muted)]">No rule is below the bar this week.</p> : (
            <div className="space-y-3">
              {f.proposals.map((p, i) => {
                const ok = approved[p.rule_id];
                return (
                  <motion.div key={p.rule_id} initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.1 }}
                    className={`relative overflow-hidden rounded-2xl border p-4 transition ${ok ? "border-[var(--good)] bg-[rgba(52,211,153,0.08)]" : "border-[rgba(167,139,250,0.4)] bg-[rgba(167,139,250,0.06)] shadow-[0_0_30px_-12px_var(--accent-2)]"}`}>
                    <div className="flex flex-wrap items-center justify-between gap-4">
                      <div className="max-w-3xl">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="display font-semibold text-[var(--accent-2)]">{p.rule_id}</span><Badge>{words(p.family)}</Badge>
                          <Badge tone="bad">{pct(100 * p.acceptance_rate, 0)} accepted</Badge>
                          <Badge>mostly “{words(p.top_dismiss_reason)}”</Badge>
                        </div>
                        <p className="mt-2 text-sm text-[var(--ink-2)]">{p.reason}.</p>
                        {Object.keys(p.proposed || {}).length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-3">
                            {Object.entries(p.proposed).map(([k, v]) => (
                              <div key={k} className="flex items-center gap-2 rounded-xl border border-[var(--line)] bg-black/20 px-3 py-1.5 text-sm">
                                <span className="text-[var(--muted)]">{words(k)}</span>
                                <span className="tabular text-[var(--bad)] line-through decoration-1">{String(p.current?.[k])}</span>
                                <motion.span animate={{ x: [0, 4, 0] }} transition={{ repeat: Infinity, duration: 1.4 }} className="text-[var(--accent)]">→</motion.span>
                                <span className="display tabular font-semibold text-[var(--good-ink)]">{String(v)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        <code className="mt-2 block text-xs text-[var(--muted)]">{p.condition}</code>
                      </div>
                      {ok ? (
                        <motion.div initial={{ scale: 0.5, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="flex items-center gap-2 font-semibold text-[var(--good-ink)]">
                          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--good)] text-[#04111c]">✓</span>Version {ok.version}
                        </motion.div>
                      ) : (
                        <Button onClick={() => approve(p.rule_id)}>{Object.keys(p.proposed || {}).length ? "Approve the change" : "Approve: pause the rule"}</Button>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Why reps dismissed suggestions" subtitle="The reason reps picked when they said no. The engine uses it to tune the rule.">
            <Bars data={f.dismiss_reasons.map((d) => ({ ...d, reason: words(d.reason) }))} label="reason" value="count" color="var(--series-2)" />
          </Card>
          <div className="grid grid-cols-2 gap-3 self-start">
            <Stat label="Accepted" value={num(acc)} note="suggestions reps took up" tone="good" />
            <Stat label="Dismissed" value={num(dismissed)} note="each with a reason" tone="bad" />
            <Stat label="Rules with feedback" value={num(f.by_rule.length)} note="rules that reached reps" />
            <Stat label="Proposals from the engine" value={num(f.proposals.length)} note="rules reps keep turning down" />
          </div>
        </div>

        <Card title="Acceptance by rule" subtitle="Lowest first.">
          <Table maxHeight="28rem" rows={f.by_rule} columns={[
            { key: "rule_id", label: "Rule" }, { key: "reason_template", label: "What it says", wide: true },
            { key: "suggestions", label: "Suggestions", num: true }, { key: "accepted", label: "Accepted", num: true },
            { key: "acceptance_rate", label: "Rate", num: true, render: (r) => <RateCell rate={r.acceptance_rate} /> },
            { key: "top_dismiss_reason", label: "Main reason when dismissed", render: (r) => words(r.top_dismiss_reason) || "–" }]} />
        </Card>
      </>)}
    </div>
  );
}

function Kpi({ label, value, note, tone }) {
  const c = tone === "good" ? "text-[var(--good-ink)]" : tone === "bad" ? "text-[var(--bad)]" : "text-[var(--ink)]";
  return (
    <div>
      <div className="text-xs text-[var(--muted)]">{label}</div>
      <div className={`display tabular text-xl font-semibold ${c}`}><CountUp value={value} /></div>
      {note && <div className="text-xs text-[var(--muted)]">{note}</div>}
    </div>
  );
}

// Weekly acceptance as glowing columns, with the 45% gate drawn across.
function WeekColumns({ weeks }) {
  const top = 70;
  return (
    <div className="mt-4">
      <div className="mb-1 text-xs text-[var(--muted)]">Acceptance each week</div>
      <div className="relative h-32">
        <div className="absolute inset-x-0 z-10 border-t-2 border-dashed border-white/70" style={{ bottom: `${(100 * GATE) / top}%` }}>
          <span className="absolute -top-5 right-0 rounded bg-black/60 px-1 text-[10px] text-white">{GATE}%</span>
        </div>
        <div className="absolute inset-0 flex items-end gap-1.5">
          {weeks.map((w, i) => {
            const ok = w.acceptance_pct >= GATE;
            return (
              <div key={i} className="group relative flex h-full flex-1 items-end">
                <motion.div className="w-full rounded-t-md" title={`Week ${i + 1}: ${pct(w.acceptance_pct, 0)}`}
                  style={{ background: ok ? "linear-gradient(to top, rgba(52,211,153,0.2), #34d399)" : "linear-gradient(to top, rgba(248,113,113,0.2), #f87171)", boxShadow: `0 0 12px -2px ${ok ? "#34d399" : "#f87171"}` }}
                  initial={{ height: 0 }} animate={{ height: `${(100 * Math.min(w.acceptance_pct, top)) / top}%` }} transition={{ delay: i * 0.05, duration: 0.7, ease: [0.16, 1, 0.3, 1] }} />
                <span className="tabular pointer-events-none absolute -top-5 left-1/2 -translate-x-1/2 text-[10px] text-[var(--ink-2)] opacity-0 transition group-hover:opacity-100">{num(w.acceptance_pct, 0)}%</span>
              </div>
            );
          })}
        </div>
      </div>
      <div className="mt-1 flex gap-1.5 text-[10px] text-[var(--muted)]">
        {weeks.map((_, i) => <span key={i} className="flex-1 text-center">{weeks.length <= 13 || i % 2 === 0 ? i + 1 : ""}</span>)}
      </div>
    </div>
  );
}

function RateCell({ rate }) {
  const p = 100 * rate;
  const c = p >= GATE ? "var(--good)" : p >= 40 ? "var(--warn)" : "var(--bad)";
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-[var(--chip)]"><span className="block h-full rounded-full" style={{ width: `${p}%`, background: c }} /></span>
      <span className="tabular w-9 text-right">{pct(p, 0)}</span>
    </span>
  );
}
