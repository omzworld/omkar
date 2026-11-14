// Scene 2: rule studio. Open a rule, change a threshold, see who it now reaches, save a new version.
import { useEffect, useMemo, useState } from "react";
import { api, num, words } from "../api";
import { Badge, Button, Card, Field, inputClass, Message, Table } from "../ui";

export default function RuleStudio() {
  const [rules, setRules] = useState([]);
  const [selected, setSelected] = useState("R075");
  const [family, setFamily] = useState("all");
  const [detail, setDetail] = useState(null);
  const [params, setParams] = useState({});
  const [preview, setPreview] = useState(null);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => api("/rules").then(setRules);
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!selected) return;
    setPreview(null); setMsg(null);
    api(`/rules/${selected}`).then((d) => { setDetail(d); setParams(d.parameters); });
  }, [selected]);

  const families = useMemo(() => ["all", ...new Set(rules.map((r) => r.family))], [rules]);
  const shown = rules.filter((r) => family === "all" || r.family === family);
  const changed = detail && Object.keys(params).some((k) => String(params[k]) !== String(detail.parameters[k]));

  const doPreview = async () => {
    setBusy(true); setMsg(null);
    try { setPreview(await api(`/rules/${selected}/preview`, { parameters: cast(params), week: 1 })); }
    catch (e) { setMsg({ tone: "bad", text: e.message }); }
    setBusy(false);
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
      <header>
        <h1 className="text-2xl font-semibold">Rule studio</h1>
        <p className="mt-1 max-w-3xl text-[var(--ink-2)]">
          The rules that raise a trigger for a physician or account. Change a threshold, see exactly who it adds or
          removes this week, then save it as a new version. The catalogue itself is never overwritten.
        </p>
      </header>
      <div className="grid gap-6 xl:grid-cols-[22rem_1fr]">
        <Card title={`Rules switched on (${rules.filter((r) => r.enabled).length})`}>
          <select className={`${inputClass} mb-3`} value={family} onChange={(e) => setFamily(e.target.value)} aria-label="Rule family">
            {families.map((f) => <option key={f} value={f}>{f === "all" ? "All families" : words(f)}</option>)}
          </select>
          <ul className="max-h-[36rem] space-y-1 overflow-auto">
            {shown.filter((r) => r.enabled).map((r) => (
              <li key={r.id}>
                <button onClick={() => setSelected(r.id)}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm ${selected === r.id ? "bg-[var(--chip)]" : "hover:bg-[var(--chip)]/60"}`}>
                  <div className="flex items-center gap-2">
                    <span className="tabular font-medium">{r.id}</span>
                    <span className="text-xs text-[var(--muted)]">{words(r.brand)}</span>
                    {r.version > 1 && <Badge tone="accent">v{r.version}</Badge>}
                    {r.paused && <Badge tone="bad">paused</Badge>}
                  </div>
                  <div className="mt-0.5 line-clamp-2 text-[var(--ink-2)]">{r.reason_template}</div>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        {detail && (
          <div className="min-w-0 space-y-6">
            <Card title={`${detail.id} · ${words(detail.family)}`} subtitle={`${words(detail.brand)} · ${detail.markets.join(", ")} · ${detail.trigger_type} · action: ${words(detail.channel)}, ${words(detail.content_theme)}`}
              actions={<Badge tone="accent">version {detail.version}</Badge>}>
              <p className="text-sm text-[var(--ink-2)]">Reason the rep sees</p>
              <p className="mb-4 mt-1">{detail.reason_template}</p>
              <p className="text-sm text-[var(--ink-2)]">Condition</p>
              <pre className="mt-1 overflow-auto rounded-lg bg-[var(--chip)] p-3 text-sm">{detail.condition}</pre>
              {Object.keys(params).length > 0 ? (
                <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {Object.keys(params).map((k) => (
                    <Field key={k} label={words(k)} hint={`Catalogue value: ${detail.catalogue_parameters[k]}`}>
                      <input className={inputClass} value={params[k]} inputMode="decimal"
                        onChange={(e) => setParams({ ...params, [k]: e.target.value })} />
                    </Field>
                  ))}
                </div>
              ) : <p className="mt-4 text-sm text-[var(--muted)]">This rule has no thresholds to change.</p>}
              <div className="mt-5 flex flex-wrap gap-2">
                <Button onClick={doPreview} disabled={busy}>See who it reaches</Button>
              </div>
              {msg && <div className="mt-4"><Message tone={msg.tone}>{msg.text}</Message></div>}
            </Card>

            {preview && (
              <Card title="Who the rule reaches" subtitle={`Week 1 of the pilot (${preview.run_date}), all territories.`}>
                <div className="grid grid-cols-3 gap-3">
                  <Stat2 label="Now" value={num(preview.before)} />
                  <Stat2 label="With your change" value={num(preview.after)} />
                  <Stat2 label="Difference" value={`${preview.after - preview.before >= 0 ? "+" : ""}${num(preview.after - preview.before)}`} />
                </div>
                <h3 className="mb-2 mt-5 text-sm font-medium">Added ({preview.added.length})</h3>
                <Table maxHeight="20rem" rows={preview.added} empty="No one is added." columns={[
                  { key: "name", label: "Physician" }, { key: "hcp_id", label: "Id" }, { key: "territory_id", label: "Territory" },
                  { key: "pilot_arm", label: "Pilot group", render: (r) => words(r.pilot_arm) }, { key: "reason", label: "Reason", wide: true }]} />
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
    </div>
  );
}

function Stat2({ label, value }) {
  return (
    <div className="rounded-lg bg-[var(--chip)] p-3">
      <div className="text-xs text-[var(--ink-2)]">{label}</div>
      <div className="tabular text-xl font-semibold">{value}</div>
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
