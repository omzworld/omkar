// Animated pieces for the Feedback and Results screens: the pilot console, a ring gauge, the feedback loop,
// the return dial and the test-versus-control race chart.
import { useEffect, useState } from "react";
import { animate, motion, useMotionValue, useTransform } from "motion/react";
import { num } from "./api";
import { CountUp } from "./fx.jsx";

const EASE = [0.16, 1, 0.3, 1];

// Pilot console: big week counter, a 26-week timeline that lights up as weeks complete, and the run buttons.
export function PilotConsole({ pilot, actions, milestones = [8, 26], note }) {
  const total = pilot?.pilot_weeks ?? 26;
  const running = pilot?.running;
  const done = running ? pilot.week : pilot?.completed_weeks ?? 0;
  const target = running ? pilot.target : null;
  return (
    <div className="glass relative overflow-hidden rounded-2xl p-5">
      {running && <motion.div aria-hidden className="absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-[rgba(106,109,255,0.10)] to-transparent"
        animate={{ x: ["-100%", "300%"] }} transition={{ duration: 2.2, repeat: Infinity, ease: "linear" }} />}
      <div className="relative flex flex-wrap items-center gap-6">
        <div className="flex items-center gap-4">
          <Ring value={done} max={total} size={84} stroke={7} pulse={running}>
            <div className="display tabular text-2xl font-semibold leading-none">{done}</div>
            <div className="text-[10px] text-[var(--muted)]">of {total}</div>
          </Ring>
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--accent-2)]">{running ? "Pilot running" : "Pilot weeks run"}</div>
            <div className="display mt-1 text-lg font-semibold">
              {running ? `Simulating week ${Math.min(done + 1, target)} of ${target}…` : done === 0 ? "Ready to start" : `${done} weeks complete`}
            </div>
            <div className="mt-0.5 text-sm text-[var(--ink-2)]">{note}</div>
          </div>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">{actions}</div>
      </div>
      <div className="relative mt-5">
        <div className="flex gap-1">
          {Array.from({ length: total }, (_, i) => {
            const state = i < done ? "done" : running && i === done ? "now" : running && i < target ? "queued" : "todo";
            return (
              <motion.div key={i} className="h-2.5 flex-1 rounded-sm"
                animate={{
                  backgroundColor: state === "done" ? "#6a6dff" : state === "now" ? "#ff8f7a" : state === "queued" ? "rgba(255,143,122,0.25)" : "rgba(140,140,160,0.10)",
                  boxShadow: state === "done" ? "0 0 8px rgba(106,109,255,0.6)" : "0 0 0 rgba(0,0,0,0)",
                  opacity: state === "now" ? [1, 0.4, 1] : 1,
                }}
                transition={{ duration: state === "now" ? 1 : 0.4, repeat: state === "now" ? Infinity : 0, delay: state === "done" ? i * 0.015 : 0 }} />
            );
          })}
        </div>
        <div className="relative mt-1.5 h-4 text-[11px] text-[var(--muted)]">
          <span className="absolute left-0">Week 1</span>
          {milestones.map((m) => (
            <span key={m} className="absolute -translate-x-full whitespace-nowrap" style={{ left: `${(100 * m) / total}%` }}>
              <span className={done >= m ? "text-[var(--accent)]" : ""}>▲ week {m}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

// Circular progress ring with content in the middle.
export function Ring({ value, max = 100, size = 120, stroke = 10, color = "var(--accent)", target, pulse, children }) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const share = Math.max(0, Math.min(value / max, 1));
  const ta = target !== undefined ? (target / max) * 2 * Math.PI - Math.PI / 2 : null;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      {pulse && <span className="node-pulse absolute inset-0 rounded-full bg-[var(--accent)]/20 blur-lg" />}
      <svg width={size} height={size} className="relative -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--chip)" strokeWidth={stroke} />
        <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - share) }}
          transition={{ duration: 1.2, ease: EASE }} style={{ filter: `drop-shadow(0 0 6px ${color})` }} />
      </svg>
      {ta !== null && (
        <span className="absolute h-3 w-0.5 rounded bg-white" title={`target ${target}`}
          style={{ left: size / 2 + r * Math.cos(ta) - 1, top: size / 2 + r * Math.sin(ta) - 6, transform: `rotate(${ta + Math.PI / 2}rad)` }} />
      )}
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">{children}</div>
    </div>
  );
}

