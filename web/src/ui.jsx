// Reusable building blocks: cards, stat tiles, tables, buttons, and two small SVG charts.
import { useState } from "react";
import { motion } from "motion/react";
import { num } from "./api";
import { CountUp, Tilt } from "./fx.jsx";

export function Card({ title, subtitle, children, actions, className = "" }) {
  return (
    <motion.section initial={{ opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className={`glass glow-hover min-w-0 rounded-2xl p-5 ${className}`}>
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-base font-semibold">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-[var(--ink-2)]">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </motion.section>
  );
}

export function Stat({ label, value, note, tone }) {
  const color = tone === "good" ? "text-[var(--good-ink)]" : tone === "bad" ? "text-[var(--bad)]" : "text-[var(--ink)]";
  const bar = tone === "good" ? "var(--good)" : tone === "bad" ? "var(--bad)" : "var(--accent)";
  return (
    <Tilt max={6} className="glass glow-hover overflow-hidden rounded-2xl p-4">
      <span aria-hidden className="absolute inset-x-0 top-0 h-px" style={{ background: `linear-gradient(90deg, transparent, ${bar}, transparent)` }} />
      <div className="text-sm text-[var(--ink-2)]">{label}</div>
      <div className={`display tabular mt-1 text-2xl font-semibold ${color}`}>{typeof value === "string" || typeof value === "number" ? <CountUp value={value} /> : value}</div>
      {note && <div className="mt-1 text-xs text-[var(--muted)]">{note}</div>}
    </Tilt>
  );
}

export function Button({ children, onClick, disabled, kind = "primary", type = "button" }) {
  const styles = kind === "primary"
    ? "btn-primary font-semibold"
    : "border border-[var(--line)] bg-[var(--chip)] text-[var(--ink)] hover:border-[var(--accent)] hover:text-[var(--accent)]";
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`rounded-xl px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles}`}>
      {children}
    </button>
  );
}

