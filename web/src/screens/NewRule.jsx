// Rule studio: write a new rule. A guided form (who, when, what, why), checked live against the data
// dictionary, a quick impact test on a real week, then approval as the next rule id.
import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { api, num, words } from "../api";
import { Badge, Button, Card, Field, inputClass, Message, Table } from "../ui";
import { BrickTrend } from "../viz.jsx";

const EMPTY = { brand: "", markets: [], trigger_type: "opportunity", family: "", channel: "", content_theme: "", timing: "this_week",
  priority: 60, reason_template: "", note: "", conditions: [{ column: "", kind: "", op: "", value: "" }] };

// The brief's own example (demo scene 7), with the market left blank on purpose.
const EXAMPLE = { ...EMPTY, brand: "Movicol", trigger_type: "risk", channel: "rep_visit", content_theme: "efficacy", priority: 70,
  reason_template: "Brick {brick_id} down {brick_volume_r3m_pct}% over 3 months and no rep visit in {days_since_rep_visit} days",
  conditions: [
    { column: "brick_volume_r3m_pct", kind: "number", op: "<=", value: -8 },
    { column: "brick_r3m_months_declining", kind: "number", op: ">=", value: 2 },
    { column: "days_since_rep_visit", kind: "number", op: ">=", value: 60 },
    { column: "specialty", kind: "text", op: "==", value: "gp" }] };

