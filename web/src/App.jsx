// The app shell: a sidebar with the six demo scenes, the pilot status, and the selected screen.
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import Readiness from "./screens/Readiness.jsx";
import RuleStudio from "./screens/RuleStudio.jsx";
import WeeklyRun from "./screens/WeeklyRun.jsx";
import Delivery from "./screens/Delivery.jsx";
import Feedback from "./screens/Feedback.jsx";
import Results from "./screens/Results.jsx";

const SCREENS = [
  { id: "readiness", label: "Data readiness", hint: "What data we have", C: Readiness },
  { id: "rules", label: "Rule studio", hint: "Change a rule, see who it reaches", C: RuleStudio },
  { id: "week", label: "Weekly run", hint: "Triggers, checks, ranked actions", C: WeeklyRun },
  { id: "delivery", label: "Delivery", hint: "What reps and the agency receive", C: Delivery },
  { id: "feedback", label: "Feedback", hint: "What reps accepted, what to change", C: Feedback },
  { id: "results", label: "Results and return", hint: "Test versus control, break-even", C: Results },
];

export default function App() {
  const [screen, setScreen] = useState(() => window.location.hash.slice(1) || "readiness");
  const [pilot, setPilot] = useState(null);

  const refresh = useCallback(() => api("/pilot/status").then(setPilot).catch(() => {}), []);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (!pilot?.running) return;
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [pilot?.running, refresh]);
  useEffect(() => { window.location.hash = screen; }, [screen]);
  useEffect(() => {   // the browser's back and forward buttons, and typed addresses, switch screens too
    const onHash = () => setScreen(window.location.hash.slice(1) || "readiness");
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const runPilot = async (weeks, fresh = false) => {
    try { setPilot(await api("/pilot/run", { weeks, fresh })); } catch (e) { alert(e.message); }
    refresh();
  };
  const Current = (SCREENS.find((s) => s.id === screen) || SCREENS[0]).C;

  return (
    <div className="min-h-screen md:grid md:grid-cols-[16rem_1fr]">
      <aside className="border-b border-[var(--line)] bg-[var(--surface)] p-4 md:sticky md:top-0 md:h-screen md:border-b-0 md:border-r">
        <div className="mb-5">
          <div className="text-sm font-semibold">Next best action</div>
          <div className="text-xs text-[var(--muted)]">Pharma omnichannel · MVP</div>
        </div>
        <nav className="grid grid-cols-2 gap-1 md:grid-cols-1">
          {SCREENS.map((s, i) => (
            <button key={s.id} onClick={() => setScreen(s.id)}
              className={`rounded-lg px-3 py-2 text-left text-sm transition ${screen === s.id ? "bg-[var(--chip)] font-medium" : "hover:bg-[var(--chip)]/60"}`}>
              <span className="tabular mr-2 text-[var(--muted)]">{i + 1}</span>{s.label}
              <span className="hidden text-xs font-normal text-[var(--muted)] md:block md:pl-5">{s.hint}</span>
            </button>
          ))}
        </nav>
        <div className="mt-6 rounded-lg border border-[var(--line)] p-3 text-xs text-[var(--ink-2)]">
          <div className="font-medium text-[var(--ink)]">Pilot</div>
          {pilot ? (
            pilot.running
              ? <div className="mt-1">Running: week {pilot.week} of {pilot.target}…</div>
              : <div className="mt-1">{pilot.completed_weeks} of {pilot.pilot_weeks} weeks run</div>
          ) : <div className="mt-1">Engine not reachable</div>}
          {pilot?.error && <div className="mt-1 text-[var(--bad)]">The last run failed.</div>}
        </div>
        <p className="mt-4 text-xs text-[var(--muted)]">All data is synthetic. No real physicians, no messages sent.</p>
      </aside>
      <main className="min-w-0 p-4 md:p-8">
        <Current pilot={pilot} runPilot={runPilot} />
      </main>
    </div>
  );
}
