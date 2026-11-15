// Scene 6: results and return. Test versus control, lift, cost per engaged physician, the return model and
// break-even, with assumptions you change by dragging and see the dial move.
import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { api, eur, num, pct } from "../api";
import { Button, Card, Field, inputClass, Message, Stat, Table } from "../ui";
import { CountUp } from "../fx.jsx";
import { GapChart, PilotConsole, ReturnDial } from "../viz.jsx";

const EASE = [0.16, 1, 0.3, 1];

export default function Results({ pilot, runPilot }) {
  const done = pilot?.completed_weeks ?? 0;
  const running = pilot?.running;
  // null = use the assumptions file or the measured value
  const [inputs, setInputs] = useState({ fee: null, margin: 70, sales: "", lift: null, savings: false });
  const [m, setM] = useState(null);
  const [err, setErr] = useState(null);
  const first = useRef(true);

  const load = () => {
    const q = new URLSearchParams();
    if (inputs.fee !== null) q.set("fee", inputs.fee);
    q.set("margin", inputs.margin);
    if (inputs.sales) q.set("sales", inputs.sales);
    if (inputs.lift !== null) q.set("lift", inputs.lift);
    q.set("savings", inputs.savings);
    api(`/measure?${q}`).then((d) => { setM(d); setErr(null); }).catch((e) => setErr(e.message));
  };
  useEffect(() => { if (done) load(); }, [done]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {                                  // recalculate shortly after any assumption changes
    if (first.current) { first.current = false; return; }
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [inputs]);                                      // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k, v) => setInputs((s) => ({ ...s, [k]: v }));
  const arm = (name) => m?.arms?.find((a) => a.pilot_arm === name);
  const rm = m?.return_model;
  const ready = m?.weeks > 0 && m.lift?.months_measured > 0;
  const T = arm("test"), C = arm("control");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Results and return</h1>
        <p className="mt-1 max-w-3xl text-[var(--ink-2)]">
          Test territories ran the quarterly plan with weekly reallocation; control territories ran today's plan.
          Both had the same budget: test spent last year's, moved inside it. Territories were split before the pilot
          and never changed, so the difference between them is the effect of better allocation, not of more spend.
        </p>
      </header>

      <PilotConsole pilot={pilot}
        note={done ? `Measured over ${done} weeks${m?.from ? `, ${m.from} to ${m.to}` : ""}. Results update live as weeks complete.` : "The pilot has not run yet."}
        actions={<Button onClick={() => runPilot(26)} disabled={running || done >= 26}>▶ Run to week 26</Button>} />
      {err && <Message tone="bad">{err}</Message>}

      {!ready && (
        <Card>
          <h2 className="display text-xl font-semibold">{done ? "Waiting for the first full pilot month" : "No results yet"}</h2>
          <p className="mt-2 max-w-2xl text-[var(--ink-2)]">
            {done ? "Sales lift is measured by month, so it appears once the first pilot month is complete. Keep the pilot running."
              : <>Press <strong className="text-[var(--ink)]">Run to week 26</strong> and watch test pull away from control, the gates light up, and the return dial settle.</>}
          </p>
        </Card>
      )}

      {ready && (<>
        {/* The verdict */}
        <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: EASE }}
          className="glass relative overflow-hidden rounded-3xl p-6 md:p-8">
          <div aria-hidden className="absolute -right-24 -top-24 h-72 w-72 rounded-full blur-3xl" style={{ background: m.lift.lift_pts > 0 ? "rgba(79,209,161,0.25)" : "rgba(255,107,107,0.25)" }} />
          <div className="relative grid items-center gap-6 lg:grid-cols-[auto_1fr]">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--accent-2)]">Brick sales lift, test vs control</div>
              <div className={`display tabular mt-1 text-6xl font-semibold md:text-7xl ${m.lift.lift_pts > 0 ? "text-[var(--good-ink)]" : "text-[var(--bad)]"}`}
                style={{ textShadow: `0 0 40px ${m.lift.lift_pts > 0 ? "rgba(79,209,161,0.5)" : "rgba(255,107,107,0.5)"}` }}>
                <CountUp value={`${m.lift.lift_pts >= 0 ? "+" : ""}${num(m.lift.lift_pts, 1)}`} /><span className="text-3xl"> pts</span>
              </div>
              <div className="mt-1 text-sm text-[var(--ink-2)]">{m.lift.first_month} to {m.lift.last_month}, against the months before</div>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <Mini label="Test territories" value={pct(m.lift.test_growth_pct)} note="Movicol unit growth" color="var(--accent)" />
              <Mini label="Control territories" value={pct(m.lift.control_growth_pct)} note="Movicol unit growth" color="var(--series-2)" />
              <Mini label="Extra units sold" value={num(m.lift.incremental_units)} note="beyond what control growth predicts" color="var(--good)" />
            </div>
          </div>
        </motion.section>

        {m.spend && <SpendCheck sp={m.spend} />}
        {m.reallocation?.planned_due > 0 && <Reallocated r={m.reallocation} />}

        <Card title="Movicol brick sales, test vs control" subtitle="Units per month, indexed so the six months before the pilot average 100. One axis for both groups; the green area is the gap the engine opened.">
          <GapChart data={m.monthly_index} />
        </Card>

        <div className="grid gap-6 xl:grid-cols-2">
          <Card title="Head to head" subtitle="Physicians who can be promoted to, over the pilot weeks. Longer bar = more.">
            <div className="mb-3 flex gap-4 text-xs text-[var(--ink-2)]">
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[var(--accent)]" />Test</span>
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[var(--series-2)]" />Control</span>
            </div>
            <div className="space-y-3">
              {[
                ["Physicians", "physicians", (v) => num(v)], ["Touches", "touches", (v) => num(v)],
                ["Touches per physician", "touches_per_physician", (v) => num(v, 1)],
                ["Reached at least once", "reach_pct", (v) => pct(v)], ["Responded at least once", "engaged_pct", (v) => pct(v)],
                ["Share of touches answered", "response_pct", (v) => pct(v)], ["Moved up a journey stage", "moved_up_pct", (v) => pct(v)],
                ["Moved back a stage", "moved_back_pct", (v) => pct(v)], ["Cost of touches", "cost_eur", (v) => eur(v)],
                ["Cost per engaged physician", "cost_per_engaged_eur", (v) => eur(v)],
              ].map(([label, key, f], i) => <Pair key={key} i={i} label={label} t={T?.[key]} c={C?.[key]} f={f} />)}
            </div>
          </Card>

          <Card title="Pilot gates" subtitle="The success criteria agreed for the pilot.">
            <div className="space-y-2.5">
              {m.gates.map((g, i) => <Gate key={g.gate} g={g} i={i} />)}
            </div>
            <div className="mt-4 text-sm text-[var(--ink-2)]">
              <strong className="text-[var(--ink)]">{m.gates.filter((g) => g.passed).length} of {m.gates.length}</strong> gates met after {m.weeks} weeks.
            </div>
          </Card>
        </div>

        {/* The return model */}
        <Card title="Return model" subtitle="What the lift and the freed field time are worth against the fee, per quarter. Drag any assumption and the dial moves.">
          <div className="grid gap-8 lg:grid-cols-[1fr_1.1fr]">
            <div className="space-y-5">
              <Slider label="Fee per quarter" value={inputs.fee ?? rm?.fee_per_quarter_eur ?? 180000} min={0} max={500000} step={10000}
                show={(v) => eur(v)} onChange={(v) => set("fee", v)} changed={inputs.fee !== null} reset={() => set("fee", null)} hint="from the assumptions file until you drag it" />
              <Slider label="Gross margin" value={inputs.margin} min={30} max={95} step={1} show={(v) => `${v}%`} onChange={(v) => set("margin", v)} />
              <Slider label="Lift to use" value={inputs.lift ?? m.lift.lift_pts} min={-2} max={10} step={0.1}
                show={(v) => `${num(v, 1)} pts`} onChange={(v) => set("lift", v)} changed={inputs.lift !== null} reset={() => set("lift", null)}
                hint={`measured: ${num(m.lift.lift_pts, 1)} pts`} />
              <Field label="Brand sales per quarter (€)" hint="blank = synthetic test territories; enter the client's real figure to see roll-out scale">
                <input className={inputClass} value={inputs.sales} onChange={(e) => set("sales", e.target.value)} placeholder="e.g. 20000000" inputMode="numeric" />
              </Field>
              <label className="flex items-center gap-3 text-sm" title="Off by default: the budget is the same in both arms, so there is no saving to count.">
                <button type="button" role="switch" aria-checked={inputs.savings} onClick={() => set("savings", !inputs.savings)}
                  className={`relative h-6 w-11 rounded-full transition ${inputs.savings ? "bg-[var(--accent)] shadow-[0_0_14px_-2px_var(--accent)]" : "bg-[var(--chip)]"}`}>
                  <motion.span layout className="absolute top-1 h-4 w-4 rounded-full bg-white" style={{ left: inputs.savings ? 24 : 4 }} />
                </button>
                Count freed field time <span className="text-xs text-[var(--muted)]">(only if reps' time is redeployed)</span>
              </label>
            </div>

            {rm && (
              <div>
                <ReturnDial value={rm.return_on_fee} />
                <Waterfall rm={rm} />
              </div>
            )}
          </div>
          {rm && (<>
            <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Extra gross margin per quarter" value={eur(rm.incremental_margin_per_quarter_eur)} note={`${num(rm.lift_pts_used, 1)} pts on ${eur(rm.baseline_sales_per_quarter_eur)} sales${rm.baseline_is_synthetic ? " (synthetic)" : ""}`} />
              <Stat label="Touch cost saving per quarter" value={eur(rm.touch_cost_saving_per_quarter_eur)} note={rm.count_touch_savings ? "counted" : "not counted"} />
              <Stat label="Net benefit per quarter" value={eur(rm.net_benefit_per_quarter_eur)} note={`after a fee of ${eur(rm.fee_per_quarter_eur)}`} tone={rm.net_benefit_per_quarter_eur >= 0 ? "good" : "bad"} />
              <Stat label="Break-even lift" value={`${num(rm.break_even_lift_pts, 2)} pts`} note={rm.break_even_lift_pts === 0 ? "the saving alone covers the fee" : `measured: ${num(m.lift.lift_pts, 1)} pts`} tone={m.lift.lift_pts >= rm.break_even_lift_pts ? "good" : "bad"} />
            </div>
            <p className="mt-3 text-xs text-[var(--muted)]">
              Return on the fee: {num(rm.return_on_fee, 2)}×. Fee at risk if the 4-point lift gate is missed: {eur(rm.fee_at_risk_eur)}.
              The synthetic market is small; enter the client's real brand sales to see the return at roll-out scale.
            </p>
          </>)}
        </Card>
      </>)}
    </div>
  );
}

