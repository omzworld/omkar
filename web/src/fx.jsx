// Visual effects shared by every screen: the moving background, 3D tilt on hover, and numbers that count up.
import { useEffect, useRef, useState } from "react";
import { animate, motion, useMotionValue, useSpring, useTransform, useInView } from "motion/react";

// Fixed layers behind the app: drifting colour glows, faint stars and a perspective grid floor.
export function Backdrop() {
  return (
    <div className="backdrop" aria-hidden>
      <div className="aurora a1" />
      <div className="aurora a2" />
      <div className="aurora a3" />
      <div className="stars" />
      <div className="grid-floor" />
    </div>
  );
}

// Wraps any element so it tilts towards the mouse in 3D and lifts slightly, with a soft light spot.
export function Tilt({ children, className = "", max = 4, as = "div", ...rest }) {
  const x = useMotionValue(0.5);
  const y = useMotionValue(0.5);
  const sx = useSpring(x, { stiffness: 200, damping: 18 });
  const sy = useSpring(y, { stiffness: 200, damping: 18 });
  const rotateX = useTransform(sy, [0, 1], [max, -max]);
  const rotateY = useTransform(sx, [0, 1], [-max, max]);
  const light = useTransform([sx, sy], ([a, b]) =>
    `radial-gradient(22rem circle at ${a * 100}% ${b * 100}%, color-mix(in srgb, var(--accent) 12%, transparent), transparent 45%)`);
  const M = motion[as];
  return (
    <M
      {...rest}
      className={`relative ${className}`}
      style={{ rotateX, rotateY, transformPerspective: 900, transformStyle: "preserve-3d", ...(rest.style || {}) }}
      whileHover={{ scale: 1.01, y: -2 }}
      transition={{ type: "spring", stiffness: 260, damping: 20 }}
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        x.set((e.clientX - r.left) / r.width);
        y.set((e.clientY - r.top) / r.height);
      }}
      onMouseLeave={() => { x.set(0.5); y.set(0.5); }}
    >
      <motion.span aria-hidden className="pointer-events-none absolute inset-0 rounded-[inherit]" style={{ background: light }} />
      {children}
    </M>
  );
}

// Counts up to the first number inside a formatted string ("€146,958", "3,000", "+2.3 pts"), keeping
// the text around it and the number of decimals. Strings without a number are shown as they are.
export function CountUp({ value, duration = 1.1 }) {
  const text = value === null || value === undefined ? "–" : String(value);
  const m = text.match(/-?[\d,]*\.?\d+/);
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const [shown, setShown] = useState(m ? text.replace(m[0], fmt(0, m[0])) : text);

  useEffect(() => {
    if (!m) { setShown(text); return; }
    if (!inView) return;
    const target = parseFloat(m[0].replace(/,/g, ""));
    const ctl = animate(0, target, {
      duration, ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setShown(text.replace(m[0], fmt(v, m[0]))),
    });
    return () => ctl.stop();
  }, [text, inView]);   // eslint-disable-line react-hooks/exhaustive-deps

  return <span ref={ref}>{shown}</span>;
}

function fmt(v, original) {
  const decimals = (original.split(".")[1] || "").length;
  const grouped = original.includes(",");
  return new Intl.NumberFormat("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: grouped }).format(v);
}

// Fades and lifts its children into place the first time they scroll into view.
export function Reveal({ children, delay = 0, className = "" }) {
  return (
    <motion.div className={className} initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.7, delay, ease: [0.16, 1, 0.3, 1] }}>
      {children}
    </motion.div>
  );
}
