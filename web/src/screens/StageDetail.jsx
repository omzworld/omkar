// The zoomed-in view of one platform stage: a plain explanation on the left, live engine numbers on the right.
import { motion } from "motion/react";
import { eur, num, pct, words } from "../api";
import { CountUp } from "../fx.jsx";

// The six stages, in the order the engine runs them each week. `to` is the screen that shows the stage in full.
export const STAGES = [
  { key: "data", title: "Read the data", to: "data",
    text: "Every week starts from what is known about each doctor and account: calls, emails, events, sales by area and consent to be contacted.",
    how: ["Client source formats: Veeva CRM, PromoMats, OpenData, IQVIA", "24 months of history, checked live", "Consent recorded per channel and market"] },
  { key: "plan", title: "Segment & plan", to: "plan",
    text: "Each quarter every physician is segmented on potential, adoption and responsiveness, and last year's budget becomes a plan: the same total, shifted to the segments where a touch is worth most. Reps adjust it.",
    how: ["Same budget as last year, by channel", "Each segment within ±20% of last year", "Reps' adjustments from the CRM, each with a reason"] },
  { key: "rules", title: "Spot a risk or opportunity", to: "rules",
    text: "Rules look for a reason to act now: a sales area in a steady decline, a competitor gaining, a doctor going quiet or ready for the next step. Each raises a trigger with a one-line reason.",
    how: ["Rolling 3-month trends, confirmed over months", "Written and tested by marketers in the rule studio", "Every trigger carries the rule that raised it"] },
  { key: "checks", title: "Check what is allowed", to: "week",
    text: "Every candidate touch is checked against consent, contact limits, content expiry and eligibility before it can go anywhere.",
    how: ["Allowed, delayed or blocked, with the reason", "Market rules such as German double opt-in", "Planned touches follow the same compliance rules"] },
  { key: "rank", title: "Move touches within the plan", to: "week",
    text: "Planned touches and the new reasons to act are scored on the same scale. Where a risk or opportunity is worth clearly more, it takes the slot of the weakest planned touch of the same rep, on the same channel.",
    how: ["Chance of response × value − cost of the touch", "At most 20% of planned touches a quarter, paced weekly", "Never adds touches: same total, same spend"] },
  { key: "deliver", title: "Deliver the week", to: "delivery",
    text: "Reps get their plan plus the engine's changes as suggestions in their CRM, with a short talk track; the agency gets its email file. A rep can decline a change and the planned touch goes ahead.",
    how: ["Veeva CRM suggestions for the changes only", "Weekly talk track per rep", "In this demo nothing is actually sent"] },
  { key: "learn", title: "Learn and re-plan", to: "feedback",
    text: "Responses, acceptances and dismissal reasons feed next week's signals, and next quarter's segmentation and plan start from what this quarter showed.",
    how: ["Acceptance and dismissal reasons by rule", "Rule changes proposed for a marketer to approve", "Next quarter's plan uses this quarter's responses"] },
];

const fade = (i = 0) => ({ initial: { opacity: 0, y: 14 }, animate: { opacity: 1, y: 0 }, transition: { delay: 0.25 + i * 0.08, duration: 0.5, ease: [0.16, 1, 0.3, 1] } });