function Mini({ label, value, note, color }) {
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-black/20 p-4" style={{ boxShadow: `inset 0 1px 0 ${color}` }}>
      <div className="text-xs text-[var(--ink-2)]">{label}</div>
      <div className="display tabular mt-1 text-2xl font-semibold" style={{ color }}><CountUp value={value} /></div>
      <div className="text-xs text-[var(--muted)]">{note}</div>
    </div>
  );
}

// One metric, test and control as two bars on the same scale.
function Pair({ label, t, c, f, i }) {
  const max = Math.max(t ?? 0, c ?? 0) || 1;
  const bar = (v, color, d) => (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--chip)]">
        <motion.div className="h-full rounded-full" style={{ background: color, boxShadow: `0 0 10px ${color}` }}
          initial={{ width: 0 }} whileInView={{ width: `${(100 * (v ?? 0)) / max}%` }} viewport={{ once: true }} transition={{ delay: 0.1 + i * 0.05 + d, duration: 0.8, ease: EASE }} />
      </div>
      <span className="tabular w-20 text-right text-xs">{f(v)}</span>
    </div>
  );
  return (
    <div className="grid grid-cols-[minmax(8rem,11rem)_1fr] items-center gap-3 text-sm">
      <span className="text-[var(--ink-2)]">{label}</span>
      <div className="space-y-1">{bar(t, "var(--accent)", 0)}{bar(c, "var(--series-2)", 0.1)}</div>
    </div>
  );
}

