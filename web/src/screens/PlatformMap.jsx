// "How the platform works": the six weekly stages on a glowing loop around the engine. Click a stage to zoom
// into it (live numbers from the engine), step through with the arrows, or let the auto tour present it.
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useMotionValue, useSpring, useTransform } from "motion/react";
import { num, pct } from "../api";
import { STAGES, StageVisual } from "./StageDetail.jsx";

const TOUR_MS = 7000;

// The loop's geometry: a wide oval on big screens, a tall one when the map is narrow so labels never collide.
function makeGeo(narrow) {
  const [W, H, RX, RY] = narrow ? [1000, 1150, 330, 430] : [1000, 600, 360, 205];
  const CX = W / 2, CY = H / 2;
  // Clockwise from top left: data, rules, checks, ranking, delivery, learning, then back to data.
  const POS = STAGES.map((_, i) => {
    const a = ((-120 + i * 60) * Math.PI) / 180;
    return { x: CX + RX * Math.cos(a), y: CY + RY * Math.sin(a) };
  });
  const LOOP = `M ${CX - RX} ${CY} A ${RX} ${RY} 0 1 1 ${CX + RX} ${CY} A ${RX} ${RY} 0 1 1 ${CX - RX} ${CY}`;
  return { W, H, CX, CY, POS, LOOP, narrow };
}

