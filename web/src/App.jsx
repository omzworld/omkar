// The app shell: a sidebar with home and the six demo scenes, the pilot status, and the selected screen.
import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { api } from "./api";
import { Backdrop } from "./fx.jsx";
import Home from "./screens/Home.jsx";
import DataCenter from "./screens/DataCenter.jsx";
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
  { id: "rules", n: 2, label: "Rule studio", hint: "Change or write a rule", icon: "⚙", C: RuleStudio },
  { id: "week", n: 3, label: "Weekly run", hint: "Triggers, checks, ranked actions", icon: "▶", C: WeeklyRun },
  { id: "delivery", n: 4, label: "Delivery", hint: "What reps and the agency receive", icon: "➤", C: Delivery },
  { id: "feedback", n: 5, label: "Feedback", hint: "What reps accepted, what to change", icon: "↻", C: Feedback },
  { id: "results", n: 6, label: "Results and return", hint: "Test versus control, break-even", icon: "◔", C: Results },
];

export default function App() {
  const [screen, setScreen] = useState(() => window.location.hash.slice(1) || "home");
  const [pilot, setPilot] = useState(null);

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
          <button onClick={() => go("home")} className="group mb-6 flex items-center gap-3 text-left">
            <span className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--accent)] text-[#ffffff] shadow-[0_0_24px_-4px_var(--accent)] transition group-hover:rotate-12">
              <span className="display text-sm font-bold">N</span>
            </span>
            <span>
              <span className="display block text-sm font-semibold">Next best action</span>
              <span className="block text-xs text-[var(--muted)]">Pharma omnichannel · MVP</span>
            </span>
          </button>
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