// The feedback loop: four stations on a circle with green (accepted) and red (dismissed) particles flowing round.
export function FeedbackLoop({ sent, accepted, dismissed, proposals, weeks }) {
  const S = 360, C = S / 2, R = 128;
  const pos = (deg) => ({ x: C + R * Math.cos((deg * Math.PI) / 180), y: C + R * Math.sin((deg * Math.PI) / 180) });
  const stations = [
    { deg: -90, label: "Suggestions to reps", value: num(sent), color: "#6a6dff" },
    { deg: 0, label: "Accepted", value: num(accepted), color: "#4fd1a1" },
    { deg: 90, label: "Engine learns", value: `${num(proposals)} proposal${proposals === 1 ? "" : "s"}`, color: "#ffd0a8" },
    { deg: 180, label: "Dismissed, with a reason", value: num(dismissed), color: "#ff6b6b" },
  ];
  const circle = `M ${C} ${C - R} A ${R} ${R} 0 1 1 ${C - 0.01} ${C - R}`;
  const share = accepted / Math.max(accepted + dismissed, 1);
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[22rem]">
      <svg viewBox={`0 0 ${S} ${S}`} className="absolute inset-0 h-full w-full" aria-hidden>
        <circle cx={C} cy={C} r={R} fill="none" stroke="#6a6dff" strokeOpacity="0.12" strokeWidth="14" />
        <circle cx={C} cy={C} r={R} fill="none" stroke="#6a6dff" strokeOpacity="0.55" strokeWidth="1.4" className="dash-flow" />
        {Array.from({ length: 14 }, (_, i) => {
          const ok = (i / 14) < share;
          return (
            <circle key={i} r={i % 4 === 0 ? 4 : 2.6} fill={ok ? "#4fd1a1" : "#ff6b6b"} style={{ filter: `drop-shadow(0 0 5px ${ok ? "#4fd1a1" : "#ff6b6b"})` }}>
              <animateMotion dur="9s" repeatCount="indefinite" begin={`${-i * (9 / 14)}s`} path={circle} />
            </circle>
          );
        })}
        <g className="spin-slow"><circle cx={C} cy={C} r="62" fill="none" stroke="#ff8f7a" strokeOpacity="0.4" strokeDasharray="3 9" strokeWidth="2" /></g>
        <circle cx={C} cy={C} r="50" fill="#0b0b0f" stroke="#6a6dff" strokeOpacity="0.4" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <div className="display tabular text-3xl font-semibold text-gradient"><CountUp value={`${num(weeks)}`} /></div>
        <div className="text-[11px] text-[var(--ink-2)]">weeks of<br />learning</div>
      </div>
      {stations.map((s, i) => {
        const p = pos(s.deg);
        return (
          <motion.div key={s.label} className="absolute w-28 text-center" style={{ left: `${(100 * p.x) / S}%`, top: `${(100 * p.y) / S}%`, x: "-50%", y: "-50%" }}
            initial={{ opacity: 0, scale: 0.5 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.2 + i * 0.12, type: "spring", stiffness: 200, damping: 16 }}>
            <div className="glass mx-auto rounded-xl px-2 py-1.5" style={{ borderColor: s.color, boxShadow: `0 0 22px -6px ${s.color}` }}>
              <div className="display tabular text-base font-semibold" style={{ color: s.color }}>{s.value}</div>
              <div className="text-[10px] leading-tight text-[var(--ink-2)]">{s.label}</div>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

// Half-circle dial for return on the fee: 0× to 3×, break-even at 1×.
export function ReturnDial({ value, label = "return on the fee" }) {
  const max = 3, v = Math.max(0, Math.min(value ?? 0, max));
  const W = 300, H = 170, CX = 150, CY = 155, R = 120;
  const ang = (x) => Math.PI + (x / max) * Math.PI;
  const pt = (x, r = R) => [CX + r * Math.cos(ang(x)), CY + r * Math.sin(ang(x))];
  const arc = (a, b, r = R) => { const [x1, y1] = pt(a, r), [x2, y2] = pt(b, r); return `M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`; };
  const good = (value ?? 0) >= 1;
  // The needle swings along the arc: animate the value, then work out the needle tip from it.
  const mv = useMotionValue(0);
  useEffect(() => { const c = animate(mv, v, { duration: 1.6, ease: EASE }); return () => c.stop(); }, [v, mv]);
  const nx = useTransform(mv, (x) => CX + (R - 30) * Math.cos(ang(x)));
  const ny = useTransform(mv, (x) => CY + (R - 30) * Math.sin(ang(x)));
  return (
    <div className="relative mx-auto w-full max-w-sm">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" aria-label={`${label}: ${num(value, 2)} times`}>
        <defs>
          <linearGradient id="dial" x1="0" x2="1"><stop offset="0%" stopColor="#ff6b6b" /><stop offset="33%" stopColor="#ffd0a8" /><stop offset="45%" stopColor="#4fd1a1" /><stop offset="100%" stopColor="#6a6dff" /></linearGradient>
        </defs>
        <path d={arc(0, max)} fill="none" stroke="var(--chip)" strokeWidth="16" strokeLinecap="round" />
        <motion.path d={arc(0, max)} fill="none" stroke="url(#dial)" strokeWidth="16" strokeLinecap="round" pathLength="1"
          initial={{ pathLength: 0 }} animate={{ pathLength: v / max }} transition={{ duration: 1.6, ease: EASE }} style={{ filter: "drop-shadow(0 0 8px rgba(106,109,255,0.5))" }} />
        {[0, 1, 2, 3].map((t) => {
          const [x, y] = pt(t, R - 26);
          return <text key={t} x={x} y={y + 4} textAnchor="middle" fontSize="11" fill={t === 1 ? "#e8eefc" : "var(--muted)"}>{t}×</text>;
        })}
        {(() => { const [x1, y1] = pt(1, R - 12), [x2, y2] = pt(1, R + 12); return <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#fff" strokeWidth="2" />; })()}
        <motion.line x1={CX} y1={CY} x2={nx} y2={ny} stroke="#e8eefc" strokeWidth="3" strokeLinecap="round" style={{ filter: "drop-shadow(0 0 4px #fff)" }} />
        <circle cx={CX} cy={CY} r="8" fill="#e8eefc" />
      </svg>
      <div className="-mt-2 text-center">
        <div className={`display tabular text-4xl font-semibold ${good ? "text-[var(--good-ink)]" : "text-[var(--bad)]"}`}><CountUp value={`${num(value, 2)}×`} /></div>
        <div className="text-sm text-[var(--ink-2)]">{label} · break-even at 1×</div>
      </div>
    </div>
  );
}

// Test against control over time, one axis, with the pilot months shaded and the gap between the lines filled.
export function GapChart({ data, height = 280 }) {
  const [hi, setHi] = useState(null);
  const W = 600, H = height, L = 40, R = 84, T = 16, B = 30;
  const ys = data.flatMap((d) => [d.test, d.control]);
  let lo = Math.min(...ys), top = Math.max(...ys);
  const pad = (top - lo) * 0.12 || 1; lo -= pad; top += pad;
  const px = (i) => L + (i * (W - L - R)) / Math.max(data.length - 1, 1);
  const py = (v) => T + ((top - v) * (H - T - B)) / (top - lo);
  const line = (k) => data.map((d, i) => `${i ? "L" : "M"} ${px(i)} ${py(d[k])}`).join(" ");
  const p0 = data.findIndex((d) => d.pilot);
  const pilotPts = p0 >= 0 ? data.slice(Math.max(p0 - 1, 0)).map((d, j) => ({ d, i: Math.max(p0 - 1, 0) + j })) : [];
  const gap = pilotPts.length > 1
    ? `M ${pilotPts.map(({ d, i }) => `${px(i)} ${py(d.test)}`).join(" L ")} L ${[...pilotPts].reverse().map(({ d, i }) => `${px(i)} ${py(d.control)}`).join(" L ")} Z` : null;
  const ticks = Array.from({ length: 5 }, (_, i) => lo + (i * (top - lo)) / 4);
  const last = data[data.length - 1];
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-4 text-sm text-[var(--ink-2)]">
        <span className="inline-flex items-center gap-2"><span className="h-0.5 w-5 rounded bg-[var(--accent)]" />Test: the engine</span>
        <span className="inline-flex items-center gap-2"><span className="h-0.5 w-5 rounded bg-[var(--series-2)]" />Control: today's plan</span>
        <span className="inline-flex items-center gap-2"><span className="h-3 w-5 rounded-sm bg-[rgba(79,209,161,0.25)]" />The gap: the engine's effect</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Movicol units index, test against control"
        onMouseLeave={() => setHi(null)}
        onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); const i = Math.round(((((e.clientX - r.left) / r.width) * W - L) / (W - L - R)) * (data.length - 1)); setHi(i >= 0 && i < data.length ? i : null); }}>
        {p0 >= 0 && <rect x={px(p0) - 8} y={T} width={px(data.length - 1) - px(p0) + 16} height={H - T - B} fill="rgba(255,143,122,0.07)" rx="6" />}
        {p0 >= 0 && <text x={px(p0) - 2} y={T + 12} fontSize="11" fill="#ff8f7a">Pilot</text>}
        {ticks.map((t, i) => (
          <g key={i}><line x1={L} x2={W - R} y1={py(t)} y2={py(t)} stroke="var(--line)" /><text x={L - 8} y={py(t) + 4} textAnchor="end" fontSize="12" fill="var(--muted)">{num(t)}</text></g>
        ))}
        {data.map((d, i) => (i % Math.ceil(data.length / 5) === 0 || i === data.length - 1) && <text key={i} x={px(i)} y={H - 10} textAnchor="middle" fontSize="12" fill="var(--muted)">{d.month}</text>)}
        {gap && <motion.path d={gap} fill="rgba(79,209,161,0.22)" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.4, duration: 0.8 }} />}
        {[["control", "var(--series-2)"], ["test", "var(--accent)"]].map(([k, c]) => (
          <motion.path key={k + data.length} d={line(k)} fill="none" stroke={c} strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round"
            initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.6, ease: [0.4, 0, 0.2, 1] }} style={{ filter: `drop-shadow(0 0 6px ${c})` }} />
        ))}
        <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.5 }}>
          <circle cx={px(data.length - 1)} cy={py(last.test)} r="4.5" fill="var(--accent)" />
          <circle cx={px(data.length - 1)} cy={py(last.control)} r="4.5" fill="var(--series-2)" />
          <text x={px(data.length - 1) + 10} y={py(last.test) + (last.test >= last.control ? -2 : 12)} fontSize="13" fill="var(--accent)">Test {num(last.test)}</text>
          <text x={px(data.length - 1) + 10} y={py(last.control) + (last.test >= last.control ? 12 : -2)} fontSize="13" fill="var(--series-2)">Control {num(last.control)}</text>
        </motion.g>
        {hi !== null && (
          <g>
            <line x1={px(hi)} x2={px(hi)} y1={T} y2={H - B} stroke="var(--axis)" />
            <circle cx={px(hi)} cy={py(data[hi].test)} r="5" fill="var(--accent)" stroke="#0b0b0f" strokeWidth="2" />
            <circle cx={px(hi)} cy={py(data[hi].control)} r="5" fill="var(--series-2)" stroke="#0b0b0f" strokeWidth="2" />
          </g>
        )}
      </svg>
      <div className="min-h-6 text-sm text-[var(--ink-2)]" aria-live="polite">
        {hi !== null && <span className="tabular"><strong className="text-[var(--ink)]">{data[hi].month}</strong><span className="ml-4">Test: <strong className="text-[var(--ink)]">{num(data[hi].test, 1)}</strong></span><span className="ml-4">Control: <strong className="text-[var(--ink)]">{num(data[hi].control, 1)}</strong></span><span className="ml-4">Gap: <strong className="text-[var(--ink)]">{num(data[hi].test - data[hi].control, 1)}</strong></span></span>}
      </div>
    </div>
  );
}