// A gate lights up green or red in turn, with its result against the target.
function Gate({ g, i }) {
  const color = g.passed ? "var(--good)" : "var(--bad)";
  return (
    <motion.div initial={{ opacity: 0, x: 20 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: 0.2 + i * 0.25, duration: 0.5, ease: EASE }}
      className="flex items-center gap-3 rounded-xl border border-[var(--line)] bg-black/20 p-3">
      <motion.span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold text-[#ffffff]"
        initial={{ scale: 0, backgroundColor: "rgba(140,140,160,0.2)" }} whileInView={{ scale: 1, backgroundColor: g.passed ? "#4fd1a1" : "#ff6b6b" }}
        viewport={{ once: true }} transition={{ delay: 0.45 + i * 0.25, type: "spring", stiffness: 300, damping: 15 }}
        style={{ boxShadow: `0 0 18px -2px ${color}` }}>{g.passed ? "✓" : "✕"}</motion.span>
      <div className="min-w-0 flex-1">
        <div className="text-sm">{g.gate}</div>
        <div className="text-xs text-[var(--muted)]">{g.cadence} · target {g.rule === ">=" ? "at least" : "at most"} {num(g.target)}{g.unit}</div>
      </div>
      <div className="display tabular text-right text-lg font-semibold" style={{ color }}>{num(g.value, 1)}<span className="text-xs">{g.unit}</span></div>
    </motion.div>
  );
}

function Slider({ label, value, min, max, step, show, onChange, changed, reset, hint }) {
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span className="text-[var(--ink-2)]">{label}</span>
        <span className="flex items-baseline gap-2">
          {changed && reset && <button onClick={reset} className="text-xs text-[var(--muted)] hover:text-[var(--accent)]">reset</button>}
          <span className="display tabular text-lg font-semibold text-[var(--accent)]">{show(value)}</span>
        </span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 w-full accent-[var(--accent)]" aria-label={label} />
      {hint && <div className="text-xs text-[var(--muted)]">{hint}</div>}
    </div>
  );
}