export default function NewRule({ onClose, onApproved }) {
  const [opt, setOpt] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [check, setCheck] = useState(null);
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => { api("/author/options").then(setOpt).catch((e) => setErr(e.message)); }, []);
  useEffect(() => {                          // check the draft as it is typed
    const t = setTimeout(() => api("/author/check", { form }).then(setCheck).catch(() => {}), 250);
    setTest(null);
    return () => clearTimeout(t);
  }, [form]);

  const cols = useMemo(() => Object.fromEntries((opt?.columns || []).map((c) => [c.name, c])), [opt]);
  const grouped = useMemo(() => {
    const g = {};
    (opt?.columns || []).forEach((c) => { (g[c.group] ||= []).push(c); });
    return g;
  }, [opt]);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setCond = (i, patch) => setForm((f) => ({ ...f, conditions: f.conditions.map((c, j) => (j === i ? { ...c, ...patch } : c)) }));
  const pickColumn = (i, name) => {
    if (name === "__theme__") return setCond(i, { column: "__theme__", kind: "theme", op: "yes", value: "" });
    const c = cols[name];
    setCond(i, { column: name, kind: c?.kind || "", op: c?.kind === "number" ? ">=" : c?.kind === "yes_no" ? "yes" : "==", value: "" });
  };
  const missing = new Set((check?.missing || []).map((m) => m.toLowerCase()));
  const isMissing = (label) => missing.has(label);

  const runTest = async () => {
    setBusy(true); setErr(null);
    try { setTest(await api("/author/test", { form })); } catch (e) { setErr(e.message); }
    setBusy(false);
  };
  const approve = async () => {
    setBusy(true); setErr(null);
    try { const rec = await api("/author/approve", { form }); onApproved(rec); } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  if (!opt) return <Card><p className="text-sm text-[var(--muted)]">{err || "Loading the data dictionary…"}</p></Card>;
  const t = test?.test;

  return (
    <div className="min-w-0 space-y-6">
      <Card title="Write a new rule" subtitle={`Pick the conditions from the ${opt.columns.length} columns the engine builds every week. Every number becomes a named setting you can change later. It will be saved as ${opt.next_id}.`}
        actions={<div className="flex gap-2"><Button kind="secondary" onClick={() => setForm(EXAMPLE)}>Start from an example</Button><Button kind="secondary" onClick={onClose}>Close</Button></div>}>

        <PlainWords onParsed={(f) => setForm({ ...EMPTY, ...f })} />

        <Step n="1" title="Who it is for">
          <div className="grid gap-4 md:grid-cols-3">
            <Field label="Brand"><select className={ring(inputClass, isMissing("brand"))} value={form.brand} onChange={(e) => set("brand", e.target.value)}>
              <option value="">Choose…</option>{opt.brands.map((b) => <option key={b} value={b}>{b === "all" ? "Any brand" : words(b)}</option>)}</select></Field>
            <Field label="Markets">
              <div className={`flex gap-2 rounded-xl p-1 ${isMissing("market") ? "ring-2 ring-[var(--warn)]" : ""}`}>
                {opt.markets.map((m) => {
                  const on = form.markets.includes(m);
                  return <button key={m} type="button" onClick={() => set("markets", on ? form.markets.filter((x) => x !== m) : [...form.markets, m])}
                    className={`btn-pill flex-1 border px-3 py-2 text-sm ${on ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--ink)]" : "border-[var(--axis)] text-[var(--ink-2)]"}`} title={m === "UK" ? "United Kingdom" : "Germany"}>{m}</button>;
                })}
              </div>
              {isMissing("market") && <span className="mt-1 block text-xs text-[var(--warn)]">Which market?</span>}
            </Field>
            <Field label="It flags a">
              <div className="flex gap-2">
                {["risk", "opportunity"].map((k) => (
                  <button key={k} type="button" onClick={() => set("trigger_type", k)}
                    className={`btn-pill flex-1 border px-3 py-2 text-sm capitalize ${form.trigger_type === k ? "border-[var(--accent-2)] text-[var(--accent-2)]" : "border-[var(--axis)] text-[var(--ink-2)]"}`}>{k}</button>
                ))}
              </div>
            </Field>
          </div>
        </Step>

        <Step n="2" title="When it fires" note="All conditions must be true (AND). Columns with no data yet are shown but cannot be picked.">
          <div className="space-y-2">
            {form.conditions.map((c, i) => (
              <motion.div key={i} layout initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
                className="grid items-start gap-2 rounded-xl border border-[var(--line)] bg-[var(--well)] p-2 md:grid-cols-[minmax(12rem,1.3fr)_minmax(8rem,0.8fr)_1fr_auto]">
                <select className={inputClass} value={c.column} onChange={(e) => pickColumn(i, e.target.value)} aria-label="Column">
                  <option value="">Choose a column…</option>
                  <option value="__theme__">has received a content theme</option>
                  {Object.entries(grouped).map(([g, list]) => (
                    <optgroup key={g} label={g}>
                      {list.map((col) => <option key={col.name} value={col.name} disabled={col.no_data}>{col.label}{col.no_data ? " (no data yet)" : ""}</option>)}
                    </optgroup>
                  ))}
                </select>
                <OpPicker c={c} opt={opt} onChange={(op) => setCond(i, { op })} />
                <ValueInput c={c} col={cols[c.column]} themes={opt.themes} onChange={(value) => setCond(i, { value })} />
                <button type="button" onClick={() => set("conditions", form.conditions.filter((_, j) => j !== i))} disabled={form.conditions.length === 1}
                  className="px-2 py-2 text-[var(--muted)] hover:text-[var(--bad)] disabled:opacity-30" aria-label="Remove condition">✕</button>
                {cols[c.column]?.kind === "number" && (
                  <div className="text-xs text-[var(--muted)] md:col-span-4">This week: lowest {num(cols[c.column].min, 1)}, typical {num(cols[c.column].median, 1)}, highest {num(cols[c.column].max, 1)}{cols[c.column].blank_pct > 0 ? `, blank for ${num(cols[c.column].blank_pct, 0)}%` : ""}.</div>
                )}
              </motion.div>
            ))}
            <button type="button" onClick={() => set("conditions", [...form.conditions, { column: "", kind: "", op: "", value: "" }])}
              className="text-sm font-semibold text-[var(--work)] hover:text-[var(--ink)]">+ Add a condition</button>
          </div>
          {check?.condition_words && (
            <div className="mt-3 rounded-xl border-l-2 border-[var(--accent-2)] bg-[var(--chip)] px-4 py-3 text-sm">
              <div className="text-[var(--ink)]">Fires when {check.condition_words}.</div>
              <code className="mt-1 block text-xs text-[var(--muted)]">{check.record.condition}</code>
            </div>
          )}
        </Step>

        <Step n="3" title="What it suggests">
          <div className="grid gap-4 md:grid-cols-4">
            <Field label="Action"><select className={ring(inputClass, isMissing("action channel"))} value={form.channel} onChange={(e) => set("channel", e.target.value)}>
              <option value="">Choose…</option>{opt.channels.map((c) => <option key={c} value={c}>{c === "next_best" ? "best channel (the optimiser picks)" : words(c)}</option>)}</select></Field>
            <Field label="Content theme"><select className={ring(inputClass, isMissing("content theme"))} value={form.content_theme} onChange={(e) => set("content_theme", e.target.value)}>
              <option value="">Choose…</option>{opt.themes.map((c) => <option key={c} value={c}>{c === "next_theme" ? "next in the journey" : words(c)}</option>)}</select></Field>
            <Field label="Timing"><select className={inputClass} value={form.timing} onChange={(e) => set("timing", e.target.value)}>
              {opt.timings.map((c) => <option key={c} value={c}>{words(c)}</option>)}</select></Field>
            <Field label={`Priority: ${form.priority}`} hint="Used when the rules decide (the dial at 0)">
              <input type="range" min="10" max="100" step="5" value={form.priority} onChange={(e) => set("priority", Number(e.target.value))} className="w-full accent-[var(--accent)]" /></Field>
          </div>
        </Step>

        <Step n="4" title="Why: the reason the rep sees" last>
          <textarea rows={2} className={ring(inputClass, isMissing("the reason the rep sees"))} value={form.reason_template} maxLength={160}
            onChange={(e) => set("reason_template", e.target.value)} placeholder="e.g. Brick {brick_id} down {brick_volume_r3m_pct}% over 3 months and no rep visit in {days_since_rep_visit} days" />
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-[var(--muted)]">
            <span className={form.reason_template.length > 140 ? "text-[var(--bad)]" : ""}>{form.reason_template.length}/140.</span> Insert a value:
            {[...new Set(form.conditions.map((c) => c.column).filter((c) => c && c !== "__theme__")), "brick_id", "territory_id"].map((c) => (
              <button key={c} type="button" onClick={() => set("reason_template", `${form.reason_template}{${c}}`)}
                className="btn-pill border border-[var(--axis)] px-2 py-0.5 hover:border-[var(--accent)] hover:text-[var(--ink)]">{words(c)}</button>
            ))}
          </div>
        </Step>
      </Card>

      {/* What is missing, what is wrong, and the test */}
      <Card title="Check and test" subtitle="The rule is checked against the data dictionary and the catalogue's rules as you type.">
        <div className="space-y-2">
          {(check?.missing || []).map((m) => <Line key={m} tone="warn">Still needed: {m}</Line>)}
          {(check?.problems || []).map((p) => <Line key={p} tone="bad">{p}</Line>)}
          {check?.ready && <Line tone="good">Ready to test: every column exists and every value is allowed.</Line>}
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button onClick={runTest} disabled={busy || !check?.ready}>{busy && !t ? "Testing…" : "Run the quick test"}</Button>
          <span className="text-sm text-[var(--muted)]">Runs on the latest week ({opt.week}) with every other rule. Nothing is saved.</span>
        </div>
        {err && <div className="mt-3"><Message tone="bad">{err}</Message></div>}

        <AnimatePresence>
          {t && (
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-6 space-y-5">
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Big label="Doctors and accounts matched" value={num(t.matched)} note={Object.entries(t.by_market).map(([m, n]) => `${m} ${num(n)}`).join(" · ") || "none"} />
                <Big label="Reps who would get one" value={num(t.reps)} note={`in ${num(t.territories)} territories`} />
                <Big label="In test territories" value={num(t.matched_test_arm)} note="where the engine runs in the pilot" />
                <Big label="Would be sent" value={num(t.would_send_test_arm)} note="after the optimiser, next to every other rule" tone="good" />
              </div>
              <div>
                <div className="mb-2 text-sm text-[var(--ink-2)]">What the constraints engine does with it</div>
                <Verdicts v={t.verdicts} />
                {t.by_constraint.length > 0 && (
                  <ul className="mt-3 space-y-1 text-sm">
                    {t.by_constraint.map((b) => <li key={b.verdict + b.constraint_id} className="flex justify-between gap-3 border-b border-[var(--line)] pb-1"><span>{b.example} <span className="text-[var(--muted)]">({b.constraint_id})</span></span><span className="tabular">{num(b.candidates)}</span></li>)}
                  </ul>
                )}
                <p className="mt-2 text-xs text-[var(--muted)]">{num(t.overlap_other_rules)} of the matches are also picked out by another rule this week; the optimiser keeps the best action for each. {t.note}</p>
              </div>
              <Table maxHeight="18rem" rows={t.sample} empty="No one matches this week." columns={[
                { key: "name", label: "Physician or account" }, { key: "territory_id", label: "Territory" },
                { key: "pilot_arm", label: "Pilot group", render: (r) => words(r.pilot_arm) }, { key: "reason", label: "Reason the rep sees", wide: true, render: (r) => <span>{r.reason}{/brick/i.test(r.reason) && <span className="mt-1 block"><BrickTrend brick={r.brick_id} until={t.run_date} /></span>}</span> }]} />
              <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-[var(--line)] bg-[var(--chip)] p-4">
                <div className="min-w-[16rem] flex-1"><Field label="Approval note (who and why)"><input className={inputClass} value={form.note} onChange={(e) => set("note", e.target.value)} placeholder="e.g. Approved by the Movicol brand lead, 14 Nov" /></Field></div>
                <Button onClick={approve} disabled={busy}>Approve as {opt.next_id}</Button>
              </div>
              <p className="text-xs text-[var(--muted)]">Approved rules join the next week the pilot runs. You can change their settings or pause them like any other rule.</p>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </div>
  );
}

function ring(cls, on) { return `${cls} ${on ? "ring-2 ring-[var(--warn)]" : ""}`; }

function Step({ n, title, note, children, last }) {
  return (
    <section className={`relative pl-10 ${last ? "" : "pb-6"}`}>
      {!last && <span className="absolute bottom-0 left-[0.85rem] top-8 w-px bg-[var(--line)]" />}
      <span className="absolute left-0 top-0 flex h-7 w-7 items-center justify-center rounded-full border border-[var(--accent-2)] text-xs font-semibold text-[var(--accent-2)]">{n}</span>
      <h3 className="text-base font-semibold">{title}</h3>
      {note && <p className="mb-3 mt-0.5 text-xs text-[var(--muted)]">{note}</p>}
      <div className={note ? "" : "mt-3"}>{children}</div>
    </section>
  );
}

function OpPicker({ c, opt, onChange }) {
  if (c.kind === "number") return <select className={inputClass} value={c.op} onChange={(e) => onChange(e.target.value)} aria-label="Comparison">{opt.number_ops.map((o) => <option key={o.op} value={o.op}>{o.label}</option>)}</select>;
  if (c.kind === "text") return <select className={inputClass} value={c.op} onChange={(e) => onChange(e.target.value)} aria-label="Comparison">{opt.text_ops.map((o) => <option key={o.op} value={o.op}>{o.label}</option>)}</select>;
  if (c.kind === "yes_no" || c.kind === "theme") return (
    <select className={inputClass} value={c.op} onChange={(e) => onChange(e.target.value)} aria-label="Yes or no">
      <option value="yes">{c.kind === "theme" ? "yes, has received" : "is yes"}</option><option value="no">{c.kind === "theme" ? "no, never received" : "is no"}</option>
    </select>);
  return <div />;
}

function ValueInput({ c, col, themes, onChange }) {
  if (c.kind === "number") return <input className={inputClass} inputMode="decimal" value={c.value} onChange={(e) => onChange(e.target.value)} placeholder="number" aria-label="Value" />;
  if (c.kind === "theme") return <select className={inputClass} value={c.value} onChange={(e) => onChange(e.target.value)} aria-label="Theme"><option value="">Choose a theme…</option>{themes.filter((t) => t !== "next_theme").map((t) => <option key={t} value={t}>{words(t)}</option>)}</select>;
  if (c.kind === "text") {
    const vals = col?.values || [];
    if (c.op === "in") {
      const chosen = Array.isArray(c.value) ? c.value : [];
      return (
        <div className="flex flex-wrap gap-1">
          {vals.map((v) => {
            const on = chosen.includes(v);
            return <button key={v} type="button" onClick={() => onChange(on ? chosen.filter((x) => x !== v) : [...chosen, v])}
              className={`btn-pill border px-2 py-1 text-xs ${on ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--axis)] text-[var(--ink-2)]"}`}>{words(v)}</button>;
          })}
        </div>);
    }
    return <select className={inputClass} value={Array.isArray(c.value) ? "" : c.value} onChange={(e) => onChange(e.target.value)} aria-label="Value"><option value="">Choose…</option>{vals.map((v) => <option key={v} value={v}>{words(v)}</option>)}</select>;
  }
  return <div />;
}

function Line({ tone, children }) {
  const c = { warn: "var(--warn)", bad: "var(--bad)", good: "var(--good)" }[tone];
  return <div className="flex items-start gap-2 text-sm"><span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: c }} /><span>{children}</span></div>;
}

