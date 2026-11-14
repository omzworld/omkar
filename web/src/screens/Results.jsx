// Scene 6: results and return. Test versus control, lift, cost per engaged physician, the return model and
// break-even, with editable assumptions.
import { useEffect, useState } from "react";
import { api, eur, num, pct } from "../api";
import { Button, Card, Field, inputClass, Lines, Message, Stat, Status, Table } from "../ui";

export default function Results({ pilot, runPilot }) {
  const done = pilot?.completed_weeks ?? 0;
  const running = pilot?.running;
  const [inputs, setInputs] = useState({ fee: "", margin: "70", sales: "", lift: "", savings: true });
  const [m, setM] = useState(null);
  const [err, setErr] = useState(null);

  const load = () => {
    const q = new URLSearchParams();
    if (inputs.fee) q.set("fee", inputs.fee);
    if (inputs.margin) q.set("margin", inputs.margin);
    if (inputs.sales) q.set("sales", inputs.sales);
    if (inputs.lift) q.set("lift", inputs.lift);
    q.set("savings", inputs.savings);
    api(`/measure?${q}`).then(setM).catch((e) => setErr(e.message));
  };
  useEffect(() => { if (!running && done) load(); }, [done, running]);  // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k) => (e) => setInputs({ ...inputs, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const arm = (name) => m?.arms?.find((a) => a.pilot_arm === name);
  const rm = m?.return_model;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Results and return</h1>
        <p className="mt-1 max-w-3xl text-[var(--ink-2)]">
          Test territories ran the engine; control territories ran today's plan. Territories were split before the
          pilot and never changed, so the difference between them is the engine's effect.
        </p>
      </header>
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => runPilot(26)} disabled={running || done >= 26}>Run to week 26</Button>
          <span className="text-sm text-[var(--ink-2)]">
            {running ? `Running week ${pilot.week} of ${pilot.target}…` : done ? `Measured over ${done} weeks${m?.from ? `, ${m.from} to ${m.to}` : ""}.` : "The pilot has not run yet."}
          </span>
        </div>
      </Card>
      {err && <Message tone="bad">{err}</Message>}

      {m?.weeks > 0 && m.lift?.months_measured > 0 && (<>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Brick sales lift, test vs control" value={`${m.lift.lift_pts >= 0 ? "+" : ""}${num(m.lift.lift_pts, 1)} pts`}
            note={`Movicol units: test ${pct(m.lift.test_growth_pct)}, control ${pct(m.lift.control_growth_pct)} (${m.lift.first_month}–${m.lift.last_month} vs the months before)`} tone={m.lift.lift_pts > 0 ? "good" : "bad"} />
          <Stat label="Extra units sold" value={num(m.lift.incremental_units)} note="in test territories, against what control growth predicts" />
          <Stat label="Cost per engaged physician" value={eur(arm("test")?.cost_per_engaged_eur)} note={`control: ${eur(arm("control")?.cost_per_engaged_eur)}`} />
          <Stat label="Touches per physician" value={num(arm("test")?.touches_per_physician, 1)} note={`control: ${num(arm("control")?.touches_per_physician, 1)}`} />
        </div>

        <Card title="Movicol brick sales, test vs control" subtitle="Units per month, indexed so the six months before the pilot average 100. One axis for both groups.">
          <Lines data={m.monthly_index} x="month" yLabel="Movicol units index"
            series={[{ key: "test", label: "Test", color: "var(--accent)" }, { key: "control", label: "Control", color: "var(--series-2)" }]}
            shadeFrom={(d) => d.pilot} />
        </Card>

        <div className="grid gap-6 xl:grid-cols-2">
          <Card title="Test and control side by side" subtitle="Physicians who can be promoted to, over the pilot weeks.">
            <Table rows={[
              ["Physicians", "physicians", (v) => num(v)], ["Touches", "touches", (v) => num(v)],
              ["Reached at least once", "reach_pct", (v) => pct(v)], ["Responded at least once", "engaged_pct", (v) => pct(v)],
              ["Share of touches answered", "response_pct", (v) => pct(v)], ["Moved up a journey stage", "moved_up_pct", (v) => pct(v)],
              ["Moved back a stage", "moved_back_pct", (v) => pct(v)], ["Cost of touches", "cost_eur", (v) => eur(v)],
              ["Cost per engaged physician", "cost_per_engaged_eur", (v) => eur(v)],
            ].map(([label, key, f]) => ({ label, test: f(arm("test")?.[key]), control: f(arm("control")?.[key]) }))}
              columns={[{ key: "label", label: "" }, { key: "test", label: "Test", num: true }, { key: "control", label: "Control", num: true }]} />
          </Card>
          <Card title="Pilot gates" subtitle="The success criteria agreed for the pilot.">
            <Table rows={m.gates} columns={[
              { key: "gate", label: "Gate", wide: true }, { key: "cadence", label: "Checked" },
              { key: "value", label: "Result", num: true, render: (g) => `${num(g.value, 1)}${g.unit}` },
              { key: "target", label: "Target", num: true, render: (g) => `${g.rule === ">=" ? "at least" : "at most"} ${num(g.target)}${g.unit}` },
              { key: "passed", label: "", render: (g) => <Status passed={g.passed} /> }]} />
          </Card>
        </div>

        <Card title="Return model" subtitle="What the lift and the freed field time are worth against the fee, per quarter. Change any input and recalculate.">
          <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
            <Field label="Fee per quarter (€)" hint="blank = assumptions file"><input className={inputClass} value={inputs.fee} onChange={set("fee")} placeholder="180000" inputMode="numeric" /></Field>
            <Field label="Gross margin (%)"><input className={inputClass} value={inputs.margin} onChange={set("margin")} inputMode="decimal" /></Field>
            <Field label="Brand sales per quarter (€)" hint="blank = synthetic test territories"><input className={inputClass} value={inputs.sales} onChange={set("sales")} placeholder="e.g. 20000000" inputMode="numeric" /></Field>
            <Field label="Lift to use (points)" hint="blank = measured"><input className={inputClass} value={inputs.lift} onChange={set("lift")} placeholder={num(m.lift.lift_pts, 1)} inputMode="decimal" /></Field>
            <Field label="Count freed field time" hint="only if reps' time is redeployed">
              <label className="flex items-center gap-2 py-2 text-sm"><input type="checkbox" checked={inputs.savings} onChange={set("savings")} className="accent-[var(--accent)]" />Include touch cost saving</label>
            </Field>
            <div className="flex items-end"><Button onClick={load}>Recalculate</Button></div>
          </div>
          {rm && (<>
            <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Extra gross margin per quarter" value={eur(rm.incremental_margin_per_quarter_eur)} note={`${num(rm.lift_pts_used, 1)} pts on ${eur(rm.baseline_sales_per_quarter_eur)} sales${rm.baseline_is_synthetic ? " (synthetic)" : ""}`} />
              <Stat label="Touch cost saving per quarter" value={eur(rm.touch_cost_saving_per_quarter_eur)} note={rm.count_touch_savings ? "counted" : "not counted"} />
              <Stat label="Net benefit per quarter" value={eur(rm.net_benefit_per_quarter_eur)} note={`after a fee of ${eur(rm.fee_per_quarter_eur)}`} tone={rm.net_benefit_per_quarter_eur >= 0 ? "good" : "bad"} />
              <Stat label="Break-even lift" value={`${num(rm.break_even_lift_pts, 2)} pts`} note={rm.break_even_lift_pts === 0 ? "the saving alone covers the fee" : `measured: ${num(m.lift.lift_pts, 1)} pts`} tone={m.lift.lift_pts >= rm.break_even_lift_pts ? "good" : "bad"} />
            </div>
            <p className="mt-3 text-xs text-[var(--muted)]">
              Return on the fee: {num(rm.return_on_fee, 2)}×. Fee at risk if the 4-point lift gate is missed: {eur(rm.fee_at_risk_eur)}.
              The synthetic market is small; enter the client's real brand sales to see the return at roll-out scale.
            </p>
          </>)}
        </Card>
      </>)}
      {done > 0 && m && !m.lift?.months_measured && <Message>The first pilot month is not complete yet; sales lift appears once it is.</Message>}
    </div>
  );
}
