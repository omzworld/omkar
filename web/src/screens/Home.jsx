// Home: what the tool does, the live platform map, what is different, and the guided demo tour.
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { api, num } from "../api";
import { CountUp, Reveal, Tilt } from "../fx.jsx";
import PlatformMap from "./PlatformMap.jsx";

const DIFFERENT = [
  { icon: "Aa", title: "Rules in plain English", text: "Marketers type a rule as a sentence, see the form it becomes, and test it on last week's data before approving it." },
  { icon: "◎", title: "Finds what the rules missed", text: "A discovery module spots risks and opportunities no rule covers, capped at 10% of what is sent each week." },
  { icon: "☰", title: "A talk track, not a list", text: "Each rep gets a short weekly brief: their territory, three suggestions and what to say, every number checked." },
  { icon: "?", title: "Every decision explained", text: "Every action, and everything not sent, carries its reason: the rule that fired and the check that stopped it." },
];

const TOUR = {
  readiness: "Two markets, 3,000 doctors and 24 months of history. Is the data good enough to act on?",
  rules: "Change the Movicol brick-decline threshold and see straight away which doctors it now reaches.",
  week: "Run one week: triggers raised, checks applied, and the ranked list with expected return.",
  delivery: "What a rep, a key account manager and the agency would actually receive.",
  feedback: "Run to week 8: what reps accepted or dismissed, and the changes the engine proposes.",
  results: "Run to week 26: test against control territories, lift, cost and break-even.",
};

const HEADLINE = ["The", "right", "next", "step", "for", "every", "doctor,", "every", "week."];