function Big({ label, value, note, tone }) {
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--well)] p-4">
      <div className="text-xs text-[var(--ink-2)]">{label}</div>
      <div className={`display tabular mt-1 text-2xl font-bold ${tone === "good" ? "text-[var(--good-ink)]" : ""}`}>{value}</div>
      <div className="text-xs text-[var(--muted)]">{note}</div>
    </div>
  );
}

function Verdicts({ v }) {
  const total = (v.allowed || 0) + (v.delayed || 0) + (v.blocked || 0);
  if (!total) return <p className="text-sm text-[var(--muted)]">Nothing to check: the rule matches no one this week.</p>;
  const segs = [["Allowed", v.allowed, "var(--good)"], ["Delayed", v.delayed, "var(--warn)"], ["Blocked", v.blocked, "var(--bad)"]];
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full bg-[var(--chip)]">
        {segs.map(([l, n, c], i) => <motion.div key={l} style={{ background: c }} initial={{ width: 0 }} animate={{ width: `${(100 * (n || 0)) / total}%` }} transition={{ delay: i * 0.1, duration: 0.7 }} />)}
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-sm">{segs.map(([l, n, c]) => <span key={l} className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: c }} />{l} <strong className="tabular">{num(n || 0)}</strong></span>)}</div>
    </div>
  );
}