export function Badge({ children, tone = "neutral" }) {
  const t = {
    neutral: "bg-[var(--chip)] text-[var(--ink-2)]",
    good: "bg-[var(--chip)] text-[var(--good-ink)]",
    bad: "bg-[var(--chip)] text-[var(--bad)]",
    accent: "bg-[var(--chip)] text-[var(--accent)]",
  }[tone];
  return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${t}`}>{children}</span>;
}

export function Status({ passed }) {
  return passed
    ? <Badge tone="good"><span aria-hidden>✓</span> Met</Badge>
    : <Badge tone="bad"><span aria-hidden>✕</span> Not met</Badge>;
}

export function Table({ columns, rows, empty = "Nothing to show.", maxHeight }) {
  if (!rows || rows.length === 0) return <p className="text-sm text-[var(--muted)]">{empty}</p>;
  return (
    <div className="overflow-auto rounded-xl border border-[var(--line)] bg-black/10" style={maxHeight ? { maxHeight } : undefined}>
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 bg-[var(--raised)]">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={`border-b border-[var(--line)] px-3 py-2 text-left font-medium text-[var(--ink-2)] ${c.num ? "text-right" : ""}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-[var(--line)] transition-colors last:border-0 hover:bg-[var(--accent-soft)]">
              {columns.map((c) => (
                <td key={c.key} className={`px-3 py-2 align-top ${c.num ? "tabular whitespace-nowrap text-right" : ""} ${c.wide ? "min-w-[18rem]" : ""}`}>
                  {c.render ? c.render(r) : r[c.key] ?? "–"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Field({ label, children, hint }) {
  return (
    <label className="block text-sm">
      <span className="text-[var(--ink-2)]">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-1 block text-xs text-[var(--muted)]">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-lg border border-[var(--line)] bg-[var(--raised)] px-3 py-2 text-sm text-[var(--ink)] outline-none focus:border-[var(--accent)]";

export function Message({ children, tone = "neutral" }) {
  const border = tone === "bad" ? "border-[var(--bad)]" : tone === "good" ? "border-[var(--good)]" : "border-[var(--line)]";
  return <div className={`glass rounded-xl border ${border} px-4 py-3 text-sm`}>{children}</div>;
}

// ------------------------------------------------------------------------------------- charts

// Horizontal bars, one series. Thin bars, rounded data end, value labels, hover tooltip.
export function Bars({ data, label, value, format = (v) => num(v), color = "var(--accent)", unit = "" }) {
  const [hover, setHover] = useState(null);
  const max = Math.max(...data.map((d) => d[value]), 0) || 1;
  return (
    <div className="space-y-1.5" role="list">
      {data.map((d, i) => (
        <div key={i} role="listitem" className="grid grid-cols-[minmax(8rem,14rem)_1fr_auto] items-center gap-3 text-sm"
          onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
          <span className="truncate text-[var(--ink-2)]" title={d[label]}>{d[label]}</span>
          <div className="relative h-5">
            <div className="bar-grow absolute inset-y-1 left-0 rounded-r-[4px] transition-opacity"
              style={{ width: `${Math.max((100 * d[value]) / max, 0.5)}%`, background: `linear-gradient(90deg, color-mix(in srgb, ${color} 35%, transparent), ${color})`,
                boxShadow: `0 0 12px color-mix(in srgb, ${color} 45%, transparent)`, opacity: hover === null || hover === i ? 1 : 0.55, animationDelay: `${i * 40}ms` }} />
          </div>
          <span className="tabular w-20 text-right text-[var(--ink)]">{format(d[value])}{unit}</span>
        </div>
      ))}
    </div>
  );
}

// Line chart for up to a few series on one axis, with a crosshair tooltip, a legend and direct end labels.
export function Lines({ data, x, series, height = 260, yLabel, shadeFrom }) {
  const [hi, setHi] = useState(null);
  const W = 720, H = height, L = 44, R = 92, T = 12, B = 30;
  const ys = data.flatMap((d) => series.map((s) => d[s.key])).filter((v) => v !== null && v !== undefined);
  let lo = Math.min(...ys), hiY = Math.max(...ys);
  const pad = (hiY - lo) * 0.1 || 1;
  lo -= pad; hiY += pad;
  const px = (i) => L + (i * (W - L - R)) / Math.max(data.length - 1, 1);
  const py = (v) => T + ((hiY - v) * (H - T - B)) / (hiY - lo);
  const ticks = Array.from({ length: 5 }, (_, i) => lo + (i * (hiY - lo)) / 4);
  const shadeIdx = shadeFrom ? data.findIndex(shadeFrom) : -1;
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-4 text-sm text-[var(--ink-2)]">
        {series.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-2">
            <span className="inline-block h-0.5 w-5 rounded" style={{ background: s.color }} />{s.label}
          </span>
        ))}
        {shadeIdx >= 0 && <span className="inline-flex items-center gap-2"><span className="inline-block h-3 w-5 rounded-sm bg-[var(--chip)]" />Pilot period</span>}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={yLabel}
        onMouseLeave={() => setHi(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const xPos = ((e.clientX - r.left) / r.width) * W;
          const i = Math.round(((xPos - L) / (W - L - R)) * (data.length - 1));
          setHi(i >= 0 && i < data.length ? i : null);
        }}>
        {shadeIdx >= 0 && <rect x={px(shadeIdx) - 6} y={T} width={px(data.length - 1) - px(shadeIdx) + 12} height={H - T - B} fill="var(--chip)" />}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={L} x2={W - R} y1={py(t)} y2={py(t)} stroke="var(--line)" strokeWidth="1" />
            <text x={L - 8} y={py(t) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">{num(t)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const step = Math.ceil(data.length / 8);
          const show = i % step === 0 || (i === data.length - 1 && (data.length - 1) % step >= step / 2);
          return show && <text key={i} x={px(i)} y={H - 10} textAnchor="middle" fontSize="11" fill="var(--muted)">{d[x]}</text>;
        })}
        {(() => {
          // Direct end labels, nudged apart so they never overlap.
          const ends = series.map((s) => ({ s, y: py(data[data.length - 1][s.key]) + 4 })).sort((a, b) => a.y - b.y);
          for (let i = 1; i < ends.length; i++) ends[i].y = Math.max(ends[i].y, ends[i - 1].y + 15);
          return series.map((s) => {
            const pts = data.map((d, i) => [px(i), py(d[s.key])]);
            const label = ends.find((e) => e.s === s);
            return (
              <g key={s.key}>
                <polyline className="line-draw" pathLength="1" points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke={s.color} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round"
                  style={{ filter: `drop-shadow(0 0 6px ${s.color})` }} />
                <text x={pts[pts.length - 1][0] + 10} y={label.y} fontSize="12" fill="var(--ink-2)">{s.label}</text>
              </g>
            );
          });
        })()}
        {hi !== null && (
          <g>
            <line x1={px(hi)} x2={px(hi)} y1={T} y2={H - B} stroke="var(--axis)" strokeWidth="1" />
            {series.map((s) => (
              <circle key={s.key} cx={px(hi)} cy={py(data[hi][s.key])} r="4.5" fill={s.color} stroke="var(--surface)" strokeWidth="2" />
            ))}
          </g>
        )}
      </svg>
      <div className="min-h-6 text-sm text-[var(--ink-2)]" aria-live="polite">
        {hi !== null && (
          <span className="tabular">
            <strong className="text-[var(--ink)]">{data[hi][x]}</strong>
            {series.map((s) => <span key={s.key} className="ml-4">{s.label}: <strong className="text-[var(--ink)]">{num(data[hi][s.key], 1)}</strong></span>)}
          </span>
        )}
      </div>
    </div>
  );
}
