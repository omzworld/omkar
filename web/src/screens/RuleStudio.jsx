// Scene 2: rule studio. A summary of every rule by type and what it did this week, the catalogue grouped by family
// (expand for detail), the playbook behind each action, threshold changes with a preview, and new rules.
import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { api, num, words } from "../api";
import { Badge, Button, Card, Field, inputClass, Message, Table } from "../ui";
import NewRule from "./NewRule.jsx";
import { BrickTrend } from "../viz.jsx";
import { Playbook } from "../playbook.jsx";

const TYPE_COLOR = { risk: "var(--bad)", opportunity: "var(--good)", guardrail: "var(--warn)", cadence: "var(--accent-2)",
  channel: "var(--accent)", content: "var(--accent-3)", capacity: "var(--series-2)" };

function Spark({ values, color = "var(--accent)", w = 64, h = 20 }) {
  if (!values?.length || values.every((v) => !v)) return <span className="text-[10px] text-[var(--muted)]">–</span>;
  const max = Math.max(...values, 1);
  const pts = values.map((v, i) => `${(i * w) / Math.max(values.length - 1, 1)},${h - 2 - ((h - 4) * v) / max}`).join(" ");
  return <svg width={w} height={h} aria-hidden><polyline points={pts} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" /></svg>;
}