export default function PlatformMap({ week, readiness, feedback, go }) {
  const box = useRef(null);
  const [width, setWidth] = useState(1000);
  const narrow = width < 760;
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    if (box.current) ro.observe(box.current);
    return () => ro.disconnect();
  }, []);
  const { W, H, CX, CY, POS, LOOP } = useMemo(() => makeGeo(narrow), [narrow]);
  const [focus, setFocus] = useState(null);       // index of the zoomed stage, or null for the whole map
  const [dir, setDir] = useState(1);              // slide direction when stepping between stages
  const [touring, setTouring] = useState(false);
  const origin = POS[focus ?? 0];

  // Gentle 3D tilt of the whole map towards the mouse.
  const mx = useMotionValue(0.5), my = useMotionValue(0.5);
  const rotateY = useTransform(useSpring(mx, { stiffness: 80, damping: 20 }), [0, 1], [-6, 6]);
  const rotateX = useTransform(useSpring(my, { stiffness: 80, damping: 20 }), [0, 1], [6, -6]);

  useEffect(() => {
    if (!touring) return;
    const t = setTimeout(() => {
      if (focus === STAGES.length - 1) { setTouring(false); setFocus(null); }
      else { setDir(1); setFocus((f) => (f === null ? 0 : f + 1)); }
    }, focus === null ? 400 : TOUR_MS);
    return () => clearTimeout(t);
  }, [touring, focus]);

  const open = (i) => { setTouring(false); setDir(i > (focus ?? -1) ? 1 : -1); setFocus(i); };
  const step = (d) => { setTouring(false); setDir(d); setFocus((f) => (f + d + STAGES.length) % STAGES.length); };
  const back = () => { setTouring(false); setFocus(null); };

  const h = week?.headline;
  const fbAcc = feedback?.weeks
    ? (100 * feedback.by_week.reduce((a, w) => a + w.accepted, 0)) / Math.max(feedback.by_week.reduce((a, w) => a + w.suggestions, 0), 1) : null;
  const hcps = readiness ? readiness.headline.reduce((a, x) => a + x.healthcare_professionals, 0) : null;
  const chips = [
    hcps !== null ? `${num(hcps)} doctors` : "…",
    h ? `${num(h["triggers raised"])} triggers` : "…",
    h ? `${num(h.delayed + h.blocked)} held back` : "…",
    h ? `${num(h["actions sent"])} sent` : "…",
    week ? `${week.by_channel.length} channels` : "…",
    fbAcc !== null ? `${pct(fbAcc, 0)} accepted` : "learns weekly",
  ];

  useEffect(() => {   // arrow keys and Escape while zoomed in
    const onKey = (e) => {
      if (focus === null) return;
      if (e.key === "ArrowRight") step(1);
      else if (e.key === "ArrowLeft") step(-1);
      else if (e.key === "Escape") back();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div ref={box} className="glass relative overflow-hidden rounded-3xl" style={{ minHeight: narrow ? Math.max(width * 1.15 + 110, 560) : 608 }}
      onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); mx.set((e.clientX - r.left) / r.width); my.set((e.clientY - r.top) / r.height); }}
      onMouseLeave={() => { mx.set(0.5); my.set(0.5); }}>

      {/* Controls along the top */}
      <div className="absolute inset-x-0 top-0 z-20 flex flex-wrap items-center justify-between gap-2 p-4 md:p-5">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--accent-2)]">
          {focus === null ? "Live platform map · week 1" : `Stage ${focus + 1} of ${STAGES.length}`}
        </div>
        <div className="flex gap-2">
          {focus !== null && (
            <button onClick={back} className="rounded-full border border-[var(--axis)] px-3 py-1.5 text-xs font-medium hover:border-[var(--muted)]">
              ⤢ Zoom out to the map
            </button>
          )}
          <button onClick={() => (touring ? setTouring(false) : (setFocus(null), setTouring(true)))}
            className="btn-primary rounded-xl px-3 py-1.5 text-xs">
            {touring ? "❚❚ Stop the tour" : "▶ Auto tour"}
          </button>
        </div>
      </div>

      {/* The whole map: zooms towards the chosen stage and fades out */}
      <motion.div className="absolute inset-0 flex items-center justify-center px-2 pb-10 pt-14"
        style={{ transformOrigin: `${(100 * origin.x) / W}% ${(100 * origin.y) / H}%`, pointerEvents: focus === null ? "auto" : "none" }}
        animate={focus === null ? { scale: 1, opacity: 1 } : { scale: 2.6, opacity: 0 }}
        transition={{ duration: 0.8, ease: [0.7, 0, 0.2, 1] }}>
        <motion.div className="relative max-h-full w-full max-w-5xl" style={{ aspectRatio: `${W} / ${H}`, rotateX, rotateY, transformPerspective: 1400 }}>
          <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 h-full w-full" aria-hidden>
            <defs>
              <radialGradient id="core" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#8a8dff" stopOpacity="0.95" />
                <stop offset="45%" stopColor="#6a6dff" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#6a6dff" stopOpacity="0" />
              </radialGradient>
              <linearGradient id="loop" x1="0" x2="1">
                <stop offset="0%" stopColor="#6a6dff" /><stop offset="50%" stopColor="#ff8f7a" /><stop offset="100%" stopColor="#6a6dff" />
              </linearGradient>
              <filter id="soft"><feGaussianBlur stdDeviation="3" /></filter>
            </defs>
            {/* The loop: a soft glow under a flowing dashed line */}
            <path d={LOOP} fill="none" stroke="url(#loop)" strokeWidth="10" opacity="0.18" filter="url(#soft)" />
            <path d={LOOP} fill="none" stroke="url(#loop)" strokeWidth="1.6" className="dash-flow" opacity="0.8" />
            {/* Spokes from the engine to each stage */}
            {POS.map((p, i) => (
              <line key={i} x1={CX} y1={CY} x2={p.x} y2={p.y} stroke="#6a6dff" strokeOpacity="0.18" strokeWidth="1" className="dash-flow" />
            ))}
            {/* Data particles travelling round the loop */}
            {Array.from({ length: 10 }, (_, i) => (
              <circle key={i} r={i % 3 === 0 ? 4 : 2.5} fill={i % 2 ? "#ff8f7a" : "#8a8dff"} style={{ filter: "drop-shadow(0 0 6px #6a6dff)" }}>
                <animateMotion dur="12s" repeatCount="indefinite" begin={`${-i * 1.2}s`} path={LOOP} />
              </circle>
            ))}
            {/* The engine at the centre: glow and counter-rotating rings */}
            <circle cx={CX} cy={CY} r="110" fill="url(#core)" className="node-pulse" style={{ transformOrigin: `${CX}px ${CY}px` }} />
            <g className="spin-slow"><circle cx={CX} cy={CY} r="78" fill="none" stroke="#6a6dff" strokeOpacity="0.5" strokeDasharray="2 10" strokeWidth="2" /></g>
            <g className="spin-slow-rev"><circle cx={CX} cy={CY} r="94" fill="none" stroke="#ff8f7a" strokeOpacity="0.45" strokeDasharray="40 14 4 14" strokeWidth="1.2" /></g>
            <circle cx={CX} cy={CY} r="58" fill="#0b0b0f" stroke="#6a6dff" strokeOpacity="0.6" />
          </svg>

          {/* Centre label */}
          <div className="pointer-events-none absolute text-center" style={{ left: `${(100 * CX) / W}%`, top: `${(100 * CY) / H}%`, transform: "translate(-50%,-50%)" }}>
            <div className="display text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--accent)] md:text-xs">Engine</div>
            <div className="display tabular text-sm font-semibold md:text-lg">{h ? num(h["actions sent"]) : "…"}</div>
            <div className="text-[10px] text-[var(--ink-2)] md:text-[11px]">actions this week</div>
          </div>

          {/* The six stages */}
          {STAGES.map((s, i) => (
            <motion.button key={s.key} onClick={() => open(i)}
              className="group absolute flex w-28 flex-col items-center text-center md:w-40"
              style={{ left: `${(100 * POS[i].x) / W}%`, top: `${(100 * POS[i].y) / H}%`, x: "-50%", y: "-50%" }}
              initial={{ opacity: 0, scale: 0.4 }} animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.15 + i * 0.1, type: "spring", stiffness: 220, damping: 18 }}
              whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.95 }}>
              <span className="relative flex h-12 w-12 items-center justify-center md:h-16 md:w-16">
                <span className="node-pulse absolute inset-0 rounded-full bg-[var(--accent)]/25 blur-md" style={{ animationDelay: `${i * 0.5}s` }} />
                <span className="relative flex h-full w-full items-center justify-center rounded-full border border-[rgba(106,109,255,0.5)] bg-[#141418] text-[var(--accent)] shadow-[0_0_24px_-4px_var(--accent)] transition group-hover:border-[var(--accent)] group-hover:bg-[#1d2056] group-hover:shadow-[0_0_36px_0_var(--accent)]">
                  <StageIcon i={i} />
                </span>
                <span className="display tabular absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--accent)] text-[10px] font-bold text-[#ffffff]">{i + 1}</span>
              </span>
              <span className="display mt-2 text-xs font-semibold leading-tight md:text-sm">{s.title}</span>
              <span className="mt-1 hidden rounded-full border border-[var(--line)] bg-black/30 px-2 py-0.5 text-[11px] text-[var(--ink-2)] transition group-hover:border-[var(--accent)] group-hover:text-[var(--accent)] sm:inline-block">{chips[i]}</span>
            </motion.button>
          ))}
        </motion.div>
        <p className="absolute inset-x-0 bottom-4 text-center text-xs text-[var(--muted)]">Click any stage to zoom in · the loop repeats every week</p>
      </motion.div>

      {/* The zoomed-in stage */}
      <AnimatePresence mode="wait" custom={dir}>
        {focus !== null && (
          <motion.div key={focus} custom={dir} className="relative z-10 px-5 pb-24 pt-16 md:px-10"
            style={{ transformOrigin: `${(100 * origin.x) / W}% ${(100 * origin.y) / H}%` }}
            variants={{
              enter: (d) => ({ opacity: 0, scale: 0.35, x: d * 0 }),
              show: { opacity: 1, scale: 1, x: 0 },
              leave: { opacity: 0, scale: 0.9 },
            }}
            initial="enter" animate="show" exit="leave"
            transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}>
            <div className="grid gap-8 lg:grid-cols-[1fr_1.15fr]">
              <div>
                <div className="flex items-center gap-3">
                  <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-[rgba(106,109,255,0.5)] bg-[#141418] text-[var(--accent)] shadow-[0_0_30px_-4px_var(--accent)]"><StageIcon i={focus} big /></span>
                  <span className="display text-sm text-[var(--muted)]">Step {focus + 1}</span>
                </div>
                <h3 className="text-gradient mt-4 text-3xl font-semibold md:text-4xl">{STAGES[focus].title}</h3>
                <p className="mt-3 max-w-xl text-[var(--ink-2)] md:text-lg">{STAGES[focus].text}</p>
                <ul className="mt-5 space-y-2">
                  {STAGES[focus].how.map((t, i) => (
                    <motion.li key={t} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 + i * 0.1 }}
                      className="flex items-center gap-2.5 text-sm"><span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] shadow-[0_0_8px_var(--accent)]" />{t}</motion.li>
                  ))}
                </ul>
                <button onClick={() => go(STAGES[focus].to)} className="btn-primary mt-7 rounded-xl px-4 py-2.5 text-sm">Open this screen →</button>
              </div>
              <div className="glass rounded-2xl p-5">
                <div className="mb-4 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">Live from the engine</div>
                <StageVisual index={focus} week={week} readiness={readiness} feedback={feedback} />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Step controls while zoomed in, with tour progress */}
      {focus !== null && (
        <div className="absolute inset-x-0 bottom-0 z-20 flex items-center justify-between gap-3 border-t border-[var(--line)] bg-[#0b0b0f]/80 px-4 py-3 backdrop-blur md:px-6">
          <button onClick={() => step(-1)} className="rounded-lg px-3 py-1.5 text-sm text-[var(--ink-2)] hover:text-[var(--accent)]">← {narrow ? "Previous" : STAGES[(focus + 5) % 6].title}</button>
          <div className="flex items-center gap-2">
            {STAGES.map((s, i) => (
              <button key={s.key} onClick={() => open(i)} aria-label={s.title}
                className={`relative h-1.5 overflow-hidden rounded-full transition-all ${i === focus ? "w-10 bg-[var(--chip)]" : "w-3 bg-[var(--line)] hover:bg-[var(--accent)]"}`}>
                {i === focus && (
                  <motion.span key={`${focus}-${touring}`} className="absolute inset-y-0 left-0 bg-[var(--accent)]"
                    initial={{ width: touring ? "0%" : "100%" }} animate={{ width: "100%" }} transition={{ duration: touring ? TOUR_MS / 1000 : 0, ease: "linear" }} />
                )}
              </button>
            ))}
          </div>
          <button onClick={() => step(1)} className="rounded-lg px-3 py-1.5 text-sm text-[var(--ink-2)] hover:text-[var(--accent)]">{narrow ? "Next" : STAGES[(focus + 1) % 6].title} →</button>
        </div>
      )}
    </div>
  );
}

// Small line icons for the six stages.
function StageIcon({ i, big }) {
  const s = big ? 26 : 22;
  const p = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round" };
  const paths = [
    <><ellipse cx="12" cy="6" rx="7" ry="3" {...p} /><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" {...p} /></>,
    <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" {...p} />,
    <><path d="M12 3 4 6v6c0 4.5 3.4 8 8 9 4.6-1 8-4.5 8-9V6l-8-3z" {...p} /><path d="m8.5 12 2.5 2.5 4.5-5" {...p} /></>,
    <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" {...p} /></>,
    <><path d="M3 11 21 3l-8 18-2-8-8-2z" {...p} /></>,
    <><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v4h-4" {...p} /></>,
  ];
  return <svg width={s} height={s} viewBox="0 0 24 24" aria-hidden>{paths[i]}</svg>;
}
