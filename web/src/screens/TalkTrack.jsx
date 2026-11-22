// The rep's weekly talk track as cards: the week at a glance, one card per doctor (why now, what to show, what to
// ask, what to leave, what follows), the bricks to watch and why these were chosen. The prose version is one click away.
import { useState } from "react";
import { motion } from "motion/react";
import { eur, num, words } from "../api";
import { Badge } from "../ui";
import { ladderOf } from "../ladder.js";

const KIND_ICON = { call: "◉", email: "✉", account: "▣", event: "◆", other: "•" };

function Glance({ label, value, note }) {
  return (
    <div className="rounded-xl bg-[var(--chip)] p-3">
      <div className="tabular text-2xl font-semibold">{value}</div>
      <div className="text-xs text-[var(--ink-2)]">{label}</div>
      {note && <div className="text-[11px] text-[var(--muted)]">{note}</div>}
    </div>
  );
}

function Block({ label, children }) {
  if (!children || (Array.isArray(children) && !children.length)) return null;
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--muted)]">{label}</div>
      <div className="mt-0.5 text-sm">{children}</div>
    </div>
  );
}

function DoctorCard({ s, pb, i }) {
  const [open, setOpen] = useState(i === 0);
  const kind = pb?.kind || (/email/.test(s.channel) ? "email" : "call");
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
      className="rounded-2xl border border-[var(--line)] bg-[var(--surface)]">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-start gap-3 p-4 text-left">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] text-sm font-semibold">{s.rank}</span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-semibold">{s.physician}</span>
            {s.account && <span className="text-xs text-[var(--muted)]">{s.account}</span>}
            {s.origin === "discovery" && <Badge tone="accent">found by discovery</Badge>}
          </span>
          <span className="mt-1 flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded-full bg-[var(--chip)] px-2 py-0.5 text-xs"><span className="mr-1">{KIND_ICON[kind]}</span>{s.channel} · {s.theme}</span>
            {pb?.stage && <span className="text-xs text-[var(--ink-2)]">{ladderOf(pb.stage)}{pb.barrier ? ` · concern: ${words(pb.barrier)}` : ""}</span>}
            <span className="text-xs text-[var(--muted)]">expected return {eur(s.expected_return_eur)}</span>
          </span>
          <span className="mt-1.5 block text-sm text-[var(--ink-2)]"><span className="font-medium text-[var(--ink)]">Why now: </span>{s.reason}</span>
        </span>
        <span className={`text-xs text-[var(--muted)] transition-transform ${open ? "rotate-90" : ""}`}>▶</span>
      </button>
      {open && (
        <div className="grid gap-4 border-t border-[var(--line)] p-4 sm:grid-cols-2">
          <div className="space-y-3">
            <Block label="Objective">{pb?.objective}</Block>
            <Block label={kind === "email" ? "Email" : "Show, in this order"}>
              {kind === "email" ? (pb && <span>{pb.subject && <span className="font-medium">“{pb.subject}”</span>}<span className="block text-xs text-[var(--ink-2)]">{pb.sender}</span><span className="block text-xs text-[var(--ink-2)]">Send: {pb.send_window}</span></span>)
                : pb?.slides?.length ? <ol className="list-decimal space-y-0.5 pl-4">{pb.slides.map((x) => <li key={x}>{x}</li>)}</ol> : null}
            </Block>
            <Block label="Key message">{s.key_message && <span className="text-[var(--ink-2)]">{s.key_message}</span>}</Block>
          </div>
          <div className="space-y-3">
            <Block label="Ask">{(pb?.ask || s.listen_for) && <span className="italic">“{pb?.ask || s.listen_for}”</span>}</Block>
            <Block label="If they object">{pb?.objection}</Block>
            <Block label="Leave behind">{pb?.leave_behind}</Block>
            <Block label="Then">{(pb?.after || pb?.follow_up)?.length > 0 && <ul className="list-disc space-y-0.5 pl-4">{(pb.after || pb.follow_up).map((x) => <li key={x}>{x}</li>)}</ul>}</Block>
          </div>
        </div>
      )}
    </motion.div>
  );
}

