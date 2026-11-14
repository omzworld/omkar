// Scene 3: one weekly run. Triggers -> constraint verdicts -> optimiser decisions, and the rules-to-score dial.
import { useState } from "react";
import { api, eur, num, pct, words } from "../api";
import { Bars, Button, Card, Field, inputClass, Message, Stat, Table } from "../ui";

export default function WeeklyRun({ pilot }) {
  const [week, setWeek] = useState(1);
  const [dial, setDial] = useState(1);
  const [r, setR] = useState(null);
  const [prev, setPrev] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const maxWeek = Math.max(1, Math.min((pilot?.completed_weeks ?? 0) + 1, pilot?.pilot_weeks ?? 26));

  const run = async () => {
    setBusy(true); setErr(null);
    try {
      const res = await api("/week", { week: Number(week), dial: Number(dial) });
      if (r) setPrev({ dial: r.headline["rules-to-score dial"], h: r.headline });
      setR(res);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };
  const h = r?.headline;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Weekly run</h1>
        <p className="mt-1 max-w-3xl text-[var(--ink-2)]">
          One week of the engine for the test territories: rules raise triggers, constraints allow, delay or block
          them, and the optimiser ranks what is left by expected return and fills each rep's capacity.
        </p>
      </header>

      <Card>
        <div className="grid gap-5 md:grid-cols-[10rem_1fr_auto] md:items-end">
          <Field label="Pilot week">
            <select className={inputClass} value={week} onChange={(e) => setWeek(e.target.value)}>
              {Array.from({ length: maxWeek }, (_, i) => i + 1).map((w) => <option key={w} value={w}>Week {w}</option>)}
            </select>
          </Field>
          <Field label={`Rules-to-score dial: ${Number(dial).toFixed(2)}`}
            hint="0 = the rules decide (highest rule priority first, as a rules-only engine would). 1 = expected return decides.">
            <input type="range" min="0" max="1" step="0.25" value={dial} onChange={(e) => setDial(e.target.value)} className="w-full accent-[var(--accent)]" aria-label="Rules-to-score dial" />
            <div className="flex justify-between text-xs text-[var(--muted)]"><span>Rules decide</span><span>Expected return decides</span></div>
          </Field>
          <Button onClick={run} disabled={busy}>{busy ? "Running…" : "Run the week"}</Button>
        </div>
        {err && <div className="mt-4"><Message tone="bad">{err}</Message></div>}
      </Card>

      {h && (<>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Stat label="Triggers raised" value={num(h["triggers raised"])} note={`for ${num(h["physicians and accounts with a trigger"])} physicians and accounts`} />
          <Stat label="Allowed" value={num(h.allowed)} note={`of ${num(h["candidate actions"])} candidate actions`} />
          <Stat label="Held back" value={num(h.delayed + h.blocked)} note={`${num(h.blocked)} blocked, ${num(h.delayed)} delayed`} />
          <Stat label="Sent" value={num(h["actions sent"])} note={`${num(h["of which substituted to a cheaper channel"])} moved to a cheaper channel`} />
          <Stat label="Expected return" value={eur(h["total expected return (EUR)"])} note={`for ${eur(h["total cost of touches sent (EUR)"])} of touches`} />
        </div>
        {prev && prev.dial !== h["rules-to-score dial"] && (
          <Message>
            With the dial at {prev.dial} the engine sent {num(prev.h["actions sent"])} actions for {eur(prev.h["total expected return (EUR)"])} expected
            return and {eur(prev.h["total cost of touches sent (EUR)"])} of touches. At {h["rules-to-score dial"]} it sends {num(h["actions sent"])} for{" "}
            {eur(h["total expected return (EUR)"])} and {eur(h["total cost of touches sent (EUR)"])}.
          </Message>
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="1. Triggers raised, by rule" subtitle="Which rules fired this week, with one example reason.">
            <Table maxHeight="22rem" rows={[...r.triggers].sort((a, b) => b.triggers - a.triggers)} columns={[
              { key: "rule_id", label: "Rule" }, { key: "triggers", label: "Triggers", num: true, render: (t) => num(t.triggers) },
              { key: "example", label: "Example reason", wide: true }]} />
          </Card>
          <Card title="2. Held back by a constraint" subtitle="Candidate actions blocked or delayed, by the constraint that held them.">
            <Bars data={r.constraints.map((c) => ({ ...c, name: `${c.verdict === "blocked" ? "Blocked" : "Delayed"} · ${c.constraint_id}` }))}
              label="name" value="candidates" />
            <div className="mt-4">
              <Table maxHeight="14rem" rows={r.constraints} columns={[
                { key: "constraint_id", label: "Constraint" }, { key: "candidates", label: "Actions", num: true },
                { key: "example", label: "Example", wide: true }]} />
            </div>
          </Card>
        </div>

        <Card title="3. What is sent, highest expected return first"
          subtitle="Expected return = chance of response × value of response − cost of the touch. Chance comes from the physician's own history, their peers', or the IQVIA benchmark.">
          <Table maxHeight="30rem" rows={r.sent} columns={[
            { key: "name", label: "Physician or account", render: (s) => <span>{s.name}<span className="block text-xs text-[var(--muted)]">{s.hcp_id} · {s.territory_id}</span></span> },
            { key: "final_channel", label: "Action", render: (s) => `${words(s.final_channel)}, ${words(s.content_theme)}` },
            { key: "probability_of_response", label: "Chance", num: true, render: (s) => <span>{pct(100 * s.probability_of_response, 0)}<span className="block text-xs text-[var(--muted)]">{words(s.chance_tier)}</span></span> },
            { key: "value_of_response", label: "Value", num: true, render: (s) => eur(s.value_of_response) },
            { key: "cost_of_touch", label: "Cost", num: true, render: (s) => eur(s.cost_of_touch) },
            { key: "final_return", label: "Expected return", num: true, render: (s) => eur(s.final_return) },
            { key: "reason", label: "Why", wide: true, render: (s) => <span>{s.reason}<span className="block text-xs text-[var(--muted)]">{s.rule_ids}{s.status === "substituted" ? " · moved to a cheaper channel" : ""}</span></span> }]} />
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Sent by channel">
            <Table rows={r.by_channel} columns={[
              { key: "final_channel", label: "Channel", render: (c) => words(c.final_channel) },
              { key: "sent", label: "Sent", num: true },
              { key: "expected_return_eur", label: "Expected return", num: true, render: (c) => eur(c.expected_return_eur) },
              { key: "average_chance", label: "Average chance", num: true, render: (c) => pct(100 * c.average_chance, 0) }]} />
          </Card>
          <Card title="Allowed but not sent, and why">
            <Bars data={r.not_sent} label="reason" value="candidates" />
          </Card>
        </div>

        <Card title="Not sent: the reasons" subtitle="Every candidate action that did not go out carries the reason.">
          <Table maxHeight="24rem" rows={r.held} columns={[
            { key: "name", label: "Physician or account" },
            { key: "final_channel", label: "Action", render: (s) => `${words(s.final_channel)}, ${words(s.content_theme)}` },
            { key: "rule_ids", label: "Rule" },
            { key: "not_sent_reason", label: "Reason not sent", wide: true }]} />
        </Card>
      </>)}
    </div>
  );
}
