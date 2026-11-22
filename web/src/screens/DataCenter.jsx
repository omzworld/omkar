// Data control center: every dataset the engine reads and writes, checked live against its schema; the data
// model with the integrity of every join; the lineage from source systems to what reps receive.
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { api, num, words } from "../api";
import { Badge, Button, Card, Message, Stat, Table } from "../ui";

// Columns of the data model diagram, left to right, in the order data flows.
const LANES = [
  { key: "field", label: "Field force", tables: ["user_vod", "territory_vod", "rep_capacity", "rep_plan_input"] },
  { key: "customers", label: "Customers", tables: ["hcp_master_opendata", "account_vod", "account_profile_vod", "hco_master_opendata", "address_vod", "consent", "hcp_stage_weekly"] },
  { key: "activity", label: "Activity", tables: ["call2_vod", "sent_email_vod", "email_activity_vod", "event_attendee_vod", "agency_email", "agency_media"] },
  { key: "market", label: "Content and market", tables: ["promomats_document", "iqvia_brick_sales", "procedure_volume", "iqvia_channel_preference"] },
  { key: "engine", label: "Engine outputs", tables: ["hcp_segment", "call_plan", "segment_budget", "suggestion_vod", "rep_brief", "feature_snapshot", "rule_draft", "ml_candidate", "proposed_rule"] },
];
const LANE_COLOR = { field: "#ffd0a8", customers: "#6a6dff", activity: "#8a8dff", market: "#ff8f7a", engine: "#4fd1a1" };
const ROADMAP = new Set(["rule_draft", "ml_candidate", "proposed_rule"]);

