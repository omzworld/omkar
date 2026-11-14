// Scene 5: feedback. Run to week 8, see what reps accepted and dismissed by rule, approve an engine proposal.
import { useEffect, useState } from "react";
import { api, num, pct, words } from "../api";
import { Badge, Bars, Button, Card, Message, Stat, Table } from "../ui";

export default function Feedback({ pilot, runPilot }) {
  const [f, setF] = useState(null);
  const [msg, setMsg] = useState(null);
  const done = pilot?.completed_weeks ?? 0;
  const running = pilot?.running;

  const load = () => api("/feedback").then(setF).catch(() => setF(null));
  useEffect(() => { if (!running) load(); }, [done, running]);

  const approve = async (rule) => {
    try {
      const v = await api(`/feedback/proposals/${rule}/approve`, {});
      setMsg(`Approved: ${rule} is now version ${v.version}${v.paused ? " (paused)" : ""}. It applies from the next week the pilot runs.`);
      load();
    } catch (e) { setMsg(e.message); }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Feedback</h1>
        <p className="mt-1 max-w-3xl text-[var(--ink-2)]">
          Reps accept or dismiss each suggestion and say why. The engine reads that back every week, and proposes
          changes to rules the field keeps turning down.
        </p>
      </header>
      <Card title="Run the pilot" subtitle="Test territories get the engine; control territories keep today's plan. About 4 seconds a week.">
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => runPilot(8, done === 0 || done > 8)} disabled={running}>Run to week 8</Button>
          <Button kind="secondary" onClick={() => runPilot(26)} disabled={running || done >= 26}>Carry on to week 26</Button>
          <Button kind="secondary" onClick={() => { if (confirm("Start the pilot again from week 1?")) runPilot(8, true); }} disabled={running}>Start again</Button>
          <span className="text-sm text-[var(--ink-2)]">
            {running ? `Running week ${pilot.week} of ${pilot.target}…` : `${done} of ${pilot?.pilot_weeks ?? 26} weeks run.`}
          </span>
        </div>
      </Card>
      {msg && <Message tone="good">{msg}</Message>}

      {f?.weeks > 0 && (<>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {(() => {
            const total = f.by_week.reduce((a, w) => a + w.suggestions, 0);
            const acc = f.by_week.reduce((a, w) => a + w.accepted, 0);
            const last = f.by_week[f.by_week.length - 1];
            return (<>
              <Stat label="Suggestions to reps" value={num(total)} note={`over ${f.weeks} weeks`} />
              <Stat label="Accepted" value={pct((100 * acc) / Math.max(total, 1), 0)} note={`${num(acc)} suggestions`} />
              <Stat label="Accepted last week" value={pct(last?.acceptance_pct, 0)} note="pilot gate: at least 45%" tone={last?.acceptance_pct >= 45 ? "good" : "bad"} />
              <Stat label="Proposals from the engine" value={num(f.proposals.length)} note="rules reps keep turning down" />
            </>);
          })()}
        </div>

        <Card title="What the engine proposes" subtitle="Rule R134: a rule with at least 20 triggers in 30 days whose suggestions reps accepted less than 40% of the time.">
          {f.proposals.length === 0 ? <p className="text-sm text-[var(--muted)]">No rule is below the bar this week.</p> : (
            <div className="space-y-3">
              {f.proposals.map((p) => (
                <div key={p.rule_id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--line)] p-4">
                  <div className="max-w-3xl">
                    <div className="flex items-center gap-2"><span className="font-medium">{p.rule_id}</span><Badge>{words(p.family)}</Badge>
                      <Badge tone="bad">{pct(100 * p.acceptance_rate, 0)} accepted</Badge></div>
                    <p className="mt-1 text-sm text-[var(--ink-2)]">{p.reason}.</p>
                    <code className="mt-1 block text-xs text-[var(--muted)]">{p.condition}</code>
                  </div>
                  <Button onClick={() => approve(p.rule_id)}>{Object.keys(p.proposed || {}).length ? "Approve the change" : "Approve: pause the rule"}</Button>
                </div>
              ))}
            </div>
          )}
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Acceptance by week" subtitle="Share of suggestions reps accepted. Trust builds as reps see the reasons.">
            <Bars data={f.by_week.map((w, i) => ({ ...w, label: `Week ${i + 1}` }))} label="label" value="acceptance_pct" format={(v) => num(v, 0)} unit="%" />
          </Card>
          <Card title="Why reps dismissed suggestions">
            <Bars data={f.dismiss_reasons.map((d) => ({ ...d, reason: words(d.reason) }))} label="reason" value="count" color="var(--series-2)" />
          </Card>
        </div>

        <Card title="Acceptance by rule" subtitle="Lowest first.">
          <Table maxHeight="28rem" rows={f.by_rule} columns={[
            { key: "rule_id", label: "Rule" }, { key: "reason_template", label: "What it says", wide: true },
            { key: "suggestions", label: "Suggestions", num: true }, { key: "accepted", label: "Accepted", num: true },
            { key: "acceptance_rate", label: "Rate", num: true, render: (r) => pct(100 * r.acceptance_rate, 0) },
            { key: "top_dismiss_reason", label: "Main reason when dismissed", render: (r) => words(r.top_dismiss_reason) || "–" }]} />
        </Card>
      </>)}
    </div>
  );
}
