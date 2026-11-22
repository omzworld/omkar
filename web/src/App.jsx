// The app shell: a sidebar with home and the six demo scenes, the pilot status, and the selected screen.
import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { api } from "./api";
import { Backdrop } from "./fx.jsx";
import { GenpactLogo, OmnisenseMark } from "./brand.jsx";
import Home from "./screens/Home.jsx";
import DataCenter from "./screens/DataCenter.jsx";
import SegmentPlan from "./screens/SegmentPlan.jsx";
import Stories from "./screens/Stories.jsx";
import MyTerritory from "./screens/MyTerritory.jsx";
import Readiness from "./screens/Readiness.jsx";
import RuleStudio from "./screens/RuleStudio.jsx";
import WeeklyRun from "./screens/WeeklyRun.jsx";
import Delivery from "./screens/Delivery.jsx";
import Feedback from "./screens/Feedback.jsx";
import Results from "./screens/Results.jsx";

const SCREENS = [
  { id: "home", label: "Home", hint: "What this tool does", icon: "◈", C: Home },
  { id: "data", label: "Data control center", hint: "Sources, data model, live checks", icon: "◫", C: DataCenter },
  { id: "readiness", n: 1, label: "Data readiness", hint: "What data we have", icon: "▤", C: Readiness },
  { id: "plan", n: 2, label: "Segment & plan", hint: "Quarterly segments and budget", icon: "▦", C: SegmentPlan },
  { id: "rules", n: 3, label: "Rule studio", hint: "Risk and opportunity signals", icon: "⚙", C: RuleStudio },
  { id: "week", n: 4, label: "Weekly run", hint: "The plan, and what moves", icon: "▶", C: WeeklyRun },
  { id: "territory", n: 5, label: "My territory", hint: "The rep's one page this week", icon: "☰", C: MyTerritory },
  { id: "delivery", n: 6, label: "Delivery", hint: "What reps and the agency receive", icon: "➤", C: Delivery },
  { id: "feedback", n: 7, label: "Feedback", hint: "What reps accepted, what to change", icon: "↻", C: Feedback },
  { id: "results", n: 8, label: "Results and return", hint: "Same spend, plan attainment, lift", icon: "◔", C: Results },
  { id: "stories", n: 9, label: "Doctor and rep view", hint: "One doctor, one rep, side by side", icon: "◉", C: Stories },
];

