// Scene 1: data readiness. What data we have before the pilot, and whether it is good enough.
import { useEffect, useState } from "react";
import { api, num, pct, words } from "../api";
import { Bars, Card, Message, Stat, Status, Table } from "../ui";

const STAGES = ["curiosity", "consideration", "experience", "loyalty", "advocacy"];

export default function Readiness() {
  const [r, setR] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { api("/readiness").then(setR).catch((e) => setErr(e.message)); }, []);
  if (err) return <Message tone="bad">{err}</Message>;
  if (!r) return <p className="text-sm text-[var(--muted)]">Loading the data audit…</p>;

  const hcps = r.headline.reduce((a, h) => a + h.healthcare_professionals, 0);
  const orgs = r.headline.reduce((a, h) => a + h.organisations, 0);
  const terr = r.headline.reduce((a, h) => a + h.test_territories + h.control_territories, 0);
  const consentOk = r.consent.every((c) => c.within_5_points);
  const stageRows = ["DE", "UK"].map((m) => {
    const row = { market: m };
    r.stages.filter((s) => s.market === m).forEach((s) => { row[s.stage] = s.end_pct; });
    return row;
  });

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Data readiness</h1>
        <p className="mt-1 max-w-3xl text-[var(--ink-2)]">
          The data audit before the pilot starts: who is in the data, how much history we have, whether consent and
          response data are good enough to act on.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Markets" value={r.headline.map((h) => h.market).join(" and ")} note="Germany and the United Kingdom" />
        <Stat label="Healthcare professionals" value={num(hcps)} note={`plus ${num(orgs)} practices, hospitals, units and pharmacies`} />
        <Stat label="History" value={`${Math.round(r.history_weeks / 4.33)} months`} note={`${r.history_weeks} weeks of calls, emails, events and sales`} />
        <Stat label="Territories in the pilot" value={num(terr)} note="split into test and control, by market and tier mix" />
      </div>

      <Card title="Email consent by market" subtitle="Share of healthcare professionals who allow us to email them, against the rate the data design expects."
        actions={<Status passed={consentOk} />}>
        <Table rows={r.consent} columns={[
          { key: "market", label: "Market" },
          { key: "email_pct", label: "Email consent", num: true, render: (c) => pct(c.email_pct) },
          { key: "expected_email_pct", label: "Expected", num: true, render: (c) => pct(c.expected_email_pct) },
          { key: "gap_points", label: "Difference (points)", num: true, render: (c) => num(c.gap_points, 1) },
          { key: "email_double_opt_in_pct", label: "Double opt-in", num: true, render: (c) => pct(c.email_double_opt_in_pct) },
          { key: "remote_call_pct", label: "Remote calls", num: true, render: (c) => pct(c.remote_call_pct) },
          { key: "tracked_digital_pct", label: "Tracked digital", num: true, render: (c) => pct(c.tracked_digital_pct) },
        ]} />
        <p className="mt-3 text-xs text-[var(--muted)]">Germany requires double opt-in for marketing email; the engine blocks email where it is missing.</p>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Response rate by channel" subtitle="Share of touches over the 24 months that got a response (a visit with a next step, an opened email, an attended webinar).">
          <Bars data={[...r.response_by_channel].sort((a, b) => b.response_pct - a.response_pct).map((d) => ({ ...d, channel: words(d.channel) }))}
            label="channel" value="response_pct" format={(v) => num(v, 1)} unit="%" />
        </Card>
        <Card title="Brick sales trend" subtitle="Movicol units in each sales area (brick): the last 3 complete months against the 3 before. A brick counts as down or up only when 2 of its last 3 monthly readings agree and it sells at least 100 units in 3 months.">
          <Table rows={r.bricks} columns={[
            { key: "market", label: "Market" },
            { key: "bricks", label: "Bricks", num: true },
            { key: "median_change_pct", label: "Typical change", num: true, render: (b) => pct(b.median_change_pct) },
            { key: "bricks_down_8pct_or_more", label: "Steadily down 8%+", num: true },
            { key: "bricks_up_10pct_or_more", label: "Steadily up 10%+", num: true },
          ]} />
        </Card>
      </div>

      <Card title="Where physicians are in the journey today" subtitle="Share of healthcare professionals in each stage at the end of the history.">
        <Table rows={stageRows} columns={[{ key: "market", label: "Market" },
          ...STAGES.map((s) => ({ key: s, label: s[0].toUpperCase() + s.slice(1), num: true, render: (row) => pct(row[s]) }))]} />
      </Card>

      <Card title="Tables and gaps" subtitle="Rows per table, and columns with blanks. Blanks in physician-only fields on organisation rows are expected.">
        <div className="grid gap-6 lg:grid-cols-2">
          <Table maxHeight="22rem" rows={r.row_counts.filter((t) => t.rows > 0)} columns={[
            { key: "table", label: "Table" }, { key: "rows", label: "Rows", num: true, render: (t) => num(t.rows) }]} />
          <Table maxHeight="22rem" rows={r.null_rates} columns={[
            { key: "table", label: "Table" }, { key: "column", label: "Column" },
            { key: "null_pct", label: "Blank", num: true, render: (n) => pct(n.null_pct) }]} />
        </div>
      </Card>
    </div>
  );
}