export default function RuleStudio() {
  const [sum, setSum] = useState(null);
  const [selected, setSelected] = useState("R075");
  const [creating, setCreating] = useState(false);
  const [banner, setBanner] = useState(null);
  const [type, setType] = useState("all");
  const [onlyOn, setOnlyOn] = useState(true);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState({ movicol: true });
  const [detail, setDetail] = useState(null);
  const [params, setParams] = useState({});
  const [preview, setPreview] = useState(null);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => api("/rules/summary").then(setSum);
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!selected) return;
    setPreview(null); setMsg(null);
    api(`/rules/${selected}`).then((d) => { setDetail(d); setParams(d.parameters); });
  }, [selected]);

  const families = useMemo(() => (sum?.families || []).map((f) => ({
    ...f, rules: f.rules.filter((r) => (type === "all" || r.type === type) && (!onlyOn || r.on)
      && (!q || `${r.id} ${r.reason} ${r.channel} ${r.theme} ${r.brand}`.toLowerCase().includes(q.toLowerCase()))),
  })).filter((f) => f.rules.length), [sum, type, onlyOn, q]);
  const changed = detail && Object.keys(params).some((k) => String(params[k]) !== String(detail.parameters[k]));
  const row = useMemo(() => sum?.families.flatMap((f) => f.rules).find((r) => r.id === selected), [sum, selected]);

  const doPreview = async () => {
    setBusy(true); setMsg(null);
    try { setPreview(await api(`/rules/${selected}/preview`, { parameters: cast(params), week: sum?.latest_week || 1 })); }
    catch (e) { setMsg({ tone: "bad", text: e.message }); }
    setBusy(false);
  };
  const onApproved = async (rec) => {
    setCreating(false); await load(); setType("all"); setSelected(rec.id);
    setBanner(`${rec.id} is approved and switched on. It joins the next week the pilot runs.`);
  };
  const removeRule = async () => {
    if (!confirm(`Remove ${selected}? It will not run in later weeks.`)) return;
    try { await api(`/author/remove/${selected}`, {}); setBanner(`${selected} was removed.`); await load(); setSelected("R075"); }
    catch (e) { setMsg({ tone: "bad", text: e.message }); }
  };
  const doSave = async () => {
    setBusy(true);
    try {
      const v = await api(`/rules/${selected}/save`, { parameters: cast(params), note });
      setMsg({ tone: "good", text: `Saved as version ${v.version}. Every run from now on uses it.` });
      setNote("");
      const d = await api(`/rules/${selected}`); setDetail(d); setParams(d.parameters); load();
    } catch (e) { setMsg({ tone: "bad", text: e.message }); }
    setBusy(false);
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Rule studio</h1>
          <p className="mt-1 max-w-3xl text-[var(--ink-2)]">
            Every rule the engine runs, what it did in the latest weeks, and the exact playbook behind each action.
            Expand a group for the detail, change a threshold and see who it reaches, or write a new rule in plain words.
          </p>
        </div>
        <Button onClick={() => { setCreating(true); setBanner(null); }}>+ Create new rule</Button>
      </header>
      {banner && <Message tone="good"><span className="mr-2 text-[var(--good-ink)]">✓</span>{banner}</Message>}

      {sum && <Summary sum={sum} type={type} setType={setType} />}

      {creating && <NewRule onClose={() => setCreating(false)} onApproved={onApproved} />}

      {!creating && (
        <div className="grid gap-6 xl:grid-cols-[minmax(24rem,30rem)_1fr]">
          <Card title="The catalogue" subtitle={sum ? `${sum.rules_on} of ${sum.rules_total} rules switched on · counts are for week ${sum.latest_week}` : ""}>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <input className={`${inputClass} flex-1`} placeholder="Search rules, channels, content…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search rules" />
              <label className="flex items-center gap-1.5 text-xs text-[var(--ink-2)]"><input type="checkbox" checked={onlyOn} onChange={(e) => setOnlyOn(e.target.checked)} />switched on only</label>
            </div>
            {type !== "all" && <div className="mb-2 text-xs text-[var(--ink-2)]">Showing {sum?.types.find((t) => t.type === type)?.label.toLowerCase()} · <button className="underline" onClick={() => setType("all")}>show all</button></div>}
            <div className="max-h-[44rem] space-y-2 overflow-auto pr-1">
              {families.map((f) => {
                const isOpen = open[f.family] ?? (q !== "" || type !== "all");
                const reach = f.rules.reduce((a, r) => a + (r.editable ? r.reach : r.held), 0);
                return (
                  <div key={f.family} className="rounded-xl border border-[var(--line)]">
                    <button className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left" onClick={() => setOpen({ ...open, [f.family]: !isOpen })}>
                      <span className="flex items-center gap-2"><span className={`text-xs transition-transform ${isOpen ? "rotate-90" : ""}`}>▶</span>
                        <span className="font-medium">{f.label}</span><span className="text-xs text-[var(--muted)]">{f.rules.length} rules</span></span>
                      <span className="tabular text-xs text-[var(--ink-2)]">{num(reach)}</span>
                    </button>
                    <AnimatePresence initial={false}>
                      {isOpen && (
                        <motion.ul initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden border-t border-[var(--line)]">
                          {f.rules.map((r) => (
                            <li key={r.id}>
                              <button onClick={() => setSelected(r.id)}
                                className={`grid w-full grid-cols-[1fr_auto] gap-2 px-3 py-2 text-left text-sm ${selected === r.id ? "bg-[var(--chip)]" : "hover:bg-[var(--chip)]/60"}`}>
                                <span className="min-w-0">
                                  <span className="flex items-center gap-2">
                                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: r.on ? TYPE_COLOR[r.type] : "var(--axis)" }} />
                                    <span className="tabular font-medium">{r.id}</span>
                                    <span className="truncate text-xs text-[var(--muted)]">{words(r.channel)}{r.theme !== "none" ? ` · ${words(r.theme)}` : ""}</span>
                                    {r.custom && <Badge tone="good">new</Badge>}
                                    {!r.on && <Badge>off</Badge>}
                                  </span>
                                  <span className="mt-0.5 block truncate text-[var(--ink-2)]">{r.reason}</span>
                                </span>
                                <span className="flex flex-col items-end">
                                  <span className="tabular text-sm font-medium">{num(r.editable ? r.reach : r.held)}</span>
                                  <Spark values={r.trend} color={TYPE_COLOR[r.type]} w={48} h={14} />
                                </span>
                              </button>
                            </li>
                          ))}
                        </motion.ul>
                      )}
                    </AnimatePresence>
                  </div>
                );
              })}
              {families.length === 0 && <p className="text-sm text-[var(--muted)]">No rules match.</p>}
            </div>
            <p className="mt-3 text-xs text-[var(--muted)]">Number on the right: doctors picked out (risks and opportunities) or actions held (guardrails and cadence) in the latest week; the line is the last four weeks.</p>
          </Card>

          {detail && (
            <div className="min-w-0 space-y-6">
              <Card title={`${detail.id} · ${words(detail.family)}`} subtitle={`${words(detail.brand)} · ${detail.markets.join(", ")} · ${detail.trigger_type === "none" ? words(row?.type || "") : detail.trigger_type}`}
                actions={<div className="flex items-center gap-2">{detail.custom && <><Badge tone="good">written in the rule studio</Badge><Button kind="secondary" onClick={removeRule}>Remove</Button></>}
                  {row && <Badge tone={row.on ? "good" : "neutral"}>{row.on ? "switched on" : "switched off"}</Badge>}<Badge tone="accent">version {detail.version}</Badge></div>}>
                {row && (
                  <div className="mb-4 grid grid-cols-3 gap-3">
                    {row.editable ? (<>
                      <Mini label={`Doctors picked out, week ${sum.latest_week}`} value={num(row.reach)} spark={row.trend} color={TYPE_COLOR[row.type]} />
                      <Mini label="Acted on (moved into the plan)" value={num(row.acted)} />
                      <Mini label="Action" value={<span className="text-base capitalize">{words(detail.channel)}</span>} note={words(detail.content_theme)} />
                    </>) : (<>
                      <Mini label={`Actions held, week ${sum.latest_week}`} value={num(row.held)} spark={row.trend} color={TYPE_COLOR[row.type]} />
                      <Mini label="Owner" value={<span className="text-base capitalize">{detail.owner}</span>} />
                      <Mini label="Effect" value={<span className="text-base capitalize">{words(detail.channel)}</span>} />
                    </>)}
                  </div>
                )}
                <p className="text-sm text-[var(--ink-2)]">Reason the rep sees</p>
                <p className="mb-4 mt-1">{detail.reason_template}</p>
                <p className="text-sm text-[var(--ink-2)]">Condition</p>
                <pre className="mt-1 overflow-auto whitespace-pre-wrap rounded-lg bg-[var(--chip)] p-3 text-sm">{detail.condition}</pre>
                {row?.editable && (Object.keys(params).length > 0 ? (
                  <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {Object.keys(params).map((k) => (
                      <Field key={k} label={words(k)} hint={`Catalogue value: ${detail.catalogue_parameters[k]}`}>
                        <input className={inputClass} value={params[k]} inputMode="decimal" onChange={(e) => setParams({ ...params, [k]: e.target.value })} />
                      </Field>
                    ))}
                  </div>
                ) : <p className="mt-4 text-sm text-[var(--muted)]">This rule has no thresholds to change.</p>)}
                {row?.editable && <div className="mt-5 flex flex-wrap gap-2"><Button onClick={doPreview} disabled={busy}>See who it reaches</Button></div>}
                {msg && <div className="mt-4"><Message tone={msg.tone}>{msg.text}</Message></div>}
              </Card>

              {detail.playbook && detail.trigger_type !== "none" && (
                <Card title="What the action does" subtitle="The playbook the rep or agency follows. Wording is illustrative until it comes from the approved documents.">
                  <div className="grid gap-6 2xl:grid-cols-2">
                    <div><h3 className="mb-1 text-sm font-medium">For any doctor this rule picks out</h3><Playbook pb={detail.playbook} /></div>
                    {detail.example ? (
                      <div className="rounded-xl bg-[var(--chip)]/50 p-3">
                        <h3 className="text-sm font-medium">Filled in for {detail.example.name} <span className="text-xs font-normal text-[var(--muted)]">{detail.example.hcp_id} · week {detail.example.week} · {detail.example.status === "sent" ? "acted on" : "picked out, not sent"}</span></h3>
                        <p className="mb-2 mt-1 text-xs text-[var(--ink-2)]">{detail.example.reason}</p>
                        <Playbook pb={detail.example.playbook} compact />
                      </div>
                    ) : <p className="text-sm text-[var(--muted)]">No doctor was picked out by this rule in the latest week.</p>}
                  </div>
                </Card>
              )}

              {preview && (
                <Card title="Who the rule reaches" subtitle={`Week ${preview.week} of the pilot (${preview.run_date}), all territories.`}>
                  <div className="grid grid-cols-3 gap-3">
                    <Mini label="Now" value={num(preview.before)} />
                    <Mini label="With your change" value={num(preview.after)} />
                    <Mini label="Difference" value={`${preview.after - preview.before >= 0 ? "+" : ""}${num(preview.after - preview.before)}`} />
                  </div>
                  <h3 className="mb-2 mt-5 text-sm font-medium">Added ({preview.added.length})</h3>
                  <Table maxHeight="20rem" rows={preview.added} empty="No one is added." columns={[
                    { key: "name", label: "Physician" }, { key: "hcp_id", label: "Id" }, { key: "territory_id", label: "Territory" },
                    { key: "pilot_arm", label: "Pilot group", render: (r) => words(r.pilot_arm) }, { key: "reason", label: "Reason", wide: true, render: (r) => <span>{r.reason}{/brick/i.test(r.reason) && <span className="mt-1 block"><BrickTrend brick={r.brick_id} until={preview.run_date} /></span>}</span> }]} />
                  {preview.removed.length > 0 && (<>
                    <h3 className="mb-2 mt-5 text-sm font-medium">Removed ({preview.removed.length})</h3>
                    <Table maxHeight="16rem" rows={preview.removed} columns={[
                      { key: "name", label: "Physician" }, { key: "territory_id", label: "Territory" }, { key: "reason", label: "Reason", wide: true }]} />
                  </>)}
                  <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
                    <Field label="Why the change (saved with the version)">
                      <input className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Brand team review, 14 Nov" />
                    </Field>
                    <Button onClick={doSave} disabled={busy || !changed}>Save as a new version</Button>
                  </div>
                </Card>
              )}

              {detail.history?.length > 0 && (
                <Card title="Versions">
                  <Table rows={[...detail.history].reverse()} columns={[
                    { key: "version", label: "Version", num: true }, { key: "saved_at", label: "Saved" },
                    { key: "parameters", label: "Values", render: (v) => Object.entries(v.parameters).map(([k, x]) => `${words(k)} ${x}`).join(", ") },
                    { key: "paused", label: "Status", render: (v) => (v.paused ? "paused" : "active") },
                    { key: "note", label: "Note", wide: true }]} />
                </Card>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Summary({ sum, type, setType }) {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <Big label="Rules switched on" value={`${sum.rules_on}`} note={`of ${sum.rules_total} in the catalogue`} />
        <Big label={`Doctors picked out, week ${sum.latest_week}`} value={num(sum.doctors_reached)} note="by at least one risk or opportunity rule" />
        <Big label="Actions held by guardrails and cadence" value={num(sum.types.filter((t) => ["guardrail", "cadence"].includes(t.type)).reduce((a, t) => a + t.held, 0))}
          note="blocked or delayed this week, so nothing goes that should not" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-7">
        {sum.types.map((t, i) => {
          const val = t.measure === "doctors picked out" ? t.reach : t.held;
          const active = type === t.type;
          return (
            <motion.button key={t.type} type="button" onClick={() => setType(active ? "all" : t.type)}
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
              className={`rounded-2xl border p-3 text-left transition ${active ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--line)] bg-[var(--surface)] hover:border-[var(--axis)]"}`}>
              <div className="flex items-center gap-2 text-sm font-medium"><span className="h-2.5 w-2.5 rounded-full" style={{ background: TYPE_COLOR[t.type] }} />{t.label}</div>
              <div className="mt-2 flex items-end justify-between gap-2">
                <div><div className="tabular text-2xl font-semibold">{val ? num(val) : "–"}</div><div className="text-[11px] text-[var(--muted)]">{val ? t.measure : "applied inside the engine"}</div></div>
                <Spark values={t.trend} color={TYPE_COLOR[t.type]} />
              </div>
              <div className="mt-2 text-xs text-[var(--ink-2)]">{t.rules_on} of {t.rules_total} on</div>
              <div className="mt-1 line-clamp-2 text-[11px] text-[var(--muted)]">{t.blurb}</div>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}

function Big({ label, value, note }) {
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4">
      <div className="text-xs text-[var(--ink-2)]">{label}</div>
      <div className="tabular mt-1 text-3xl font-semibold">{value}</div>
      <div className="mt-0.5 text-xs text-[var(--muted)]">{note}</div>
    </div>
  );
}

function Mini({ label, value, note, spark, color }) {
  return (
    <div className="rounded-lg bg-[var(--chip)] p-3">
      <div className="text-xs text-[var(--ink-2)]">{label}</div>
      <div className="flex items-end justify-between gap-2"><div className="tabular text-xl font-semibold">{value}</div>{spark && <Spark values={spark} color={color} />}</div>
      {note && <div className="text-xs capitalize text-[var(--ink-2)]">{note}</div>}
    </div>
  );
}

function cast(p) {
  const out = {};
  for (const [k, v] of Object.entries(p)) {
    const n = Number(v);
    out[k] = v !== "" && !Number.isNaN(n) ? n : v;
  }
  return out;
}