export default function TalkTrack({ tt, playbooks = {} }) {
  const [prose, setProse] = useState(false);
  const b = tt.structured || {};
  const lw = b.last_week || {};
  const sug = b.suggestions || [];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={tt.grounding_check_passed ? "good" : "bad"}>{tt.grounding_check_passed ? "✓ every number checked against the data" : "✕ grounding check failed"}</Badge>
        <Badge>{tt.model_name === "template" ? "written from a template" : `written by ${tt.model_name}`}</Badge>
        <button type="button" className="ml-auto text-xs text-[var(--ink-2)] underline" onClick={() => setProse(!prose)}>{prose ? "Show as cards" : "Show as text"}</button>
      </div>
      {prose ? <div className="space-y-3 whitespace-pre-line text-sm leading-relaxed">{tt.prose}</div> : (<>
        <section>
          <h3 className="mb-2 text-sm font-medium">Last week at a glance{b.territory ? ` · ${b.territory.name}` : ""}</h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Glance label="visits completed" value={num(lw.visits_completed ?? 0)} />
            <Glance label="suggestions acted on" value={num(lw.suggestions_accepted ?? 0)} note={`${lw.suggestions_dismissed ?? 0} dismissed${lw.most_common_dismiss_reason ? `, mostly ${lw.most_common_dismiss_reason}` : ""}`} />
            <Glance label="rep emails opened" value={`${lw.rep_emails_opened ?? 0}/${lw.rep_emails_sent ?? 0}`} note="opened of sent" />
            <Glance label="webinar attendees" value={num(lw.webinar_attendees ?? 0)} />
          </div>
        </section>
        <section>
          <h3 className="mb-2 text-sm font-medium">This week: {sug.length ? `${sug.length} doctor${sug.length === 1 ? "" : "s"} to act on` : "follow your call plan"}</h3>
          <div className="space-y-3">{sug.slice(0, 5).map((s, i) => <DoctorCard key={s.suggestion_id || i} s={s} pb={playbooks[s.suggestion_id]} i={i} />)}</div>
          {sug.length > 5 && <p className="mt-2 text-xs text-[var(--muted)]">{sug.length - 5} more in your Veeva list.</p>}
        </section>
        {b.bricks?.length > 0 && (
          <section>
            <h3 className="mb-2 text-sm font-medium">Your bricks · last three months against the three before</h3>
            <div className="flex flex-wrap gap-2">
              {b.bricks.map((br) => {
                const c = br.change_pct;
                const steady = c < 0 ? br.months_declining >= 2 : br.months_growing >= 2;
                return (
                  <div key={br.brick_id} className="rounded-xl border border-[var(--line)] px-3 py-2">
                    <div className="text-xs text-[var(--ink-2)]">{br.brick_id}</div>
                    <div className="tabular text-lg font-semibold" style={{ color: c == null ? undefined : c < -1 ? "var(--bad)" : c > 1 ? "var(--good-ink)" : undefined }}>{c == null ? "–" : `${c > 0 ? "+" : ""}${num(c, 1)}%`}</div>
                    <div className="text-[11px] text-[var(--muted)]">{c == null ? "no data" : Math.abs(c) < 1 ? "flat" : steady ? "steady trend" : "one-off so far"}</div>
                  </div>
                );
              })}
            </div>
          </section>
        )}
        {b.held && (
          <p className="text-xs text-[var(--ink-2)]">Why these: the highest expected return of {num(b.candidates_in_territory)} doctors and accounts considered in your territory. Held back: {b.held.cadence} by cadence, {b.held.capacity} by capacity, {b.held.consent} by consent.{b.discovery_note ? ` ${b.discovery_note}` : ""}</p>
        )}
      </>)}
    </div>
  );
}
