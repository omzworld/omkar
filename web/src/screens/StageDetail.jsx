// The zoomed-in view of one platform stage: a plain explanation on the left, live engine numbers on the right.
import { motion } from "motion/react";
import { eur, num, pct, words } from "../api";
import { CountUp } from "../fx.jsx";

// The six stages, in the order the engine runs them each week. `to` is the screen that shows the stage in full.
export const STAGES = [
  { key: "data", title: "Read the data", to: "readiness",
    text: "Every week starts from what is known about each doctor and account: calls, emails, events, sales by area and consent to be contacted.",
    how: ["One row per doctor or account, rebuilt every week", "24 months of history to learn from", "Consent recorded per channel and market"] },
  { key: "rules", title: "Spot a reason to act", to: "rules",
    text: "Rules look for a risk or an opportunity, such as sales falling in an area or a doctor not seen for months, and raise a trigger with a one-line reason.",
    how: ["Rules are written and tested by marketers", "Every trigger carries the rule that raised it", "Discovery adds what the rules missed, capped at 10%"] },
  { key: "checks", title: "Check what is allowed", to: "week",
    text: "Before anything is planned, every candidate action is checked against consent, contact limits, content expiry and rep capacity.",
    how: ["Allowed, delayed or blocked", "Each verdict names the check that made it", "Market rules, such as German double opt-in, are enforced"] },
  { key: "rank", title: "Rank by expected return", to: "week",
    text: "What is allowed is scored, the best action per doctor is kept, and rep and agency time is filled with the highest return first.",
    how: ["Chance of response × value − cost of the touch", "A cheaper channel is used when reps are full", "Everything not sent says why"] },
  { key: "deliver", title: "Deliver the plan", to: "delivery",
    text: "The plan becomes suggestions in the reps' CRM, briefs for key account managers, files for the agency and a weekly talk track for each rep.",
    how: ["Veeva CRM suggestion payloads", "Key account manager briefs per unit", "In this demo nothing is actually sent"] },
  { key: "learn", title: "Learn from responses", to: "feedback",
    text: "Reps accept or dismiss each suggestion and doctors respond or not. That feeds next week's data, and rules the field keeps rejecting are flagged for change.",
    how: ["Acceptance and dismissal reasons by rule", "Proposed rule changes for a marketer to approve", "Next week starts smarter than this one"] },
];

const fade = (i = 0) => ({ initial: { opacity: 0, y: 14 }, animate: { opacity: 1, y: 0 }, transition: { delay: 0.25 + i * 0.08, duration: 0.5, ease: [0.16, 1, 0.3, 1] } });

export function StageVisual({ index, week, readiness, feedback }) {
  const h = week?.headline;
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
        <motion.div {...fade(0)} className="flex flex-wrap items-center gap-2 text-sm">
          {["Chance of response", "×", "Value of response", "−", "Cost of touch", "=", "Expected return"].map((t, i) => (
            <motion.span key={i} initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.3 + i * 0.08 }}
              className={["×", "−", "="].includes(t) ? "text-lg text-[var(--muted)]" : `rounded-lg px-2.5 py-1 ${i === 6 ? "bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]" : "glass"}`}>{t}</motion.span>
          ))}
        </motion.div>
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
          <Big i={1} value={num(h.allowed)} label="allowed actions" />
          <motion.span {...fade(2)} className="text-2xl text-[var(--accent)]">→</motion.span>
          <Big i={3} value={num(h["actions sent"])} label="sent: the best per doctor that fit capacity" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Big i={4} value={eur(h["total expected return (EUR)"])} label="expected return this week" tone="good" />
          <Big i={5} value={eur(h["total cost of touches sent (EUR)"])} label="cost of the touches sent" />
        </div>
        <motion.div {...fade(6)}>
          <div className="mb-2 text-sm text-[var(--ink-2)]">Allowed but not sent, and why</div>
          <Meter rows={week.not_sent.map((n) => ({ label: n.reason, value: n.candidates, text: num(n.candidates) }))} />
        </motion.div>
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