export default function Home({ pilot, go, screens }) {
  const [r, setR] = useState(null);
  const [week, setWeek] = useState(null);
  const [fb, setFb] = useState(null);
  const done = pilot?.completed_weeks ?? 0;
  useEffect(() => {
    api("/readiness").then(setR).catch(() => {});
    api("/week", { week: 1, dial: 1 }).then(setWeek).catch(() => {});   // a preview run: changes no saved data
  }, []);
  useEffect(() => { api("/feedback").then(setFb).catch(() => {}); }, [done]);

  const hcps = r ? r.headline.reduce((a, h) => a + h.healthcare_professionals, 0) : null;
  const terr = r ? r.headline.reduce((a, h) => a + h.test_territories + h.control_territories, 0) : null;
  const total = pilot?.pilot_weeks ?? 26;
  const tour = screens.filter((s) => s.id !== "home");

  return (
    <div className="mx-auto max-w-6xl space-y-16 pb-10">
      {/* Opening banner */}
      <section className="relative pt-4 md:pt-10">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}
          className="kicker inline-flex items-center gap-2.5">
          <span className="h-px w-6 bg-[var(--accent-2)]" />
          Pharma omnichannel · Next best action engine
        </motion.div>
        <h1 className="display mt-6 max-w-4xl text-4xl font-bold leading-[1.02] tracking-[-0.03em] md:text-6xl">
          {HEADLINE.map((w, i) => (
            <motion.span key={i} className={`mr-[0.25em] inline-block ${i >= 5 ? "text-gradient" : ""}`}
              initial={{ opacity: 0, y: 30, rotateX: -60 }} animate={{ opacity: 1, y: 0, rotateX: 0 }}
              transition={{ delay: 0.1 + i * 0.06, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}>{w}</motion.span>
          ))}
        </h1>
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.7, duration: 0.8 }}
          className="mt-6 max-w-2xl text-base text-[var(--ink-2)] md:text-lg">
          The engine reads what is happening with each doctor and account, decides who needs attention and why, checks what
          is allowed, and hands reps and the agency a ranked, explained plan. Then it learns from the response.
        </motion.p>
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.9 }} className="mt-8 flex flex-wrap gap-3">
          <button onClick={() => document.getElementById("map")?.scrollIntoView({ behavior: "smooth", block: "start" })}
            className="btn-primary px-6 py-3 text-sm font-semibold">See how it works ↓</button>
          <button onClick={() => go("readiness")}
            className="rounded-full border border-[var(--axis)] bg-transparent px-6 py-3 text-sm font-semibold transition hover:border-[var(--muted)]">
            Start the demo →
          </button>
        </motion.div>
        <div className="mt-12 grid grid-cols-2 gap-3 xl:grid-cols-4">
          {[
            [hcps === null ? "…" : num(hcps), "healthcare professionals"],
            [r ? r.headline.map((h) => h.market).join(" + ") : "…", "markets: Germany and the UK"],
            [r ? `${Math.round(r.history_weeks / 4.33)} months` : "…", "of history to learn from"],
            [terr === null ? "…" : num(terr), "territories, split test and control"],
          ].map(([v, l], i) => (
            <motion.div key={l} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1 + i * 0.1 }}>
              <Tilt className="glass glow-hover h-full rounded-2xl p-4">
                <div className="display tabular text-2xl font-semibold md:text-3xl"><CountUp value={v} /></div>
                <div className="mt-1 text-xs text-[var(--ink-2)] md:text-sm">{l}</div>
              </Tilt>
            </motion.div>
          ))}
        </div>
      </section>

      {/* The live platform map */}
      <section id="map" className="scroll-mt-6">
        <Reveal>
          <SectionHead eyebrow="How it works" title="One week in the engine"
            text="Six stages run every week in a loop. Click a stage to zoom in and see live numbers from the engine, or press Auto tour to let it present itself." />
          <PlatformMap week={week} readiness={r} feedback={fb} go={go} />
        </Reveal>
      </section>

      {/* What makes it different */}
      <section>
        <Reveal><SectionHead eyebrow="Why it is different" title="More than a list of suggestions" /></Reveal>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {DIFFERENT.map((d, i) => (
            <Reveal key={d.title} delay={i * 0.08} className="h-full">
              <Tilt className="glass glow-hover h-full rounded-2xl p-5">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-[var(--accent)]/25 to-[var(--accent-2)]/25 text-base font-semibold text-[var(--accent)] ring-1 ring-[rgba(106,109,255,0.35)]" aria-hidden>{d.icon}</div>
                <div className="display mt-4 font-semibold">{d.title}</div>
                <p className="mt-1.5 text-sm text-[var(--ink-2)]">{d.text}</p>
              </Tilt>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Demo tour and pilot status */}
      <section>
        <Reveal><SectionHead eyebrow="The demo" title="A guided tour in six screens"
          text="Follow them in order: each screen picks up where the last one left off." /></Reveal>
        <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
          <div className="grid gap-3 sm:grid-cols-2">
            {tour.map((s, i) => (
              <Reveal key={s.id} delay={i * 0.05} className="h-full">
                <Tilt as="button" max={5} onClick={() => go(s.id)} className="group glass glow-hover h-full w-full rounded-2xl p-5 text-left">
                  <div className="flex items-center justify-between">
                    <span className="display tabular text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Screen {i + 1}</span>
                    <span className="text-[var(--muted)] transition group-hover:translate-x-1 group-hover:text-[var(--accent)]" aria-hidden>→</span>
                  </div>
                  <div className="display mt-2 font-semibold">{s.label}</div>
                  <p className="mt-1 text-sm text-[var(--ink-2)]">{TOUR[s.id]}</p>
                </Tilt>
              </Reveal>
            ))}
          </div>
          <Reveal>
            <aside className="glass h-fit rounded-2xl p-5">
              <div className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">Pilot progress</div>
              <div className="display tabular mt-2 text-4xl font-semibold"><span className="text-gradient">{done}</span><span className="text-lg text-[var(--muted)]"> / {total} weeks</span></div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-[var(--chip)]" role="progressbar" aria-valuenow={done} aria-valuemin={0} aria-valuemax={total}>
                <motion.div className="h-full rounded-full bg-[var(--accent)] shadow-[0_0_12px_var(--accent)]"
                  initial={{ width: 0 }} animate={{ width: `${(100 * done) / total}%` }} transition={{ duration: 1 }} />
              </div>
              <p className="mt-3 text-sm text-[var(--ink-2)]">
                {pilot?.running ? `Running week ${pilot.week} of ${pilot.target}…`
                  : done === 0 ? "Not started. Run weeks from the Weekly run, Feedback and Results screens."
                  : done >= total ? "Complete. The Results screen shows test against control."
                  : "Under way. Carry on from the Feedback or Results screen."}
              </p>
              <button onClick={() => go(done === 0 ? "week" : done >= total ? "results" : "feedback")}
                className="btn-primary mt-4 w-full rounded-xl px-4 py-2.5 text-sm">
                {done === 0 ? "Run the first week" : done >= total ? "See the results" : "Carry on"}
              </button>
            </aside>
          </Reveal>
        </div>
      </section>

      <footer className="flex flex-wrap gap-x-8 gap-y-2 border-t border-[var(--line)] pt-6 text-sm text-[var(--muted)]">
        <span>All data is synthetic: no real doctors.</span>
        <span>Nothing is sent: delivery files are written, not mailed.</span>
        <span>Every number traces back to a rule or a check.</span>
      </footer>
    </div>
  );
}

function SectionHead({ eyebrow, title, text }) {
  return (
    <div className="mb-6">
      <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--accent-2)]">{eyebrow}</div>
      <h2 className="mt-2 text-3xl font-bold leading-tight md:text-4xl">{title}</h2>
      {text && <p className="mt-2 max-w-2xl text-[var(--ink-2)]">{text}</p>}
    </div>
  );
}