export function StageVisual({ index: shown, week, readiness, feedback, planData }) {
  const h = week?.headline;
  if (shown === 1) return <PlanVisual p={planData} />;
  const index = shown > 1 ? shown - 1 : shown;
  const loading = <p className="text-sm text-[var(--muted)]">Asking the engine for live numbers…</p>;

  if (index === 0) {
    if (!readiness) return loading;
    const hcps = readiness.headline.reduce((a, x) => a + x.healthcare_professionals, 0);
    const orgs = readiness.headline.reduce((a, x) => a + x.organisations, 0);
    return (
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-3">
          <Big i={0} value={num(hcps)} label="doctors and other healthcare professionals" />
          <Big i={1} value={num(orgs)} label="practices, hospitals, units and pharmacies" />
          <Big i={2} value={`${readiness.history_weeks}`} label="weeks of history" />
          <Big i={3} value={`${readiness.headline.length}`} label="markets: Germany and the UK" />
        </div>
        <motion.div {...fade(4)}>
          <div className="mb-2 text-sm text-[var(--ink-2)]">Doctors who allow email, by market</div>
          <Meter rows={readiness.consent.map((c) => ({ label: c.market, value: c.email_pct, text: pct(c.email_pct) }))} max={100} />
        </motion.div>
      </div>
    );
  }

  if (!week) return loading;

  if (index === 1) {
    const top = [...week.triggers].sort((a, b) => b.triggers - a.triggers).slice(0, 3);
    return (
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-3">
          <Big i={0} value={num(h["triggers raised"])} label="triggers raised in week 1" />
          <Big i={1} value={num(h["physicians and accounts with a trigger"])} label="doctors and accounts with a reason to act" />
        </div>
        <motion.div {...fade(2)} className="text-sm text-[var(--ink-2)]">The busiest rules this week, with a real reason each gave:</motion.div>
        {top.map((t, i) => (
          <motion.div key={t.rule_id} {...fade(3 + i)} className="glass rounded-xl p-3">
            <div className="flex items-center justify-between text-sm"><span className="font-medium text-[var(--accent)]">{t.rule_id}</span><span className="tabular text-[var(--ink-2)]">{num(t.triggers)} triggers</span></div>
            <div className="mt-1 text-sm text-[var(--ink)]">“{t.example}”</div>
          </motion.div>
        ))}
      </div>
    );
  }

  if (index === 2) {
    const total = h["candidate actions"];
    const segs = [
      { label: "Allowed", value: h.allowed, color: "var(--good)" },
      { label: "Delayed", value: h.delayed, color: "var(--warn)" },
      { label: "Blocked", value: h.blocked, color: "var(--bad)" },
    ];
    return (
      <div className="space-y-5">
        <Big i={0} value={num(total)} label="candidate actions checked" />
        <motion.div {...fade(1)}>
          <div className="flex h-4 overflow-hidden rounded-full bg-[var(--chip)]">
            {segs.map((s, i) => (
              <motion.div key={s.label} initial={{ width: 0 }} animate={{ width: `${(100 * s.value) / total}%` }}
                transition={{ delay: 0.4 + i * 0.15, duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
                style={{ background: s.color, boxShadow: `0 0 14px ${s.color}` }} />
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-4 text-sm">
            {segs.map((s) => <span key={s.label} className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: s.color }} />{s.label} <strong className="tabular">{num(s.value)}</strong></span>)}
          </div>
        </motion.div>
        <motion.div {...fade(2)} className="text-sm text-[var(--ink-2)]">What held most back:</motion.div>
        {week.constraints.slice(0, 3).map((c, i) => (
          <motion.div key={c.constraint_id + c.verdict} {...fade(3 + i)} className="flex items-start justify-between gap-3 border-b border-[var(--line)] pb-2 text-sm last:border-0">
            <span>{c.example}</span><span className="tabular shrink-0 text-[var(--ink-2)]">{num(c.candidates)}</span>
          </motion.div>
        ))}
      </div>
    );
  }

  if (index === 3) {
    return (
      <div className="space-y-5">
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
          <Big i={0} value={num(h["planned touches due"])} label="planned touches due this week" />
          <motion.span {...fade(1)} className="text-2xl text-[var(--accent-2)]">→</motion.span>
          <Big i={2} value={num(h["touches moved by the engine"])} label="moved to a risk or opportunity" tone="good" />
        </div>
        <motion.div {...fade(0)} className="flex flex-wrap items-center gap-2 text-sm">
          {["Chance of response", "×", "Value of response", "−", "Cost of touch", "=", "Expected return"].map((t, i) => (
            <motion.span key={i} initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.3 + i * 0.08 }}
              className={["×", "−", "="].includes(t) ? "text-lg text-[var(--muted)]" : `rounded-lg px-2.5 py-1 ${i === 6 ? "bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]" : "glass"}`}>{t}</motion.span>
          ))}
        </motion.div>
        <motion.p {...fade(3)} className="text-sm text-[var(--ink-2)]">A move happens only when the new reason beats the weakest planned touch of the same rep on the same channel by a clear margin; the total stays {num(h["actions sent"])} touches.</motion.p>
        <div className="grid grid-cols-2 gap-3">
          <Big i={4} value={eur(h["total expected return (EUR)"])} label="expected return this week" tone="good" />
          <Big i={5} value={eur(h["total cost of touches sent (EUR)"])} label="cost of the week, as planned" />
        </div>

      </div>
    );
  }

  if (index === 4) {
    const rows = [...week.by_channel].sort((a, b) => b.sent - a.sent);
    return (
      <div className="space-y-5">
        <Big i={0} value={num(h["actions sent"])} label={`actions across ${rows.length} channels in week 1`} />
        <motion.div {...fade(1)}>
          <Meter rows={rows.map((c) => ({ label: words(c.final_channel), value: c.sent, text: num(c.sent) }))} />
        </motion.div>
        <div className="grid grid-cols-3 gap-2">
          {["CRM suggestions for reps", "Key account manager briefs", "Agency files"].map((t, i) => (
            <motion.div key={t} {...fade(2 + i)} className="glass rounded-xl p-3 text-center text-xs text-[var(--ink-2)]">
              <div className="mb-1 text-lg text-[var(--accent)]" aria-hidden>{["▣", "▤", "▦"][i]}</div>{t}
            </motion.div>
          ))}
        </div>
      </div>
    );
  }

  // index 5: learning from responses
  if (!feedback?.weeks) {
    return (
      <div className="space-y-4">
        <motion.p {...fade(0)} className="text-[var(--ink-2)]">
          The pilot has not run yet, so there are no responses to learn from. Run it to week 8 on the Feedback screen and this
          view fills with live acceptance, dismissal reasons and the rule changes the engine proposes.
        </motion.p>
        {["Suggestion goes to the rep", "Rep accepts or dismisses, and says why", "Doctor responds or not", "Next week's data includes all of it"].map((t, i) => (
          <motion.div key={t} {...fade(1 + i)} className="glass flex items-center gap-3 rounded-xl p-3 text-sm">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[var(--accent)]">{i + 1}</span>{t}
          </motion.div>
        ))}
      </div>
    );
  }
  const tot = feedback.by_week.reduce((a, w) => a + w.suggestions, 0);
  const acc = feedback.by_week.reduce((a, w) => a + w.accepted, 0);
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3">
        <Big i={0} value={pct((100 * acc) / Math.max(tot, 1), 0)} label={`of ${num(tot)} suggestions accepted over ${feedback.weeks} weeks`} tone="good" />
        <Big i={1} value={num(feedback.proposals.length)} label="rule changes proposed by the engine" />
      </div>
      <motion.div {...fade(2)}>
        <div className="mb-2 text-sm text-[var(--ink-2)]">Acceptance week by week</div>
        <div className="flex h-24 items-end gap-1">
          {feedback.by_week.map((w, i) => (
            <motion.div key={i} title={`Week ${i + 1}: ${pct(w.acceptance_pct, 0)}`} className="flex-1 rounded-t bg-gradient-to-t from-[var(--accent)]/30 to-[var(--accent)]"
              initial={{ height: 0 }} animate={{ height: `${w.acceptance_pct}%` }} transition={{ delay: 0.4 + i * 0.03, duration: 0.6 }} />
          ))}
        </div>
      </motion.div>
      <motion.div {...fade(3)}>
        <div className="mb-2 text-sm text-[var(--ink-2)]">Why reps dismissed suggestions</div>
        <Meter rows={feedback.dismiss_reasons.slice(0, 4).map((d) => ({ label: words(d.reason), value: d.count, text: num(d.count) }))} color="var(--series-2)" />
      </motion.div>
    </div>
  );
}