// A small 12-month trend line of a brick's Movicol units, shown beside a reason that mentions a brick, so the
// rep sees a trend and not a single reading. Requests from many rows are batched into one call.
const trendCache = new Map();
let trendQueue = { key: null, ids: new Set(), waiters: [] };
function fetchTrend(id, until) {
  const key = `${until || ""}|${id}`;
  if (trendCache.has(key)) return trendCache.get(key);
  const p = new Promise((resolve) => {
    if (trendQueue.key !== (until || "") && trendQueue.ids.size) flushTrends();
    trendQueue.key = until || "";
    trendQueue.ids.add(id);
    trendQueue.waiters.push({ id, resolve });
    clearTimeout(trendQueue.timer);
    trendQueue.timer = setTimeout(flushTrends, 40);
  });
  trendCache.set(key, p);
  return p;
}
function flushTrends() {
  const q = trendQueue;
  trendQueue = { key: null, ids: new Set(), waiters: [] };
  if (!q.ids.size) return;
  const params = new URLSearchParams({ ids: [...q.ids].join(",") });
  if (q.key) params.set("until", q.key);
  fetch(`/api/bricks/trend?${params}`).then((r) => r.json()).catch(() => ({}))
    .then((data) => q.waiters.forEach((w) => w.resolve(data[w.id] || [])));
}