// Margin plus saving minus fee equals net benefit, as bars from a shared zero line.
function Waterfall({ rm }) {
  const rows = [
    { label: "Extra gross margin", v: rm.incremental_margin_per_quarter_eur, color: "var(--accent)" },
    { label: "Touch cost saving", v: rm.count_touch_savings ? rm.touch_cost_saving_per_quarter_eur : 0, color: "var(--accent-2)" },
    { label: "Fee", v: -rm.fee_per_quarter_eur, color: "var(--series-2)" },
    { label: "Net benefit", v: rm.net_benefit_per_quarter_eur, color: rm.net_benefit_per_quarter_eur >= 0 ? "var(--good)" : "var(--bad)", bold: true },
  ];
  const max = Math.max(...rows.map((r) => Math.abs(r.v)), 1);
  return (
    <div className="mt-5 space-y-2">
      <div className="text-xs text-[var(--muted)]">Per quarter: what goes in and what comes out</div>
      {rows.map((r, i) => (
        <div key={r.label} className={`grid grid-cols-[8.5rem_1fr_6rem] items-center gap-2 text-sm ${r.bold ? "border-t border-[var(--line)] pt-2 font-semibold" : ""}`}>
          <span className="text-[var(--ink-2)]">{r.label}</span>
          <div className="relative h-3">
            <div className="absolute inset-y-0 left-1/2 w-px bg-[var(--axis)]" />
            <motion.div className="absolute inset-y-0 rounded" style={{ background: r.color, boxShadow: `0 0 10px ${r.color}`, [r.v >= 0 ? "left" : "right"]: "50%" }}
              animate={{ width: `${(50 * Math.abs(r.v)) / max}%` }} transition={{ delay: i * 0.08, duration: 0.7, ease: EASE }} />
          </div>
          <span className="tabular text-right">{r.v < 0 ? "−" : ""}{eur(Math.abs(r.v))}</span>
        </div>
      ))}
    </div>
  );
}

