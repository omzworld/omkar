// Scene 4: delivery. The Veeva payload and talk track for one rep, a key account manager's account brief,
// and the agency file. Nothing is sent anywhere.
import { useEffect, useState } from "react";
import { api, eur, num, words } from "../api";
import { Badge, Card, Field, inputClass, Message, Status, Table } from "../ui";

export default function Delivery({ pilot }) {
  const done = pilot?.completed_weeks ?? 0;
  const [week, setWeek] = useState(1);
  const [d, setD] = useState(null);
  const [user, setUser] = useState(null);
  const [u, setU] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [tab, setTab] = useState("rep");
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!done) return;
    setErr(null);
    api(`/delivery/${week}`).then((x) => {
      setD(x);
      const reps = x.reps_with_briefs.map((b) => b.user_id);
      setUser((cur) => (cur && reps.includes(cur) ? cur : reps[0]));
    }).catch((e) => setErr(e.message));
    api(`/delivery/${week}/accounts`).then(setAccounts).catch(() => setAccounts([]));
  }, [week, done]);
  useEffect(() => { if (user) api(`/delivery/${week}/user/${user}`).then(setU); }, [user, week]);

  if (!done) return <Empty />;
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Delivery</h1>
        <p className="mt-1 max-w-3xl text-[var(--ink-2)]">
          What the field and the agency receive each week. Nothing is sent: these are the records that would be
          written to Veeva CRM and the file that would go to the agency.
        </p>
      </header>
      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <div className="w-40"><Field label="Pilot week">
            <select className={inputClass} value={week} onChange={(e) => setWeek(Number(e.target.value))}>
              {Array.from({ length: done }, (_, i) => i + 1).map((w) => <option key={w} value={w}>Week {w}</option>)}
            </select>
          </Field></div>
          {d && <p className="text-sm text-[var(--ink-2)]">{num(d.payload_count)} Veeva suggestions · {d.reps_with_briefs.length} rep talk tracks · {num(d.agency_rows)} agency emails · week of {d.run_date}</p>}
        </div>
        <div className="mt-4 flex gap-1 border-b border-[var(--line)]" role="tablist">
          {[["rep", "Rep: Veeva suggestions and talk track"], ["kam", "Key account manager: account briefs"], ["agency", "Agency file"]].map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === id ? "border-[var(--accent)] font-medium" : "border-transparent text-[var(--ink-2)]"}`}>{label}</button>
          ))}
        </div>
      </Card>
      {err && <Message tone="bad">{err}</Message>}

      {tab === "rep" && d && (
        <div className="grid gap-6 xl:grid-cols-2">
          <Card title="Talk track" subtitle="What the rep reads on Monday morning, built from the data."
            actions={<div className="w-56"><select className={inputClass} value={user || ""} onChange={(e) => setUser(e.target.value)} aria-label="Rep">
              {d.reps_with_briefs.map((b) => <option key={b.user_id} value={b.user_id}>{b.user_id} ({b.territory_id})</option>)}
            </select></div>}>
            {u?.talk_track ? (<>
              <div className="mb-3 flex flex-wrap gap-2">
                <Badge>{u.talk_track.word_count} words</Badge>
                <Badge tone={u.talk_track.grounding_check_passed ? "good" : "bad"}>
                  {u.talk_track.grounding_check_passed ? "✓ every number checked against the data" : "✕ grounding check failed"}
                </Badge>
                <Badge>{u.talk_track.model_name === "template" ? "written from a template" : `written by ${u.talk_track.model_name}`}</Badge>
              </div>
              <div className="space-y-3 whitespace-pre-line text-sm leading-relaxed">{u.talk_track.prose}</div>
            </>) : <p className="text-sm text-[var(--muted)]">No talk track for this rep this week.</p>}
          </Card>
          <Card title="Veeva CRM suggestion records" subtitle="Validated against the suggestion schema before they are written.">
            {u?.payloads?.length ? (
              <pre className="max-h-[40rem] overflow-auto rounded-lg bg-[var(--chip)] p-3 text-xs leading-relaxed">{JSON.stringify(u.payloads, null, 2)}</pre>
            ) : <p className="text-sm text-[var(--muted)]">No suggestions for this rep this week.</p>}
          </Card>
        </div>
      )}

      {tab === "kam" && (
        accounts.length === 0 ? <Message>No key account manager actions this week.</Message> : (
          <div className="grid gap-6 xl:grid-cols-2">
            {accounts.map((a) => (
              <Card key={a.account_id} title={a.name} subtitle={`${a.account_id} · ${a.kam} · ${words(a.action)}, ${words(a.theme)} · expected return ${eur(a.expected_return)}`}>
                <p className="mb-3 text-sm">{a.reason}</p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <h3 className="mb-1 text-sm font-medium">The account's signal</h3>
                    <dl className="space-y-1 text-sm">
                      {Object.entries(a.signals).map(([k, v]) => (
                        <div key={k} className="flex justify-between gap-3"><dt className="text-[var(--ink-2)]">{k}</dt><dd className="tabular">{v === null ? "–" : num(v, 1)}</dd></div>
                      ))}
                    </dl>
                  </div>
                  <div>
                    <h3 className="mb-1 text-sm font-medium">Suggested sequence</h3>
                    <ol className="space-y-1 text-sm">{a.sequence.map((s) => <li key={s}>{s}</li>)}</ol>
                  </div>
                </div>
                {a.stakeholders.length > 0 && (<>
                  <h3 className="mb-1 mt-4 text-sm font-medium">Stakeholders</h3>
                  <p className="text-sm text-[var(--ink-2)]">{a.stakeholders.map((s) => `${s.name} (${words(s.role)}, ${s.stage})`).join(" · ")}</p>
                </>)}
                {a.key_messages.length > 0 && (<>
                  <h3 className="mb-1 mt-4 text-sm font-medium">Key messages</h3>
                  <ul className="list-disc pl-5 text-sm text-[var(--ink-2)]">{a.key_messages.map((m) => <li key={m}>{m}</li>)}</ul>
                </>)}
              </Card>
            ))}
          </div>
        )
      )}

      {tab === "agency" && d && (
        <Card title="Agency marketing email file" subtitle={`${num(d.agency_rows)} emails this week, in two send windows. First 50 shown.`}>
          <Table maxHeight="34rem" rows={d.agency} columns={[
            { key: "account_id", label: "Physician" }, { key: "market", label: "Market" },
            { key: "approved_document_id", label: "Approved asset" }, { key: "content_theme", label: "Theme", render: (r) => words(r.content_theme) },
            { key: "send_window", label: "Send window" },
            { key: "expected_return_eur", label: "Expected return", num: true, render: (r) => eur(r.expected_return_eur) },
            { key: "rule_ids", label: "Rule" }]} />
        </Card>
      )}
    </div>
  );
}

function Empty() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Delivery</h1>
      <Message>Nothing has been delivered yet. Run the pilot from the Feedback screen first.</Message>
      <Status passed={false} />
    </div>
  );
}
