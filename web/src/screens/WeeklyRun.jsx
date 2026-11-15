// Scene 3: one weekly run. Triggers -> constraint verdicts -> optimiser decisions, and the rules-to-score dial.
import { useState } from "react";
import { api, eur, num, pct, words } from "../api";
import { Badge, Bars, Button, Card, Field, inputClass, Message, Stat, Table } from "../ui";
import { BrickTrend } from "../viz.jsx";

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
          One week in the test territories. The week starts from the quarter's plan: the touches due this week for
          every rep. Rules raise risks and opportunities; constraints check them; the optimiser scores everything and
          moves a planned touch to a physician who needs it more, like for like, never adding to the total.
        </p>
      </header>

      <Card>
        <div className="grid gap-5 md:grid-cols-[10rem_1fr_auto] md:items-end">
          <Field label="Pilot week">
            <select className={inputClass} value={week} onChange={(e) => setWeek(e.target.value)}>
              {Array.from({ length: maxWeek }, (_, i) => i + 1).map((w) => <option key={w} value={w}>Week {w}</option>)}
            </select>
          </Field>
          <Field label={`Plan-to-reallocate dial: ${Number(dial).toFixed(2)}`}
            hint="0 = follow the plan exactly. 1 = move up to the quarter's cap (20% of planned touches) to where they are worth most.">
            <input type="range" min="0" max="1" step="0.25" value={dial} onChange={(e) => setDial(e.target.value)} className="w-full accent-[var(--accent)]" aria-label="Plan-to-reallocate dial" />
            <div className="flex justify-between text-xs text-[var(--muted)]"><span>Follow the plan</span><span>Reallocate up to the cap</span></div>
          </Field>
          <Button onClick={run} disabled={busy}>{busy ? "Running…" : "Run the week"}</Button>
        </div>
        {err && <div className="mt-4"><Message tone="bad">{err}</Message></div>}
      </Card>

      {h && (<>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Stat label="Planned touches due" value={num(h["planned touches due"])} note="this week's share of the quarter's plan" />
          <Stat label="Delivered as planned" value={num(h["planned touches delivered"])} note={`${num(h["planned touches blocked"])} blocked by consent or eligibility`} />
          <Stat label="Moved by the engine" value={num(h["touches moved by the engine"])} note={`${pct((100 * h["touches moved by the engine"]) / Math.max(h["planned touches due"], 1), 0)} of planned, to a risk or opportunity`} tone="good" />
          <Stat label="Risks and opportunities raised" value={num(h["triggers raised"])} note={`for ${num(h["physicians and accounts with a trigger"])} physicians and accounts`} />
          <Stat label="Expected return" value={eur(h["total expected return (EUR)"])} note={`same touches, ${eur(h["total cost of touches sent (EUR)"])} as planned`} />
        </div>
        {prev && prev.dial !== h["rules-to-score dial"] && (
          <Message>
            With the dial at {prev.dial} the engine moved {num(prev.h["touches moved by the engine"])} planned touches for {eur(prev.h["total expected return (EUR)"])} expected
            return. At {h["rules-to-score dial"]} it moves {num(h["touches moved by the engine"])} for {eur(h["total expected return (EUR)"])}. The number of touches and
            their cost stay the same: {num(h["actions sent"])} touches, {eur(h["total cost of touches sent (EUR)"])}.
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

        <Card title="3. This week's touches: the plan, and what moved in"
          subtitle="Moved-in touches first. Expected return = chance of response × value of response − cost of the touch. Chance comes from the physician's own history, their peers', or the IQVIA benchmark.">
          <Table maxHeight="30rem" rows={r.sent} columns={[
            { key: "name", label: "Physician or account", render: (s) => <span>{s.name}<span className="block text-xs text-[var(--muted)]">{s.hcp_id} · {s.territory_id}</span>
              <span className="mt-1 inline-block"><Badge tone={s.origin === "plan" ? "neutral" : "good"}>{s.origin === "plan" ? "planned" : "moved in"}</Badge></span></span> },
            { key: "final_channel", label: "Action", render: (s) => `${words(s.final_channel)}, ${words(s.content_theme)}` },
            { key: "probability_of_response", label: "Chance", num: true, render: (s) => <span>{pct(100 * s.probability_of_response, 0)}<span className="block text-xs text-[var(--muted)]">{words(s.chance_tier)}</span></span> },
            { key: "value_of_response", label: "Value", num: true, render: (s) => eur(s.value_of_response) },
            { key: "cost_of_touch", label: "Cost", num: true, render: (s) => eur(s.cost_of_touch) },
            { key: "final_return", label: "Expected return", num: true, render: (s) => eur(s.final_return) },
            { key: "reason", label: "Why", wide: true, render: (s) => <span>{s.reason}{/brick/i.test(s.reason) && <span className="mt-1 block"><BrickTrend brick={s.brick_id} until={h["run date"]} /></span>}<span className="block text-xs text-[var(--muted)]">{s.rule_ids}{s.status === "substituted" ? " · moved to a cheaper channel" : ""}</span></span> }]} />
        </Card>

        {r.moved?.length > 0 && (
          <Card title="Planned touches the engine moved, and why" subtitle="Each one went to a physician with a higher expected return on the same channel, or was blocked and its slot reused. A moved touch is not rescheduled, so the quarter's total stays on plan.">
            <Table maxHeight="22rem" rows={r.moved} columns={[
              { key: "name", label: "Planned for", render: (s) => <span>{s.name}<span className="block text-xs text-[var(--muted)]">{s.segment_name || ""}</span></span> },
              { key: "final_channel", label: "Channel", render: (s) => words(s.final_channel) },
              { key: "final_return", label: "Its expected return", num: true, render: (s) => eur(s.final_return) },
              { key: "not_sent_reason", label: "What happened", wide: true }]} />
          </Card>
        )}

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