// The budget-neutral check: same spend per physician in both arms, and test against its own planned budget.
function SpendCheck({ sp }) {
  const ok = sp.equal;
  const ch = { rep_visit: "Visits", remote_call: "Remote calls", rep_email: "Rep emails", marketing_email: "Marketing emails", webinar: "Webinar seats" };
  return (
    <Card title="Same budget in both arms?" subtitle={`Spend per physician over the pilot. Budget neutral means within ±${sp.tolerance_pct}%.`}
      actions={<span className={`btn-pill border px-3 py-1 text-sm font-semibold ${ok ? "border-[var(--good)] text-[var(--good-ink)]" : "border-[var(--warn)] text-[var(--warn)]"}`}>{ok ? "✓ Budget neutral" : "Outside the band"}</span>}>
      <div className="grid gap-3 sm:grid-cols-3">
        <Box label="Spend per physician" a={eur(sp.test_cost_per_physician_eur)} b={eur(sp.control_cost_per_physician_eur)} diff={sp.cost_diff_pct} />
        <Box label="Touches per physician" a={num(sp.test_touches_per_physician, 1)} b={num(sp.control_touches_per_physician, 1)} diff={sp.touches_diff_pct} />
        {sp.plan_budget_eur != null && (
          <div className="rounded-2xl border border-[var(--line)] bg-black/20 p-4">
            <div className="text-xs text-[var(--ink-2)]">Test against its planned budget</div>
            <div className="display tabular mt-1 text-2xl font-bold">{eur(sp.plan_spent_eur)}</div>
            <div className="text-xs text-[var(--muted)]">of {eur(sp.plan_budget_eur)} planned ({sp.vs_plan_pct >= 0 ? "+" : ""}{num(sp.vs_plan_pct, 1)}%): touches blocked by consent or eligibility are not made up</div>
          </div>
        )}
      </div>
      <div className="mt-4">
        <Table rows={sp.by_channel} columns={[
          { key: "channel", label: "Per physician", render: (r) => ch[r.channel] || r.channel },
          { key: "test_per_physician", label: "Test", num: true }, { key: "control_per_physician", label: "Control", num: true },
          { key: "cost_per_touch_eur", label: "Cost per touch", num: true, render: (r) => eur(r.cost_per_touch_eur) }]} />
      </div>
      <p className="mt-3 text-xs text-[var(--muted)]">Test spends last year's budget. Today's plan in control is not capped and drifts with the email list and the visit trend, so a small gap against control is expected; the plan itself is the budget.</p>
    </Card>
  );
}

function Box({ label, a, b, diff }) {
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-black/20 p-4">
      <div className="text-xs text-[var(--ink-2)]">{label}</div>
      <div className="mt-1 flex items-baseline gap-2"><span className="display tabular text-2xl font-bold text-[var(--accent)]">{a}</span><span className="text-sm text-[var(--muted)]">test</span></div>
      <div className="flex items-baseline gap-2"><span className="display tabular text-lg font-semibold text-[var(--series-2)]">{b}</span><span className="text-sm text-[var(--muted)]">control</span></div>
      <div className="text-xs text-[var(--muted)]">{diff >= 0 ? "+" : ""}{num(diff, 1)}% test against control</div>
    </div>
  );
}

// What the engine moved over the pilot, and from which segments to which.
function Reallocated({ r }) {
  const max = Math.max(...r.by_segment.map((x) => Math.abs(x.net)), 1);
  return (
    <Card title="What the engine reallocated" subtitle={`${num(r.moved)} of ${num(r.planned_due)} planned touches (${num(r.moved_pct, 1)}%) moved to a physician who needed them more; ${num(r.delivered_as_planned)} went ahead as planned.`}>
      <div className="space-y-1.5">
        {r.by_segment.map((x, i) => (
          <div key={x.segment} className="grid grid-cols-[minmax(10rem,15rem)_1fr_6rem] items-center gap-3 text-sm">
            <span className="text-[var(--ink-2)]">{x.segment}</span>
            <div className="relative h-3">
              <div className="absolute inset-y-0 left-1/2 w-px bg-[var(--axis)]" />
              <motion.div className="absolute inset-y-0 rounded" style={{ background: x.net >= 0 ? "var(--good)" : "var(--accent-2)", [x.net >= 0 ? "left" : "right"]: "50%" }}
                initial={{ width: 0 }} whileInView={{ width: `${(50 * Math.abs(x.net)) / max}%` }} viewport={{ once: true }} transition={{ delay: i * 0.04, duration: 0.6 }} />
            </div>
            <span className="tabular text-right">{x.net >= 0 ? "+" : ""}{num(x.net)} <span className="text-xs text-[var(--muted)]">net</span></span>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-[var(--muted)]">Net touches gained (green) or given up (coral) by each segment, after the quarterly plan. Moves are like for like and never add to the total.</p>
    </Card>
  );
}
