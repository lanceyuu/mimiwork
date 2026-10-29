import { useEffect, useState } from "react";
import {
  connectConnector,
  type Connector,
} from "../../api";
import { ConnectorBadge } from "../../connectors/ConnectorIcon";
import { ConnectSetup } from "../ManageTabs";
import { PILL_LINE } from "./ui";
import { McpOneClick } from "./McpOneClick";

// The ONE place a connection gets added (UX-DECISIONS §21): the detail page's header
// button (or the list's Connect pill) opens this sheet. Connectors with two connect
// modes get a One click | Manual pill switcher; single-mode connectors render their
// existing ConnectSetup directly (Gmail's managed flow skips the modal entirely).

const INPUT =
  "w-full px-3 py-2 rounded-lg border border-line bg-paper text-[13px] text-ink outline-none focus:border-accent";

export function AddConnectionModal({
  c,
  title,
  onClose,
  onChanged,
}: {
  c: Connector;
  title?: string; // e.g. "Add a workspace" — defaults to "Connect {title}"
  onClose: () => void;
  onChanged: () => void;
}) {
  // MCP-backed one-click (§42): local OAuth against the vendor's hosted MCP server —
  // with manual fields alongside (jira, asana) it's a second mode; alone (monday)
  // it IS the connect flow.
  const mcpBacked = !!c.mcp;
  // The broker-based one-clicks (Slack/GitHub/HubSpot/generic) were removed with
  // the hosted relay; only the fully-local MCP OAuth keeps a
  // one-click pane. Slack keeps its guided manual (Socket Mode) flow.
  const twoModes = mcpBacked && c.fields.length > 0;
  const [pane, setPane] = useState<"one" | "manual">("one");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40" data-testid="add-connection-modal">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div
        // Tall forms (Email/IMAP has eight fields) must scroll inside the card: without a
        // height cap the SMTP fields sat below the window edge and nothing scrolled
        // (owner hit on a laptop, 2026-09-09).
        className="absolute left-1/2 top-[7vh] -translate-x-1/2 w-[480px] max-w-[calc(100vw-2rem)] max-h-[86vh] overflow-y-auto bg-panel rounded-2xl border border-line shadow-2xl"
        role="dialog"
        aria-label={title || `Connect ${c.title}`}
      >
        <div className="flex items-center gap-3 px-5 pt-5">
          <ConnectorBadge connector={c} size={34} title={c.title} />
          <div className="flex-1 font-semibold text-[16px] tracking-tight">
            {title || `Connect ${c.title}`}
          </div>
          <button className="text-faint hover:text-ink text-[18px] leading-none" onClick={onClose} title="Close">
            ×
          </button>
        </div>

        {twoModes ? (
          <>
            <div className="px-5 pt-4">
              <div className="inline-flex rounded-full p-0.5 bg-paper text-[12.5px] font-medium">
                {(["one", "manual"] as const).map((p) => (
                  <button
                    key={p}
                    data-testid={`modal-pane-${p}`}
                    className={
                      "px-3.5 py-1 rounded-full " +
                      (pane === p ? "bg-panel shadow-sm text-ink border border-line" : "text-muted")
                    }
                    onClick={() => setPane(p)}
                  >
                    {p === "one" ? "One click" : "Manual"}
                  </button>
                ))}
              </div>
            </div>
            {pane === "one" ? (
              <McpOneClick c={c} onConnected={() => { onChanged(); onClose(); }} />
            ) : c.name === "slack" ? (
              <SlackManual onConnected={() => { onChanged(); onClose(); }} />
            ) : (
              <div className="px-1.5 pb-2">
                <ConnectSetup c={c} onConnected={() => { onChanged(); onClose(); }} manualOnly />
              </div>
            )}
          </>
        ) : mcpBacked ? (
          /* MCP-backed with no manual fields (monday): one-click IS the flow. */
          <McpOneClick c={c} onConnected={() => { onChanged(); onClose(); }} />
        ) : c.name === "slack" ? (
          <SlackManual onConnected={() => { onChanged(); onClose(); }} />
        ) : (
          <div className="px-1.5 pb-2">
            {/* Existing combined setup (managed button + manual fields) for everything else. */}
            <ConnectSetup c={c} onConnected={() => { onChanged(); onClose(); }} />
          </div>
        )}
      </div>
    </div>
  );
}

// One-click pane for generic managed connectors (Notion, Attio, …): sign in
// with the service in the browser; each consent lands as its own account.




function SlackManual({ onConnected }: { onConnected: () => void }) {
  const [bot, setBot] = useState("");
  const [app, setApp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true);
    setError(null);
    const res = await connectConnector("slack", { bot_token: bot.trim(), app_token: app.trim() });
    setBusy(false);
    if (res.ok) onConnected();
    else setError(res.error || "could not connect");
  };
  return (
    <div className="px-5 py-4 space-y-3">
      <ol className="list-decimal pl-4 text-[13px] text-muted space-y-1">
        <li>Create an app at api.slack.com/apps</li>
        <li>Enable Socket Mode, add bot scopes, install it to your workspace</li>
        <li>Paste both tokens</li>
      </ol>
      <input className={INPUT} type="password" placeholder="Bot token · xoxb-…" value={bot} spellCheck={false} onChange={(e) => setBot(e.target.value)} />
      <input className={INPUT} type="password" placeholder="App token · xapp-…" value={app} spellCheck={false} onChange={(e) => setApp(e.target.value)} />
      <button className={PILL_LINE + " w-full !py-2"} onClick={submit} disabled={busy || !bot.trim() || !app.trim()}>
        {busy ? "Validating…" : "Connect"}
      </button>
      {error && <div className="text-[12.5px] text-danger">{error}</div>}
      <p className="text-[12px] text-warnInk text-center">
        One mode at a time — this pauses any relay workspaces.
      </p>
    </div>
  );
}