// Describe the rule in plain words (or pick a ready-made prompt); the parser fills the form below, and what it could
// not work out is highlighted there as missing.
function PlainWords({ onParsed }) {
  const [examples, setExamples] = useState([]);
  const [text, setText] = useState("");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api("/author/examples").then(setExamples).catch(() => {}); }, []);
  const run = async (t) => {
    const sentence = (t ?? text).trim();
    if (!sentence) return;
    setText(sentence); setBusy(true);
    try { const r = await api("/author/parse", { text: sentence }); setRes(r); onParsed(r.form); } catch { setRes(null); }
    setBusy(false);
  };
  return (
    <div className="mb-6 rounded-2xl border border-[var(--accent)]/40 bg-[var(--accent-soft)] p-4">
      <div className="text-sm font-medium">Describe it in plain words</div>
      <p className="mt-0.5 text-xs text-[var(--ink-2)]">Type a sentence or click an example. The form below fills itself in; anything missing is highlighted for you to complete.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {examples.map((e) => (
          <button key={e} type="button" onClick={() => run(e)} title={e}
            className="btn-pill max-w-full truncate border border-[var(--axis)] bg-[var(--surface)] px-3 py-1.5 text-left text-xs text-[var(--ink-2)] hover:border-[var(--accent)] hover:text-[var(--ink)]" style={{ maxWidth: "26rem" }}>{e}</button>
        ))}
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto]">
        <textarea rows={2} className={inputClass} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="e.g. If a Movicol brick drops more than 8% and the GP has not seen a rep in two months, send a rep visit with the efficacy asset" />
        <Button onClick={() => run()} disabled={busy || !text.trim()}>Fill the form</Button>
      </div>
      {res && (
        <div className="mt-3 space-y-1 text-xs">
          {res.recognised.length > 0 && <div><span className="text-[var(--ink-2)]">Understood: </span>{res.recognised.map((r) => <span key={r} className="mr-1 inline-block rounded bg-[var(--surface)] px-1.5 py-0.5">{r}</span>)}</div>}
          {res.condition_words && <div><span className="text-[var(--ink-2)]">Condition: </span>{res.condition_words}</div>}
          {res.unsupported.length > 0 && <div className="text-[var(--warn)]">No data for this yet: {res.unsupported.join(", ")}</div>}
          {res.missing.length > 0 ? <div className="text-[var(--warn)]">Still needed: {res.missing.join(", ")}</div> : <div className="text-[var(--good-ink)]">Complete: run the quick test below, then approve.</div>}
        </div>
      )}
    </div>
  );
}