export default function App() {
  const [screen, setScreen] = useState(() => window.location.hash.slice(1) || "home");
  const [pilot, setPilot] = useState(null);
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || "dark");
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("omnisense-theme", theme); } catch { /* private window: theme just isn't remembered */ }
  }, [theme]);

  const refresh = useCallback(() => api("/pilot/status").then(setPilot).catch(() => setPilot(null)), []);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (!pilot?.running) return;
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [pilot?.running, refresh]);
  useEffect(() => { window.location.hash = screen; }, [screen]);
  useEffect(() => {   // the browser's back and forward buttons, and typed addresses, switch screens too
    const onHash = () => setScreen(window.location.hash.slice(1) || "home");
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const runPilot = async (weeks, fresh = false) => {
    try { setPilot(await api("/pilot/run", { weeks, fresh })); } catch (e) { alert(e.message); }
    refresh();
  };
  const current = SCREENS.find((s) => s.id === screen) || SCREENS[0];
  const Current = current.C;
  const go = (id) => { setScreen(id); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const done = pilot?.completed_weeks ?? 0;
  const total = pilot?.pilot_weeks ?? 26;

  return (
    <MotionConfig reducedMotion="user">
      <Backdrop />
      <div className="relative z-10 min-h-screen md:grid md:grid-cols-[17rem_1fr]">
        <aside className="glass border-0 border-b border-[var(--line)] p-4 md:sticky md:top-0 md:h-screen md:border-b-0 md:border-r">
          <div className="mb-6 flex items-start justify-between gap-2">
            <button onClick={() => go("home")} className="group flex items-center gap-3 text-left" aria-label="Omnisense home">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--chip)] text-[var(--ink)] ring-1 ring-[var(--line)] transition group-hover:rotate-12">
                <OmnisenseMark className="h-7 w-7" />
              </span>
              <span>
                <span className="display block text-lg font-bold leading-tight tracking-tight">Omnisense</span>
                <span className="flex items-center gap-1.5 text-[11px] text-[var(--muted)]">by <GenpactLogo className="h-5 w-auto text-[var(--ink)]" /></span>
              </span>
            </button>
            <ThemeSwitch theme={theme} setTheme={setTheme} />
          </div>
          <nav className="grid grid-cols-2 gap-1 md:grid-cols-1">
            {SCREENS.map((s, i) => {
              const active = screen === s.id;
              return (
                <button key={s.id} onClick={() => go(s.id)}
                  className={`relative rounded-xl px-3 py-2 text-left text-sm transition ${active ? "text-[var(--ink)]" : "text-[var(--ink-2)] hover:bg-[var(--chip)] hover:text-[var(--ink)]"}`}>
                  {active && (
                    <motion.span layoutId="nav-active" className="absolute inset-0 rounded-r-lg rounded-l-none border-l-2 border-[var(--accent-2)] bg-[var(--chip)]"
                      transition={{ type: "spring", stiffness: 400, damping: 32 }} />
                  )}
                  <span className="relative flex items-start gap-2.5">
                    <span className={`mt-px w-4 text-center ${active ? "text-[var(--accent-2)]" : "text-[var(--muted)]"}`} aria-hidden>{s.icon}</span>
                    <span>
                      <span className={active ? "font-medium" : ""}>{s.n && <span className="tabular mr-1.5 text-[var(--muted)]">{s.n}</span>}{s.label}</span>
                      <span className="hidden text-xs font-normal text-[var(--muted)] md:block">{s.hint}</span>
                    </span>
                  </span>
                </button>
              );
            })}
          </nav>
          <div className="glass mt-6 rounded-xl p-3 text-xs text-[var(--ink-2)]">
            <div className="flex items-center justify-between">
              <span className="font-medium text-[var(--ink)]">Pilot</span>
              <span className={`flex items-center gap-1.5 ${pilot ? "text-[var(--good-ink)]" : "text-[var(--bad)]"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${pilot ? "bg-[var(--good)] shadow-[0_0_8px_var(--good)]" : "bg-[var(--bad)]"} ${pilot?.running ? "animate-pulse" : ""}`} />
                {pilot ? (pilot.running ? "Running" : "Engine online") : "Offline"}
              </span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--chip)]">
              <motion.div className="h-full rounded-full bg-[var(--accent)]"
                animate={{ width: `${(100 * (pilot?.running ? pilot.week : done)) / total}%` }} transition={{ duration: 0.8 }} />
            </div>
            <div className="mt-1.5">
              {pilot ? (pilot.running ? `Week ${pilot.week} of ${pilot.target}…` : `${done} of ${total} weeks run`) : "Engine not reachable"}
            </div>
            {pilot?.error && <div className="mt-1 text-[var(--bad)]">The last run failed.</div>}
          </div>
          <p className="mt-4 text-xs text-[var(--muted)]">All data is synthetic. No real physicians, no messages sent.</p>
          <div className="mt-4 flex items-center gap-2 border-t border-[var(--line)] pt-3 text-[11px] text-[var(--muted)]">
            <span>Omnisense · next best action for pharma omnichannel</span>
          </div>
          <div className="mt-2 flex items-center gap-2 text-[11px] text-[var(--muted)]">
            <span>Powered by</span><GenpactLogo className="h-7 w-auto text-[var(--ink)]" />
          </div>
        </aside>
        <main className="min-w-0 p-4 md:p-8">
          <AnimatePresence mode="wait">
            <motion.div key={current.id} className="screen"
              initial={{ opacity: 0, y: 16, scale: 0.985 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 1.01 }}
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}>
              <Current pilot={pilot} runPilot={runPilot} go={go} screens={SCREENS} />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </MotionConfig>
  );
}

// Light and dark themes. The choice is remembered in this browser.
function ThemeSwitch({ theme, setTheme }) {
  const light = theme === "light";
  return (
    <button type="button" onClick={() => setTheme(light ? "dark" : "light")} title={light ? "Switch to the dark theme" : "Switch to the light theme"}
      aria-label={light ? "Switch to the dark theme" : "Switch to the light theme"}
      className="relative mt-1 flex h-7 w-12 shrink-0 items-center rounded-full border border-[var(--axis)] bg-[var(--chip)] px-0.5">
      <motion.span layout transition={{ type: "spring", stiffness: 500, damping: 32 }}
        className={`flex h-5.5 w-5.5 items-center justify-center rounded-full text-[11px] ${light ? "ml-auto bg-[var(--accent)] text-[var(--on-accent)]" : "bg-[var(--surface)] text-[var(--ink)]"}`}
        style={{ height: 22, width: 22 }}>
        {light ? "☀" : "☾"}
      </motion.span>
    </button>
  );
}
