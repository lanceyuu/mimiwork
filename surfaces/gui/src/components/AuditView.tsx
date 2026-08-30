import { useEffect, useState } from "react";
import {
  getAudit,
  getSettings,
  qualitatiCredits,
  type AuditEvent,
  type QualitatiCreditRow,
  type QualitatiCredits,
} from "../api";
import { PanelHead } from "./IntegrationsView";
import { EdgeRadar } from "./EdgeRadar";
import { FiveABars } from "./FiveABars";
import { useT } from "../i18n";
import type { EdgeProfile, FiveAProfile } from "../timesaved";

// Activity — connector/browser tool history, restructured onto the IntegrationsView page shell
// (centered panel + PanelHead + cards), replacing the legacy `page-view` layout. Read-only:
// filterable, with sanitized arguments.
const CARD = "rounded-xl2 border border-line bg-panel";
const INPUT = "px-3 py-1.5 rounded-lg border border-line bg-paper text-[13px] text-ink outline-none focus:border-accent";
const BTN_ACCENT = "text-[12.5px] px-3 py-1.5 rounded-lg bg-accent text-white shrink-0";

export function AuditView() {
  const t = useT();
  const [edge, setEdge] = useState<EdgeProfile | null>(null);
  const [fiveA, setFiveA] = useState<FiveAProfile | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [sessionFilter, setSessionFilter] = useState("");
  const [connectorFilter, setConnectorFilter] = useState("");
  const [toolFilter, setToolFilter] = useState("");
  const [credits, setCredits] = useState<QualitatiCredits | null>(null);

  const refresh = () =>
    getAudit({
      limit: 150,
      session_id: sessionFilter.trim() || undefined,
      connector: connectorFilter.trim() || undefined,
      tool: toolFilter.trim() || undefined,
    })
      .then(setEvents)
      .catch(() => setEvents([]));

  useEffect(() => {
    refresh();
    // Credits load alongside the tool log; signed out, the panel simply isn't there.
    qualitatiCredits(50)
      .then(setCredits)
      .catch(() => setCredits(null));
  }, []);

  // The EDGE profile rides on the same settings payload as the hours-saved total,
  // so the shape and the hours can never disagree — they are the same minutes.
  useEffect(() => {
    getSettings()
      .then((s) => {
        setEdge(s.time_saved?.edge ?? null);
        setFiveA(s.time_saved?.five_a ?? null);
      })
      .catch(() => {
        setEdge(null);
        setFiveA(null);
      });
  }, []);

  return (
    <main className="flex-1 min-w-0 flex bg-paper">
      <div className="flex-1 min-w-0 overflow-y-auto hairline-scroll">
        <div className="max-w-4xl mx-auto px-7 py-6">
          <PanelHead
            title="Activity"
            sub="What ran, and what it cost. Tool arguments are sanitized before storage."
          />

          {edge?.ready && (
            <div className={CARD + " p-4 mb-4"} data-testid="edge-panel">
              <div className="text-[13px] font-medium text-ink mb-0.5">
                {t("How Mimi helps you")}
              </div>
              <div className="text-[11.5px] text-muted mb-3">
                {t("The same hours, grouped by the kind of help — the EDGE framework.")}
              </div>
              <EdgeRadar edge={edge} />
              {edge.pillars?.some((p) => p.key === "Growth" && p.percent === 0) && (
                <div className="text-[11px] text-faint mt-3 pt-2.5 border-t border-line">
                  {t("Growth reads zero for almost everyone here, and that is not a failing: it means new offerings and revenue, which happen in the market rather than in a tool's log.")}
                </div>
              )}
            </div>
          )}

          {fiveA?.ready && (
            <div className={CARD + " p-4 mb-4"} data-testid="fivea-panel">
              <div className="text-[13px] font-medium text-ink mb-0.5">
                {t("How you work with Mimi")}
              </div>
              <div className="text-[11.5px] text-muted mb-3">
                {t("Your turns placed on the Five A's continuum — by what they did, not what they were called.")}
              </div>
              <FiveABars five={fiveA} />
            </div>
          )}

          {credits?.ok && <CreditsPanel credits={credits} />}

          <div className="flex items-center gap-2 flex-wrap mb-4">
            <input className={INPUT} placeholder="session id" value={sessionFilter} onChange={(e) => setSessionFilter(e.target.value)} />
            <input className={INPUT} placeholder="connector" value={connectorFilter} onChange={(e) => setConnectorFilter(e.target.value)} />
            <input className={INPUT} placeholder="tool" value={toolFilter} onChange={(e) => setToolFilter(e.target.value)} />
            <button className={BTN_ACCENT} onClick={refresh}>
              Filter
            </button>
          </div>

          {events.length === 0 ? (
            <div className={CARD + " p-4 text-[13px] text-muted"}>No audit events yet.</div>
          ) : (
            <div className="space-y-2">
              {events.map((ev) => (
                <AuditRow ev={ev} key={ev.id} />
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

// Credit spend, straight from the QualiTaTi ledger — the account's own record of
// what MimiWork billed, so the number here is the number on the bill. Which pool
// paid matters: a team pool and this month's points both expire, purchased
// credits don't, and the gateway spends them in that order.
function CreditsPanel({ credits }: { credits: QualitatiCredits }) {
  const [open, setOpen] = useState(false);
  const rows = credits.entries ?? [];
  const balance = credits.balance;
  return (
    <div className={CARD + " p-4 mb-4"} data-testid="activity-credits">
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className="text-[13px] font-medium text-ink">Credits</span>
        <span className="text-[12.5px] text-muted">
          <b className="text-ink">{credits.spent ?? 0}</b> spent over{" "}
          {credits.calls ?? 0} {credits.calls === 1 ? "call" : "calls"}
          {credits.free_calls ? ` · ${credits.free_calls} free` : ""}
        </span>
        {balance && (
          <span className="text-[12.5px] text-muted ml-auto" data-testid="activity-credits-balance">
            <b className="text-ink">{balance.available}</b> left
            {balance.team_points ? ` · team ${balance.team_points}` : ""}
            {balance.monthly_points ? ` · monthly ${balance.monthly_points}` : ""}
            {balance.lifelong_credits ? ` · lifelong ${balance.lifelong_credits}` : ""}
          </span>
        )}
      </div>
      {rows.length === 0 ? (
        <div className="text-[11.5px] text-faint mt-1.5">
          Nothing billed yet — Mimi Puppy answers free every day.
        </div>
      ) : (
        <>
          <button
            className="text-[11.5px] text-muted hover:text-ink mt-1.5"
            onClick={() => setOpen((v) => !v)}
            data-testid="activity-credits-toggle"
          >
            {open ? "Hide" : "Show"} the last {rows.length}
          </button>
          {open && (
            <div className="mt-2 space-y-1">
              {rows.map((row, i) => (
                <CreditRow row={row} key={row.id ?? i} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function CreditRow({ row }: { row: QualitatiCreditRow }) {
  const paid = [
    row.team_points ? `${row.team_points} team` : "",
    row.monthly_points ? `${row.monthly_points} monthly` : "",
    row.lifelong_credits ? `${row.lifelong_credits} lifelong` : "",
  ]
    .filter(Boolean)
    .join(" + ");
  return (
    <div className="flex items-baseline gap-2 text-[11.5px] flex-wrap">
      <span className="font-mono text-ink w-14 shrink-0">
        {row.free ? "free" : `${row.credits}`}
      </span>
      <span className="text-muted">{row.model || row.route || "model call"}</span>
      <span className="text-faint">
        {row.tokens_in.toLocaleString()} in · {row.tokens_out.toLocaleString()} out
        {row.estimated ? " · estimated" : ""}
      </span>
      {paid && <span className="text-faint">{paid}</span>}
      <span className="text-faint ml-auto">{row.at ?? ""}</span>
    </div>
  );
}

function AuditRow({ ev }: { ev: AuditEvent }) {
  return (
    <div className={CARD + " p-3.5"}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-[12.5px] font-medium text-ink">{ev.tool}</span>
        <span className="text-[11.5px] text-faint">
          {ev.connector || "tool"} · {ev.stage || ev.status || "event"} · {ev.timestamp}
        </span>
      </div>
      <div className="text-[11.5px] text-muted mt-0.5">
        session {ev.session_id || "-"} {ev.approval ? `· ${ev.approval}` : ""} {ev.status ? `· ${ev.status}` : ""}
      </div>
      {ev.resource && <div className="text-[11.5px] text-faint mt-0.5">resource: {ev.resource}</div>}
      {ev.args && Object.keys(ev.args).length > 0 && (
        <div className="font-mono text-[11.5px] text-muted mt-1.5 break-words">{formatAuditArgs(ev.args)}</div>
      )}
      {(ev.reason || ev.result_preview) && (
        <div className="text-[11.5px] text-faint mt-1">{ev.reason || ev.result_preview}</div>
      )}
    </div>
  );
}

function formatAuditArgs(args: Record<string, any>) {
  return Object.entries(args)
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join("  ");
}