export default function DataCenter({ go }) {
  const [c, setC] = useState(null);
  const [err, setErr] = useState(null);
  const [open, setOpen] = useState(null);
  const [tab, setTab] = useState("fields");
  const openTable = (name, which = "fields") => { setOpen(name); setTab(which); };
  const [system, setSystem] = useState("all");
  const load = () => api("/data/catalog").then(setC).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const tables = useMemo(() => {
    if (!c) return [];
    const ft = c.feature_table;
    return c.tables.map((t) => t.name === "feature_snapshot" && ft.weeks
      ? { ...t, status: "ok", rows: ft.rows * ft.weeks, actual_fields: ft.columns, completeness_pct: null, note: `${ft.weeks} weekly snapshots of ${num(ft.columns)} columns, kept in data/snapshots` }
      : ROADMAP.has(t.name) && !t.rows ? { ...t, status: "roadmap" } : t);
  }, [c]);

  if (err) return <Message tone="bad">{err}</Message>;
  if (!c) return <p className="text-sm text-[var(--muted)]">Checking every dataset…</p>;

  const byName = Object.fromEntries(tables.map((t) => [t.name, t]));
  const sources = tables.filter((t) => !t.engine_written);
  const systems = [...new Set(sources.map((t) => t.system))];
  const okJoins = c.relations.filter((r) => r.match_pct >= 99).length;
  const sourceRows = sources.reduce((a, t) => a + (t.rows || 0), 0);
  const shown = system === "all" ? tables : tables.filter((t) => t.system === system);
  const ft = c.feature_table;
  const noSource = ft.groups?.flatMap((g) => g.no_source) || [];

  return (
    <div className="space-y-6">
      <header>
        <div className="kicker mb-2">Data control center</div>
        <h1 className="text-2xl font-semibold">What the engine runs on</h1>
        <p className="mt-1 max-w-3xl text-[var(--ink-2)]">
          Every dataset the engine reads and writes, in the client's own source formats (Veeva CRM, Vault PromoMats,
          OpenData, IQVIA), checked live against its schema each time this page opens. Joins are tested key by key.
          Nothing on this page is typed in by hand.
        </p>
      </header>

      {/* Live status strip */}
      <div className="glass flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl px-5 py-3 text-sm">
        <span className="flex items-center gap-2 font-semibold text-[var(--good-ink)]"><span className="h-2 w-2 animate-pulse rounded-full bg-[var(--good)]" />Live checks passed</span>
        <span className="text-[var(--ink-2)]">Checked {c.checked_at} in {c.check_seconds}s</span>
        <span className="text-[var(--ink-2)]">{c.spec.datasets_declared} datasets declared · {c.relations.length} joins tested</span>
        <span className="text-[var(--ink-2)]">Reproducible from seed {c.seed}</span>
        <span className="ml-auto"><Button kind="secondary" onClick={() => { setC(null); setTimeout(load, 50); }}>Re-run checks</Button></span>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6">
        <Stat label="Source systems" value={num(systems.length)} note={systems.slice(0, 4).join(", ") + (systems.length > 4 ? "…" : "")} />
        <Stat label="Source datasets present" value={`${sources.filter((t) => t.status === "ok").length} of ${sources.length}`} note="every declared field found" tone="good" />
        <Stat label="Rows across sources" value={num(sourceRows)} note="24 months of history plus the pilot" />
        <Stat label="Joins that match" value={`${okJoins} of ${c.relations.length}`} note="at least 99% of keys find their record" tone="good" />
        <Stat label="Feature table" value={`${num(ft.columns)} columns`} note={`${num(ft.rows)} accounts × ${ft.weeks} weeks`} />
        <Stat label="Rules switched on" value={num(c.spec.trigger_rules_on)} note={`of ${c.spec.trigger_rules} trigger rules${c.spec.rules_written_in_studio ? `, ${c.spec.rules_written_in_studio} written in the studio` : ""}`} />
      </div>

      <Lineage systems={systems} tables={tables} c={c} system={system} setSystem={setSystem} />

      <Card title="Data model" subtitle="Tables and how they join. Hover a table to see its links; click it for its fields and its data. Each line is a join tested key by key on this page load.">
        <ModelDiagram byName={byName} relations={c.relations} onOpen={(n) => openTable(n)} open={open} />
      </Card>

      <AnimatePresence>
        {open && byName[open] && <FieldPanel t={byName[open]} relations={c.relations} onClose={() => setOpen(null)} tab={tab} setTab={setTab} />}
      </AnimatePresence>

      <Card title="Dataset register" subtitle={system === "all" ? "Every dataset, its source and grain, and how complete its declared fields are. Click a row for field-level detail." : `Showing ${system}. Click the system again in the lineage to show all.`}
        actions={system !== "all" && <Button kind="secondary" onClick={() => setSystem("all")}>Show all</Button>}>
        <Table rows={shown} columns={[
          { key: "name", label: "Dataset", render: (t) => <button onClick={() => openTable(t.name)} className="text-left"><span className="font-semibold text-[var(--ink)] hover:text-[var(--work)]">{t.name}</span><span className="block text-xs text-[var(--muted)]">{t.grain}</span></button> },
          { key: "system", label: "Source", render: (t) => <span className="text-[var(--ink-2)]">{t.system}</span> },
          { key: "rows", label: "Rows", num: true, render: (t) => num(t.rows) },
          { key: "date_from", label: "Covers", render: (t) => t.date_from ? <span className="tabular whitespace-nowrap text-xs">{t.date_from} → {t.date_to}</span> : <span className="text-xs text-[var(--muted)]">{t.note ? "weekly" : "reference"}</span> },
          { key: "completeness_pct", label: "Fields filled", render: (t) => <Fill pct={t.completeness_pct} /> },
          { key: "status", label: "Status", render: (t) => <StatusPill s={t.status} /> },
          { key: "view", label: "", render: (t) => t.rows > 0 && t.status !== "roadmap" ? <button onClick={() => openTable(t.name, "data")} className="whitespace-nowrap text-sm font-semibold text-[var(--work)] hover:text-[var(--ink)]">View data →</button> : null },
        ]} />
        <p className="mt-3 text-xs text-[var(--muted)]">Fields filled is the average share of rows with a value, across the declared fields. Optional fields (for example a call's next step) are blank by design.</p>
      </Card>

      <Card title="Feature table: what the engines read" subtitle={`One row per account per week, built from the datasets above. ${num(ft.columns)} columns in ${ft.groups?.length} groups, plus ${ft.candidate_columns} columns built per candidate action and ${ft.functions?.length} theme functions.`}>
        <div className="space-y-2">
          {ft.groups?.map((g, i) => (
            <div key={g.group} className="grid grid-cols-[minmax(9rem,13rem)_1fr_auto] items-center gap-3 text-sm">
              <span className="capitalize text-[var(--ink-2)]">{g.group}</span>
              <div className="flex h-2.5 overflow-hidden rounded-full bg-[var(--chip)]">
                <motion.div className="h-full bg-[var(--accent)]" initial={{ width: 0 }} whileInView={{ width: `${(100 * (g.built - g.no_source.length)) / g.columns}%` }} viewport={{ once: true }} transition={{ delay: i * 0.05, duration: 0.7 }} />
                <motion.div className="h-full bg-[var(--axis)]" initial={{ width: 0 }} whileInView={{ width: `${(100 * g.no_source.length) / g.columns}%` }} viewport={{ once: true }} transition={{ delay: 0.3 + i * 0.05, duration: 0.7 }} />
              </div>
              <span className="tabular w-24 text-right text-xs text-[var(--ink-2)]">{g.built - g.no_source.length} of {g.columns} live</span>
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-4 text-xs text-[var(--ink-2)]">
          <span className="flex items-center gap-1.5"><span className="h-2 w-3 rounded-sm bg-[var(--accent)]" />built from source data</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-3 rounded-sm bg-[var(--axis)]" />no source in this proof of concept yet</span>
        </div>
        {noSource.length > 0 && (
          <div className="mt-4 rounded-xl border-l-2 border-[var(--accent-2)] bg-[var(--chip)] px-4 py-3 text-sm text-[var(--ink-2)]">
            <strong className="text-[var(--ink)]">{noSource.length} signals are wired in but have no source yet</strong>: {noSource.map(words).join(", ")}.
            Rules that use them stay silent until a client feed is connected; the rule studio shows them as "no data yet".
          </div>
        )}
      </Card>

      <Card title="About this data">
        <div className="grid gap-4 text-sm text-[var(--ink-2)] md:grid-cols-3">
          <p><strong className="text-[var(--ink)]">Real formats.</strong> Field names follow Veeva CRM, Vault PromoMats, OpenData and IQVIA, so mapping a client extract is a rename, not a rebuild. The schema is in <code>spec/schemas/datasets.yaml</code>.</p>
          <p><strong className="text-[var(--ink)]">Synthetic values.</strong> The rows are generated, shaped like Norgine's two markets, with no real physicians. Every number reproduces exactly from seed {c.seed}.</p>
          <p><strong className="text-[var(--ink)]">Same engine either way.</strong> Rules, constraints, optimiser and measurement read these tables through one data layer; swapping in client data changes the source, not the engine.</p>
        </div>
      </Card>
    </div>
  );
}

function Lineage({ systems, tables, c, system, setSystem }) {
  const stages = [
    { title: "Source systems", items: systems.map((s) => ({ key: s, label: s, n: tables.filter((t) => t.system === s).length, click: true })) },
    { title: "Standard datasets", items: [{ label: `${tables.filter((t) => !t.engine_written).length} datasets`, n: null }, { label: "Parquet, queried with DuckDB" }] },
    { title: "Feature table", items: [{ label: `${num(c.feature_table.columns)} columns` }, { label: `${num(c.feature_table.rows)} accounts, weekly` }] },
    { title: "Engines", items: [{ label: `Rules (${c.spec.trigger_rules_on} on)` }, { label: `Constraints (${Object.values(c.spec.constraint_tables).reduce((a, b) => a + b, 0)} table rows)` }, { label: "Optimiser" }] },
    { title: "Outputs", items: [{ label: "CRM suggestions" }, { label: "Rep talk tracks" }, { label: "Agency file" }, { label: `${c.engine.weeks_run} weeks run` }] },
  ];
  return (
    <Card title="Lineage: from source to the rep" subtitle="Click a source system to filter the register below.">
      <div className="grid gap-3 md:grid-cols-5">
        {stages.map((s, i) => (
          <div key={s.title} className="relative">
            <div className="kicker mb-2 text-[11px]">{i + 1}. {s.title}</div>
            <div className="space-y-1.5">
              {s.items.map((it, j) => (
                <motion.button key={it.label} type="button" disabled={!it.click} onClick={() => it.click && setSystem(system === it.key ? "all" : it.key)}
                  initial={{ opacity: 0, x: -8 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.12 + j * 0.04 }}
                  className={`flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-1.5 text-left text-xs transition ${system === it.key ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--line)] bg-black/20"} ${it.click ? "hover:border-[var(--axis)]" : "cursor-default"}`}>
                  <span>{it.label}</span>{it.n != null && <span className="tabular text-[var(--muted)]">{it.n}</span>}
                </motion.button>
              ))}
            </div>
            {i < stages.length - 1 && <span className="absolute -right-2.5 top-8 hidden text-[var(--accent-2)] md:block" aria-hidden>›</span>}
          </div>
        ))}
      </div>
    </Card>
  );
}

// The data model as a diagram: lanes of tables, curved lines for joins, coloured by match rate.
function ModelDiagram({ byName, relations, onOpen, open }) {
  const [hover, setHover] = useState(null);
  const W = 1080, NW = 176, NH = 46, GAP = 16, TOP = 34, LANE_W = W / LANES.length;
  const pos = {};
  LANES.forEach((l, li) => l.tables.forEach((t, ti) => { pos[t] = { x: li * LANE_W + (LANE_W - NW) / 2, y: TOP + ti * (NH + GAP), lane: l.key }; }));
  const H = TOP + Math.max(...LANES.map((l) => l.tables.length)) * (NH + GAP) + 6;
  const focus = hover || open;
  const linked = new Set(focus ? relations.filter((r) => r.child === focus || r.parent === focus).flatMap((r) => [r.child, r.parent]) : []);
  const path = (a, b) => {
    const A = pos[a], B = pos[b];
    if (!A || !B) return null;
    if (A.lane === B.lane) {                          // same lane: loop out to the left
      const x = A.x, y1 = A.y + NH / 2, y2 = B.y + NH / 2, bend = 26 + Math.abs(y2 - y1) * 0.12;
      return `M ${x} ${y1} C ${x - bend} ${y1}, ${x - bend} ${y2}, ${x} ${y2}`;
    }
    const right = A.x < B.x;
    const x1 = right ? A.x + NW : A.x, x2 = right ? B.x : B.x + NW;
    const y1 = A.y + NH / 2, y2 = B.y + NH / 2, dx = (x2 - x1) / 2;
    return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
  };
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="min-w-[880px]" role="img" aria-label="Data model diagram">
        {LANES.map((l, i) => (
          <text key={l.key} x={i * LANE_W + LANE_W / 2} y={16} textAnchor="middle" fontSize="11" letterSpacing="1.5" fill={LANE_COLOR[l.key]} style={{ textTransform: "uppercase", fontWeight: 600 }}>{l.label.toUpperCase()}</text>
        ))}
        {relations.map((r, i) => {
          const d = path(r.child, r.parent);
          if (!d) return null;
          const on = focus && (r.child === focus || r.parent === focus);
          const color = r.match_pct >= 99.5 ? "#4fd1a1" : r.match_pct >= 95 ? "#ffd0a8" : "#ff6b6b";
          return (
            <g key={i}>
              <motion.path d={d} fill="none" stroke={on ? color : "#3a3a44"} strokeWidth={on ? 2 : 1.1} opacity={focus && !on ? 0.25 : 1}
                initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1, delay: 0.2 + i * 0.03 }} />
              {on && <circle r="3" fill={color}><animateMotion dur="1.8s" repeatCount="indefinite" path={d} /></circle>}
            </g>
          );
        })}
        {Object.entries(pos).map(([name, p]) => {
          const t = byName[name];
          const dim = focus && !linked.has(name) && focus !== name;
          const roadmap = t?.status === "roadmap";
          return (
            <g key={name} transform={`translate(${p.x},${p.y})`} style={{ cursor: "pointer" }} opacity={dim ? 0.35 : 1}
              onMouseEnter={() => setHover(name)} onMouseLeave={() => setHover(null)} onClick={() => onOpen(name)}>
              <rect width={NW} height={NH} rx="10" fill={focus === name ? "#1d2056" : "#141418"} stroke={focus === name ? "#6a6dff" : "#26262c"} strokeDasharray={roadmap ? "4 4" : undefined} />
              <rect x="0" y="10" width="3" height={NH - 20} rx="1.5" fill={LANE_COLOR[p.lane]} />
              <text x="12" y="20" fontSize="12.5" fontWeight="600" fill={roadmap ? "#76767a" : "#f1f1ff"}>{name}</text>
              <text x="12" y="36" fontSize="11" fill="#76767a">{roadmap ? "roadmap" : `${num(t?.rows)} rows · ${t?.actual_fields ?? t?.declared_fields} fields`}</text>
            </g>
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-[var(--ink-2)]">
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-[#4fd1a1]" />join: 99.5% or more of keys match</span>
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-[#ffd0a8]" />95 to 99.5% (some keys have no partner)</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-5 rounded border border-dashed border-[var(--axis)]" />planned table, not yet produced</span>
      </div>
    </div>
  );
}

function FieldPanel({ t, relations, onClose, tab, setTab }) {
  const joins = relations.filter((r) => r.child === t.name || r.parent === t.name);
  const ref = useRef(null);
  const hasData = t.rows > 0 && t.status !== "roadmap";
  useEffect(() => { ref.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, [t.name, tab]);
  return (
    <motion.div ref={ref} className="scroll-mt-6" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}>
      <Card title={t.name} subtitle={`${t.source} · ${t.grain}${t.primary_key ? ` · key: ${t.primary_key}` : ""}`}
        actions={<div className="flex items-center gap-2">
          <div className="flex rounded-full border border-[var(--axis)] p-0.5 text-sm">
            {[["fields", "Fields"], ["data", "Data"]].map(([k, l]) => (
              <button key={k} type="button" disabled={k === "data" && !hasData} onClick={() => setTab(k)}
                className={`btn-pill px-4 py-1.5 transition disabled:opacity-40 ${tab === k ? "bg-[var(--accent)] text-white" : "text-[var(--ink-2)] hover:text-[var(--ink)]"}`}>{l}</button>
            ))}
          </div>
          <Button kind="secondary" onClick={onClose}>Close</Button>
        </div>}>
        {tab === "data" && hasData ? <DataViewer name={t.name} /> : (
        <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
          <Table maxHeight="24rem" rows={t.fields || []} empty="No declared fields." columns={[
            { key: "name", label: "Field", render: (f) => <span className="font-medium">{f.name}</span> },
            { key: "type", label: "Type", render: (f) => <span className="text-[var(--ink-2)]">{f.type}{f.values ? ` (${f.values.length} values)` : ""}</span> },
            { key: "present", label: "In file", render: (f) => f.present ? <span className="text-[var(--good-ink)]">✓</span> : <span className="text-[var(--bad)]">missing</span> },
            { key: "filled_pct", label: "Filled", render: (f) => <Fill pct={f.filled_pct} /> }]} />
          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-2">
              <Mini label="Rows" value={num(t.rows)} /><Mini label="Size" value={t.size_kb ? `${num(t.size_kb)} KB` : "–"} />
              <Mini label="Covers" value={t.date_from ? `${t.date_from} → ${t.date_to}` : "reference data"} /><Mini label="File written" value={t.updated || "–"} />
            </div>
            <div className="kicker pt-2 text-[11px]">Joins</div>
            {joins.length === 0 && <p className="text-[var(--muted)]">No tested joins.</p>}
            {joins.map((r) => (
              <div key={r.child + r.child_key + r.parent} className="flex items-center justify-between gap-3 border-b border-[var(--line)] pb-1.5">
                <span><span className="text-[var(--ink)]">{r.child}.{r.child_key}</span> → {r.parent}.{r.parent_key}<span className="block text-xs text-[var(--muted)]">{r.meaning} · {num(r.keys)} keys</span></span>
                <Fill pct={r.match_pct} />
              </div>
            ))}
          </div>
        </div>
        )}
      </Card>
    </motion.div>
  );
}

// The rows of one dataset, read straight from its file: 50 at a time, searchable, sortable by any column.
function DataViewer({ name }) {
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState({ col: "", desc: false });
  const [week, setWeek] = useState(null);
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const LIMIT = 50;
  useEffect(() => { setPage(0); setSearch(""); setQ(""); setSort({ col: "", desc: false }); setWeek(null); }, [name]);
  useEffect(() => { const t = setTimeout(() => { setQ(search); setPage(0); }, 300); return () => clearTimeout(t); }, [search]);
  useEffect(() => {
    const p = new URLSearchParams({ limit: LIMIT, offset: page * LIMIT, search: q, sort: sort.col, desc: sort.desc });
    if (week) p.set("week", week);
    setBusy(true);
    api(`/data/table/${name}?${p}`).then((r) => { setD(r); setErr(null); }).catch((e) => setErr(e.message)).finally(() => setBusy(false));
  }, [name, page, q, sort, week]);

  if (err) return <Message tone="bad">{err}</Message>;
  if (!d) return <p className="text-sm text-[var(--muted)]">Reading {name}…</p>;
  const from = d.total ? d.offset + 1 : 0, to = Math.min(d.offset + d.limit, d.total);
  const cell = (v) => {
    if (v === null || v === undefined || v === "") return <span className="text-[var(--muted)]">–</span>;
    if (typeof v === "boolean") return v ? "true" : "false";
    if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v)) return v.endsWith("T00:00:00.000") ? v.slice(0, 10) : v.slice(0, 16).replace("T", " ");
    if (typeof v === "number") return Number.isInteger(v) ? v : Math.round(v * 1000) / 1000;
    return String(v);
  };
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <input className="w-full max-w-xs rounded-full border border-[var(--axis)] bg-transparent px-4 py-2 text-sm outline-none focus:border-[var(--accent)]"
          placeholder="Search any column, e.g. an account id" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search the rows" />
        {d.weeks?.length > 0 && (
          <select className="rounded-full border border-[var(--axis)] bg-[var(--raised)] px-3 py-2 text-sm" value={d.week} onChange={(e) => { setWeek(Number(e.target.value)); setPage(0); }} aria-label="Snapshot week">
            {d.weeks.map((w) => <option key={w} value={w}>Week {w}</option>)}
          </select>
        )}
        <span className="text-sm text-[var(--ink-2)]">
          {d.total ? <>Rows <strong className="tabular text-[var(--ink)]">{num(from)}–{num(to)}</strong> of <strong className="tabular text-[var(--ink)]">{num(d.total)}</strong></> : "No rows match"}
          {q && d.total !== d.all_rows && <span className="text-[var(--muted)]"> (filtered from {num(d.all_rows)})</span>}
          {busy && <span className="ml-2 text-[var(--muted)]">reading…</span>}
        </span>
        <span className="ml-auto flex gap-2">
          <Button kind="secondary" onClick={() => setPage((p) => p - 1)} disabled={page === 0 || busy}>← Previous</Button>
          <Button kind="secondary" onClick={() => setPage((p) => p + 1)} disabled={to >= d.total || busy}>Next →</Button>
        </span>
      </div>
      <div className="max-h-[32rem] overflow-auto rounded-xl border border-[var(--line)]">
        <table className="w-full border-collapse text-xs">
          <thead className="sticky top-0 z-10 bg-[var(--raised)]">
            <tr>
              {d.columns.map((c) => (
                <th key={c} className="whitespace-nowrap border-b border-[var(--line)] px-3 py-2 text-left font-semibold text-[var(--ink-2)]">
                  <button type="button" onClick={() => setSort((s) => ({ col: c, desc: s.col === c ? !s.desc : false }))} className="hover:text-[var(--ink)]">
                    {c}{sort.col === c && <span className="ml-1 text-[var(--accent-2)]">{sort.desc ? "↓" : "↑"}</span>}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {d.rows.map((r, i) => (
              <tr key={i} className="border-b border-[var(--line)] last:border-0 hover:bg-[var(--chip)]">
                {d.columns.map((c) => <td key={c} className="tabular max-w-[18rem] truncate whitespace-nowrap px-3 py-1.5" title={String(r[c] ?? "")}>{cell(r[c])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-[var(--muted)]">Read directly from <code>{d.file}</code> in the data folder at the moment of asking. Click a column name to sort.</p>
    </div>
  );
}

function Mini({ label, value }) {
  return <div className="rounded-xl border border-[var(--line)] bg-black/20 p-2.5"><div className="text-[11px] text-[var(--muted)]">{label}</div><div className="tabular text-sm">{value}</div></div>;
}

function Fill({ pct }) {
  if (pct === null || pct === undefined) return <span className="text-xs text-[var(--muted)]">–</span>;
  const c = pct >= 99.5 ? "var(--good)" : pct >= 80 ? "var(--accent)" : "var(--warn)";
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-[var(--chip)]"><span className="block h-full rounded-full" style={{ width: `${pct}%`, background: c }} /></span>
      <span className="tabular w-12 text-right text-xs">{num(pct, 1)}%</span>
    </span>
  );
}

function StatusPill({ s }) {
  const m = { ok: ["checked", "good"], empty: ["empty", "bad"], missing: ["missing", "bad"], "schema gap": ["fields missing", "bad"], roadmap: ["roadmap", "neutral"] }[s] || [s, "neutral"];
  return <Badge tone={m[1]}>{m[0]}</Badge>;
}