export function BrickTrend({ brick, until, width = 96, height = 26 }) {
  const [pts, setPts] = useState(null);
  useEffect(() => { let on = true; if (brick) fetchTrend(brick, until).then((d) => on && setPts(d)); return () => { on = false; }; }, [brick, until]);
  if (!brick || !pts || pts.length < 4) return null;
  const v = pts.map((p) => p.units);
  const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
  const x = (i) => 2 + (i * (width - 4)) / (v.length - 1);
  const y = (u) => 3 + (height - 6) * (1 - (u - lo) / span);
  // Rolling 3-month line on top of the monthly points: the trend the rules act on.
  const roll = v.map((_, i) => (i >= 2 ? (v[i] + v[i - 1] + v[i - 2]) / 3 : null));
  const last3 = roll[roll.length - 1], prev3 = roll[roll.length - 4];
  const down = last3 != null && prev3 != null && last3 < prev3;
  const color = down ? "var(--bad)" : "var(--good)";
  const rollPath = roll.map((r, i) => (r == null ? null : `${x(i)},${y(r)}`)).filter(Boolean).join(" ");
  return (
    <span className="inline-flex items-center gap-1.5 align-middle" title={`Brick ${brick}, Movicol units per month: ${pts.map((p) => `${p.month} ${p.units}`).join(", ")}. Line: 3-month average.`}>
      <svg width={width} height={height} aria-label={`12-month trend for brick ${brick}`}>
        <polyline points={v.map((u, i) => `${x(i)},${y(u)}`).join(" ")} fill="none" stroke="var(--axis)" strokeWidth="1" />
        {v.map((u, i) => <circle key={i} cx={x(i)} cy={y(u)} r="1.2" fill="var(--muted)" />)}
        <polyline points={rollPath} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="text-[10px] text-[var(--muted)]">12 mo</span>
    </span>
  );
}