function Big({ value, label, i = 0, tone }) {
  return (
    <motion.div {...fade(i)} className="glass rounded-xl p-3">
      <div className={`display tabular text-2xl font-semibold md:text-3xl ${tone === "good" ? "text-[var(--good-ink)]" : "text-gradient"}`}><CountUp value={value} /></div>
      <div className="mt-0.5 text-xs text-[var(--ink-2)]">{label}</div>
    </motion.div>
  );
}

function Meter({ rows, max, color = "var(--accent)" }) {
  const top = max ?? Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="space-y-1.5">
      {rows.map((r, i) => (
        <div key={r.label} className="grid grid-cols-[minmax(6rem,11rem)_1fr_auto] items-center gap-3 text-sm">
          <span className="text-[13px] leading-tight text-[var(--ink-2)]">{r.label}</span>
          <div className="h-2 overflow-hidden rounded-full bg-[var(--chip)]">
            <motion.div className="h-full rounded-full" style={{ background: color, boxShadow: `0 0 10px ${color}` }}
              initial={{ width: 0 }} animate={{ width: `${(100 * r.value) / top}%` }} transition={{ delay: 0.5 + i * 0.08, duration: 0.8, ease: [0.16, 1, 0.3, 1] }} />
          </div>
          <span className="tabular w-14 text-right">{r.text}</span>
        </div>
      ))}
    </div>
  );
}

function PlanVisual({ p }) {
  if (!p) return <p className="text-sm text-[var(--muted)]">Building the quarter's plan…</p>;
  const bands = ["high", "medium", "low"], adopt = ["early", "building", "established"];
  const max = Math.max(...p.grid.map((g) => g.physicians), 1);
  const ly = p.by_channel.reduce((a, r) => a + r.cost_last_year_eur, 0), rec = p.by_channel.reduce((a, r) => a + r.cost_recommended_eur, 0);
  return (
    <div className="space-y-5">
      <motion.div {...fade(0)} className="grid grid-cols-[4.5rem_repeat(3,1fr)] gap-1 text-xs">
        <div />{adopt.map((a) => <div key={a} className="text-center uppercase tracking-wider text-[var(--muted)]">{a}</div>)}
        {bands.map((b) => [<div key={b} className="flex items-center uppercase tracking-wider text-[var(--muted)]">{b}</div>,
          ...adopt.map((a) => { const g = p.grid.find((x) => x.potential_band === b && x.adoption_band === a) || { physicians: 0 };
            return <div key={b + a} className="rounded-lg p-2 text-center" style={{ background: `rgba(106,109,255,${0.08 + 0.5 * g.physicians / max})` }}><span className="display tabular text-base font-bold">{num(g.physicians)}</span></div>; })])}
      </motion.div>
      <div className="grid grid-cols-2 gap-3">
        <Big i={1} value={eur(ly)} label="last year, one quarter" />
        <Big i={2} value={eur(rec)} label="recommended: same budget, new split" tone="good" />
      </div>
      <motion.p {...fade(3)} className="text-sm text-[var(--ink-2)]">{num(p.moved)} physicians changed band from today's tiers, each with a reason; reps made {num(p.rep_inputs.length)} adjustments.</motion.p>
    </div>
  );
}
