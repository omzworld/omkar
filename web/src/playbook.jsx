// Shared pieces: what an action means in practice (playbook) and the rep's simulated incentive tracker.
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { api, num, words } from "./api";
import { ladderOf } from "./ladder.js";

const ROW = "grid grid-cols-[7.5rem_1fr] gap-3 py-1.5 text-sm";

function Line({ label, children }) {
  if (!children || (Array.isArray(children) && children.length === 0)) return null;
  return (
    <div className={ROW}>
      <div className="text-xs uppercase tracking-wider text-[var(--muted)] pt-0.5">{label}</div>
      <div>{children}</div>
    </div>
  );
}

function Steps({ items, numbered }) {
  if (!items?.length) return null;
  const Tag = numbered ? "ol" : "ul";
  return <Tag className={`space-y-1 ${numbered ? "list-decimal" : "list-disc"} pl-5`}>{items.map((s) => <li key={s}>{s}</li>)}</Tag>;
}

// The playbook as a compact definition list. `compact` hides the who/what header (used inside cards).
export function Playbook({ pb, compact }) {
  if (!pb) return null;
  return (
    <div className="divide-y divide-[var(--line)]">
      {!compact && (
        <Line label="Action"><span className="font-medium capitalize">{pb.channel}</span>{pb.theme && <span className="text-[var(--ink-2)]"> · {pb.theme}</span>}
          {pb.stage && <span className="ml-2 text-xs text-[var(--muted)]">doctor is at: {ladderOf(pb.stage)}{pb.barrier ? ` · barrier: ${words(pb.barrier)}` : ""}</span>}</Line>
      )}
      <Line label="Objective">{pb.objective}</Line>
      <Line label="Sender">{pb.sender}</Line>
      <Line label="Template">{pb.template}</Line>
      <Line label="Subject">{pb.subject && <span className="font-medium">“{pb.subject}”</span>}</Line>
      <Line label="Send">{pb.send_window}</Line>
      <Line label="Show">{pb.slides?.length > 0 && <Steps items={pb.slides} numbered />}</Line>
      <Line label="Agenda">{pb.agenda?.length > 0 && <Steps items={pb.agenda} numbered />}</Line>
      <Line label="Ask">{pb.ask && <span className="italic">“{pb.ask}”</span>}</Line>
      <Line label="If they object">{pb.objection}</Line>
      <Line label="Leave behind">{pb.leave_behind}</Line>
      <Line label="Follow up">{pb.follow_up?.length > 0 && <Steps items={pb.follow_up} />}</Line>
      <Line label="Afterwards">{pb.after?.length > 0 && <Steps items={pb.after} />}</Line>
      <Line label="Quiet period">{pb.quiet_days ? `No other brand email for ${pb.quiet_days} days` : null}</Line>
    </div>
  );
}

// Simulated quarterly incentive: three measures, achievement, payout, rank and what would move it.
export function IncentiveCard({ rep, week }) {
  const [t, setT] = useState(null);
  useEffect(() => { if (rep) api(`/incentive/${rep}${week ? `?week=${week}` : ""}`).then(setT).catch(() => setT(null)); }, [rep, week]);
  if (!t || !t.measures) return null;
  const pay = t.payout_pct;
  const tone = pay >= 100 ? "var(--good-ink, #34d399)" : pay > 0 ? "var(--accent)" : "var(--bad-ink, #f87171)";
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--raised)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-wider text-[var(--muted)]">My quarter · incentive tracker</div>
          <div className="mt-0.5 text-sm text-[var(--ink-2)]">Quarter {t.quarter}, week {t.week_in_quarter} of {t.quarter_weeks} · simulated</div>
        </div>
        <div className="text-right">
          <div className="tabular text-3xl font-semibold" style={{ color: tone }}>{pay}%</div>
          <div className="text-xs text-[var(--ink-2)]">of target bonus · about €{num(t.payout_eur)} of €{num(t.target_bonus_eur)}</div>
        </div>
      </div>
      <div className="mt-4 space-y-3">
        {t.measures.map((m, i) => (
          <div key={m.key}>
            <div className="flex justify-between gap-2 text-sm">
              <span>{m.label} <span className="text-xs text-[var(--muted)]">· weight {Math.round(m.weight * 100)}%</span></span>
              <span className="tabular font-medium">{m.achievement}%</span>
            </div>
            <div className="relative mt-1 h-2 rounded-full bg-[var(--chip)]">
              <motion.div className="h-2 rounded-full" style={{ background: m.achievement >= 100 ? "var(--good-ink, #34d399)" : "var(--accent)" }}
                initial={{ width: 0 }} animate={{ width: `${Math.min(m.achievement, 150) / 1.5}%` }} transition={{ delay: i * 0.08, duration: 0.7 }} />
              <div className="absolute top-[-3px] h-[14px] w-px bg-[var(--ink-2)]" style={{ left: `${100 / 1.5}%` }} title="target" />
            </div>
            <div className="mt-0.5 text-xs text-[var(--ink-2)]">{m.actual}</div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-[var(--line)] pt-3 text-sm">
        <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 font-medium">#{t.rank} of {t.of} reps in {t.market}</span>
        <span className="text-[var(--ink-2)]">Overall achievement {t.achievement}% · nothing paid below {t.curve.threshold_pct}%, capped at {t.curve.payout_at_cap_pct}%</span>
      </div>
      {t.hints.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">{t.hints.map((h) => <li key={h} className="flex gap-2"><span className="text-[var(--accent)]">↗</span>{h}</li>)}</ul>
      )}
      <p className="mt-3 text-[11px] text-[var(--muted)]">{t.note}</p>
    </div>
  );
}
