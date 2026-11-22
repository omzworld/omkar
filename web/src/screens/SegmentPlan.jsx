// Segment & plan: the quarterly baseline. Segment every physician, allocate last year's budget across segments
// (same total), apply the reps' adjustments, then watch the plan being delivered and reallocated week by week.
import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { api, eur, num, pct, words } from "../api";
import { Badge, Button, Card, Message, Stat, Table } from "../ui";
import { BAND_LADDER } from "../ladder.js";

const BANDS = ["high", "medium", "low"];
const ADOPT = ["early", "building", "established"];
const CH = { rep_visit: "Visits", remote_call: "Remote calls", rep_email: "Rep emails", marketing_email: "Marketing emails" };
const ADJ = { must_see: "Must see", no_access: "No access to reps", more_digital: "Prefers digital", left_practice: "Left the practice" };

export default function SegmentPlan({ go }) {
  const [cycle, setCycle] = useState(null);
  const [p, setP] = useState(null);
  const [err, setErr] = useState(null);
  const [tab, setTab] = useState("segment");
  useEffect(() => {
    setP(null);
    api(`/plan${cycle ? `?cycle=${cycle}` : ""}`).then((d) => { setP(d); setErr(null); }).catch((e) => setErr(e.message));
  }, [cycle]);

  if (err) return <Message tone="bad">{err}</Message>;
  if (!p) return <p className="text-sm text-[var(--muted)]">Segmenting physicians and building the quarter's plan…</p>;
  const tabs = [["segment", "1. Segment"], ["allocate", "2. Allocate"], ["adjust", "3. Adjust & approve"]];
  if (p.progress) tabs.push(["deliver", "Delivery so far"]);

  return (
    <div className="space-y-6">
      <header>
        <div className="kicker mb-2">Quarterly planning · quarter starting {p.cycle_start}</div>
        <h1 className="text-2xl font-semibold">Segment & plan</h1>
        <p className="mt-1 max-w-3xl text-[var(--ink-2)]">
          The baseline every week starts from. Physicians are segmented on potential, adoption and responsiveness;
          last year's touches are reallocated across segments with the <strong className="text-[var(--ink)]">same total budget</strong>;
          reps adjust their lists; the plan is approved for the quarter. Each week the engine may then move up to
          {" "}{Math.round(100 * p.settings.reallocation_cap)}% of planned touches to where they are needed most.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex rounded-full border border-[var(--axis)] p-0.5 text-sm">
          {tabs.map(([k, l]) => (
            <button key={k} type="button" onClick={() => setTab(k)}
              className={`btn-pill px-4 py-1.5 transition ${tab === k ? "bg-[var(--accent)] text-[var(--on-accent)]" : "text-[var(--ink-2)] hover:text-[var(--ink)]"}`}>{l}</button>
          ))}
        </div>
        {[1, 2].map((c) => (
          <button key={c} type="button" onClick={() => setCycle(c)}
            className={`btn-pill border px-3 py-1.5 text-sm ${p.cycle === c ? "border-[var(--accent-2)] text-[var(--accent-2)]" : "border-[var(--axis)] text-[var(--ink-2)]"}`}>Quarter {c}</button>
        ))}
        <Badge tone={p.saved ? "good" : "neutral"}>{p.saved ? "approved and in use" : "preview: approved when the pilot reaches this quarter"}</Badge>
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={tab + p.cycle} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }} className="space-y-6">
          {tab === "segment" && <SegmentTab p={p} />}
          {tab === "allocate" && <AllocateTab p={p} />}
          {tab === "adjust" && <AdjustTab p={p} go={go} />}
          {tab === "deliver" && <DeliverTab p={p} go={go} />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function SegmentTab({ p }) {
  const [pick, setPick] = useState(null);
  const [rows, setRows] = useState(null);
  useEffect(() => {
    if (!pick) return;
    setRows(null);
    api(`/plan/physicians?cycle=${p.cycle}&segment=${encodeURIComponent(pick)}`).then(setRows);
  }, [pick, p.cycle]);
  const cell = (b, a) => p.grid.find((g) => g.potential_band === b && g.adoption_band === a) || { physicians: 0 };
  const max = Math.max(...p.grid.map((g) => g.physicians), 1);
  const bestTotal = Object.values(p.best_channel).reduce((x, y) => x + y, 0);
  return (<>
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Stat label="Physicians segmented" value={num(p.physicians)} note="active physicians in both markets" />
      <Stat label="Segments" value="9" note="3 potential bands × 3 adoption stages" />
      <Stat label={p.cycle > 1 ? "Changed band since last quarter" : "Changed band from today's tiers"} value={num(p.moved)} note={`${pct((100 * p.moved) / p.physicians, 0)}, each with the reason`} />
      <Stat label="Respond best to visits" value={pct((100 * (p.best_channel.rep_visit || 0)) / bestTotal, 0)} note="from 12 months of their own responses" />
    </div>

    <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
      <Card title="Segment map" subtitle="Rows: potential (what the physician could prescribe). Columns: adoption (where they are in the journey). Colour shows how many; the small figure is their average responsiveness score. Click a segment to see its physicians.">
        <div className="grid grid-cols-[6rem_repeat(3,1fr)] gap-1.5 text-sm">
          <div />
          {ADOPT.map((a) => <div key={a} className="pb-1 text-center text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">{BAND_LADDER[a]}<div className="text-[10px] font-normal normal-case tracking-normal">({a})</div></div>)}
          {BANDS.map((b) => (<>
            <div key={b} className="flex items-center text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">{b} potential</div>
            {ADOPT.map((a) => {
              const c = cell(b, a), name = `${b[0].toUpperCase() + b.slice(1)} potential · ${a}`;
              const on = pick === name;
              return (
                <motion.button key={b + a} type="button" whileHover={{ scale: 1.03 }} onClick={() => setPick(on ? null : name)}
                  className={`rounded-xl border p-3 text-left transition ${on ? "border-[var(--accent-2)]" : "border-[var(--line)] hover:border-[var(--axis)]"}`}
                  style={{ background: `color-mix(in srgb, var(--accent) ${Math.round(100 * (0.08 + 0.5 * (c.physicians / max)))}%, transparent)` }}>
                  <div className="display tabular text-2xl font-bold">{num(c.physicians)}</div>
                  <div className="text-[11px] text-[var(--ink-2)]">responsiveness {num(c.responsiveness)}</div>
                </motion.button>
              );
            })}
          </>))}
        </div>
      </Card>

      <Card title="How each physician is scored" subtitle="Scores are 0 to 100 within the physician's market.">
        <div className="space-y-3 text-sm">
          {[["Potential", "Specialty weighting × the brick's market size × practice size against similar practices. Physician-level prescribing is not available in Europe, so potential is estimated from these."],
            ["Adoption", "Journey stage, from curiosity to advocacy, from the brand's segmentation."],
            ["Responsiveness", "The physician's own response rate over the last 12 months, shrunk towards their market's average when they have few touches. It also gives each physician's best channel."]].map(([t, d]) => (
            <div key={t} className="rounded-xl border border-[var(--line)] bg-[var(--well)] p-3"><div className="font-semibold text-[var(--accent-2)]">{t}</div><div className="mt-1 text-[var(--ink-2)]">{d}</div></div>
          ))}
          <p className="text-xs text-[var(--muted)]">A physician changes potential band only when their score is clearly past the boundary (5 points), so segments stay stable from one quarter to the next. Bands use the same shares as today's tiers (20%, 35%, 45%).</p>
        </div>
      </Card>
    </div>

    {pick && (
      <Card title={pick} subtitle="Physicians in this segment, highest potential first, with their planned touches this quarter.">
        {!rows ? <p className="text-sm text-[var(--muted)]">Loading…</p> : (
          <Table maxHeight="22rem" rows={rows} columns={[
            { key: "name", label: "Physician", render: (r) => <span>{r.name}<span className="block text-xs text-[var(--muted)]">{r.account_id} · tier {r.current_tier}</span></span> },
            { key: "potential_score", label: "Potential", num: true }, { key: "responsiveness_score", label: "Responsiveness", num: true },
            { key: "best_channel", label: "Best channel", render: (r) => words(r.best_channel) },
            { key: "rep_visit", label: "Visits", num: true }, { key: "rep_email", label: "Rep emails", num: true }, { key: "marketing_email", label: "Mkt emails", num: true }]} />
        )}
      </Card>
    )}

    <div className="grid gap-6 xl:grid-cols-[1fr_1.5fr]">
      <Card title="The brand's ZS potential against the computed potential" subtitle={`They agree for ${p.zs_agree_pct}% of physicians. The plan uses the ${p.potential_source === "zs" ? "ZS classification" : "computed potential"} (setting: planning.potential_source).`}>
        <Table rows={p.zs_vs_computed} columns={[{ key: "zs", label: "ZS potential", render: (r) => r.zs || r.index },
          ...BANDS.map((b) => ({ key: b, label: `computed ${b}`, num: true }))]} />
      </Card>
      <Card title="Today's tiers against the recommended bands" subtitle="Most physicians stay where they are; movers are one band at most.">
        <Table rows={p.tiers_vs_bands} columns={[{ key: "current_tier", label: "Today's tier", render: (r) => `Tier ${r.current_tier}` },
          ...BANDS.map((b) => ({ key: b, label: `${b} potential`, num: true }))]} />
      </Card>
      <Card title="Who changed band, and why" subtitle="The reason is the part of potential that best explains the move.">
        <Table maxHeight="20rem" rows={p.movers} columns={[
          { key: "name", label: "Physician", render: (r) => <span>{r.name}<span className="block text-xs text-[var(--muted)]">{r.market} · {r.account_id}</span></span> },
          { key: "move", label: "Move", render: (r) => <span className="whitespace-nowrap">Tier {r.current_tier} → <strong>{r.potential_band}</strong></span> },
          { key: "move_reason", label: "Why", wide: true }]} />
      </Card>
    </div>
  </>);
}

function AllocateTab({ p }) {
  const [channel, setChannel] = useState("rep_visit");
  const totals = p.by_channel.reduce((a, r) => ({ ly: a.ly + r.cost_last_year_eur, rec: a.rec + r.cost_recommended_eur }), { ly: 0, rec: 0 });
  const rows = p.by_segment.filter((r) => r.channel === channel).sort((a, b) => (b.change_pct ?? 0) - (a.change_pct ?? 0));
  const cap = 100 * p.settings.segment_change_cap;
  return (<>
    <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="glass relative overflow-hidden rounded-3xl p-6">
      <div className="kicker">Same budget as last year</div>
      <div className="mt-2 flex flex-wrap items-end gap-x-10 gap-y-3">
        <div><div className="text-sm text-[var(--ink-2)]">Last year's touches, one quarter</div><div className="display tabular text-4xl font-bold">{eur(totals.ly)}</div></div>
        <div className="pb-2 text-3xl text-[var(--accent-2)]">→</div>
        <div><div className="text-sm text-[var(--ink-2)]">Recommended plan</div><div className="display tabular text-4xl font-bold text-[var(--good-ink)]">{eur(totals.rec)}</div></div>
        <div className="pb-2 text-sm text-[var(--ink-2)]">Difference {pct((100 * (totals.rec - totals.ly)) / Math.max(totals.ly, 1), 1)}. Each channel keeps its total; only the split across segments changes.</div>
      </div>
    </motion.section>

    <Card title="Touches per channel, last year and recommended">
      <Table rows={p.by_channel} columns={[
        { key: "channel", label: "Channel", render: (r) => CH[r.channel] || words(r.channel) },
        { key: "last_year_touches", label: "Last year (per quarter)", num: true, render: (r) => num(r.last_year_touches) },
        { key: "recommended_touches", label: "Recommended", num: true, render: (r) => num(r.recommended_touches) },
        { key: "cost_last_year_eur", label: "Cost last year", num: true, render: (r) => eur(r.cost_last_year_eur) },
        { key: "cost_recommended_eur", label: "Cost recommended", num: true, render: (r) => eur(r.cost_recommended_eur) }]} />
    </Card>

    <Card title="Where the touches move" subtitle={`Each segment's touches against last year, both markets. A segment gains where one more touch is worth most (potential × responsiveness × stage value, with diminishing returns), within ±${cap}% of last year.`}
      actions={<div className="flex flex-wrap gap-1">{Object.keys(CH).map((c) => (
        <button key={c} type="button" onClick={() => setChannel(c)} className={`btn-pill border px-3 py-1 text-xs ${channel === c ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--axis)] text-[var(--ink-2)]"}`}>{CH[c]}</button>))}</div>}>
      <div className="space-y-2">
        {rows.map((r, i) => {
          const v = r.change_pct ?? 0, w = Math.min(Math.abs(v), cap) / cap * 50;
          const color = v >= 0 ? "var(--good)" : "var(--accent-2)";
          return (
            <div key={r.segment} className="grid grid-cols-[minmax(10rem,15rem)_1fr_7rem] items-center gap-3 text-sm">
              <span className="text-[var(--ink-2)]">{r.segment}</span>
              <div className="relative h-4">
                <div className="absolute inset-y-0 left-1/2 w-px bg-[var(--axis)]" />
                <motion.div className="absolute inset-y-0.5 rounded" style={{ background: color, [v >= 0 ? "left" : "right"]: "50%" }}
                  initial={{ width: 0 }} animate={{ width: `${w}%` }} transition={{ delay: i * 0.04, duration: 0.6 }} />
              </div>
              <span className="tabular text-right">{v >= 0 ? "+" : ""}{num(v, 1)}% <span className="text-xs text-[var(--muted)]">{num(r.last_year_touches)}→{num(r.recommended_touches)}</span></span>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-[var(--muted)]">Within each segment, touches follow last year's pattern blended with each physician's value ({Math.round(100 * p.settings.value_weight)}% value). High-potential physicians who were visited last year keep at least {p.settings.floor_high_potential_visits} visits a quarter. Email and remote calls are planned only where consent allows.</p>
    </Card>
  </>);
}

function AdjustTab({ p, go }) {
  const final = p.by_channel.reduce((a, r) => a + r.cost_final_eur, 0), rec = p.by_channel.reduce((a, r) => a + r.cost_recommended_eur, 0);
  return (<>
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {Object.entries(ADJ).map(([k, l]) => <Stat key={k} label={l} value={num(p.rep_input_counts[k] || 0)} note="rep adjustments this quarter" />)}
    </div>
    <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
      <Card title="Reps' adjustments" subtitle="Entered in the CRM before the quarter, each with a reason. They change individual physicians, not the method.">
        <Table maxHeight="24rem" rows={p.rep_inputs} empty="No adjustments for this quarter." columns={[
          { key: "name", label: "Physician", render: (r) => <span>{r.name}<span className="block text-xs text-[var(--muted)]">{r.account_id} · {r.user_id}</span></span> },
          { key: "adjustment", label: "Adjustment", render: (r) => <Badge tone={r.adjustment === "must_see" ? "accent" : "neutral"}>{ADJ[r.adjustment]}</Badge> },
          { key: "reason", label: "Reason", wide: true }]} />
      </Card>
      <Card title="The plan after adjustments" subtitle="What the reps' changes do to the recommended plan.">
        <Table rows={p.by_channel} columns={[
          { key: "channel", label: "Channel", render: (r) => CH[r.channel] },
          { key: "recommended_touches", label: "Recommended", num: true, render: (r) => num(r.recommended_touches) },
          { key: "final_touches", label: "After adjustments", num: true, render: (r) => num(r.final_touches) }]} />
        <p className="mt-3 text-sm text-[var(--ink-2)]">Cost of the final plan: <strong className="text-[var(--ink)]">{eur(final)}</strong> ({pct((100 * (final - rec)) / Math.max(rec, 1), 1)} against the recommendation, mostly visits turned into emails for physicians reps cannot see).</p>
        <div className="mt-4 rounded-xl border-l-2 border-[var(--accent-2)] bg-[var(--chip)] px-4 py-3 text-sm">
          <div className="font-semibold">{p.saved ? "Approved for the quarter" : "Ready for approval"}</div>
          <div className="mt-1 text-[var(--ink-2)]">{p.saved ? "This plan is what the reps and the agency follow this quarter. The weekly run starts from it." : "In the pilot, the plan is approved when the quarter starts, and every weekly run starts from it."}</div>
          <div className="mt-3"><Button onClick={() => go("week")}>See a week of the plan →</Button></div>
        </div>
      </Card>
    </div>
  </>);
}

function DeliverTab({ p, go }) {
  const g = p.progress;
  const rows = useMemo(() => [...g.by_segment].sort((a, b) => b.planned - a.planned), [g]);
  return (<>
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Stat label="Weeks into the quarter" value={`${g.weeks_in} of ${p.settings.cycle_weeks}`} note="test territories" />
      <Stat label="Planned touches delivered" value={num(g.delivered)} note={`of ${num(g.planned)} planned this quarter`} />
      <Stat label="Moved by the engine" value={num(g.moved)} note={`${pct((100 * g.moved) / Math.max(g.planned, 1), 1)} of the plan (cap ${Math.round(100 * p.settings.reallocation_cap)}%)`} />
      <Stat label="Postponed, still due" value={num(g.pending)} note="held by consent or asset rules this week" />
    </div>
    <Card title="Delivery by segment" subtitle="Delivered against where the plan should be by now (pro rata). Moved = planned touches the engine gave to another physician.">
      <Table rows={rows} columns={[
        { key: "segment", label: "Segment" }, { key: "planned", label: "Planned (quarter)", num: true },
        { key: "pro_rata", label: "Due by now", num: true }, { key: "delivered", label: "Delivered", num: true },
        { key: "swaps_out", label: "Moved out", num: true }, { key: "pending", label: "Postponed", num: true }]} />
      <div className="mt-4"><Button kind="secondary" onClick={() => go("results")}>See the results →</Button></div>
    </Card>
  </>);
}
