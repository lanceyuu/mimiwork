import { useEffect, useState } from "react";
import {
  disconnectConnector,
  getConnectors,
  getSlackStatus,
  type Connector,
  type SlackStatus,
} from "../../api";
import { ConnectorBadge } from "../../connectors/ConnectorIcon";
import { AllowlistBlock, ConnectorTools, ListeningSessionsBlock, UnauthorizedBlock } from "../ManageTabs";
import { AccountsDetail } from "./AccountsDetail";
import { AddConnectionModal } from "./AddConnectionModal";
import { AvailableDetail } from "./AvailableDetail";
import { CalendarDetail } from "./CalendarDetail";
import { ConnectorsList } from "./ConnectorsList";
import { GithubDetail } from "./GithubDetail";
import { GmailDetail } from "./GmailDetail";
import { HubSpotDetail } from "./HubSpotDetail";
import { SlackDetail } from "./SlackDetail";
import { GRP } from "./ui";

// Connectors surface = LIST ⇄ per-connector DETAIL SUBPAGE (UX-DECISIONS §21). The
// Integrations sub-nav never grows per-connector items; detail pages live behind a
// `‹ Connectors` breadcrumb. Connectors without a bespoke page get GenericDetail so
// every connected row navigates from day one.

export interface DetailProps {
  c: Connector;
  slack: SlackStatus | null; // live Slack health (relay/sign-in/tokens); null elsewhere
  onChanged: () => void;
}

// Bespoke pages register here; everything else gets GenericDetail below.
const DETAIL_PAGES: Partial<Record<string, (p: DetailProps) => JSX.Element>> = {
  slack: (p) => <SlackDetail {...p} />,
  gmail: (p) => <GmailDetail {...p} />,
  google_calendar: (p) => <CalendarDetail {...p} />,
  hubspot: (p) => <HubSpotDetail {...p} />,
  github: (p) => <GithubDetail {...p} />,
  // Generic multi-account connectors (accounts.py layer) share one page.
  notion: (p) => <AccountsDetail {...p} />,
  attio: (p) => <AccountsDetail {...p} />,
  posthog: (p) => <AccountsDetail {...p} />,
  mixpanel: (p) => <AccountsDetail {...p} />,
  amplitude: (p) => <AccountsDetail {...p} />,
  apollo: (p) => <AccountsDetail {...p} />,
  hunter: (p) => <AccountsDetail {...p} />,
};

export function ConnectorsSection() {
  const [detail, setDetail] = useState<string | null>(null);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [slack, setSlack] = useState<SlackStatus | null>(null);

  const refresh = () => {
    getConnectors().then(setConnectors).catch(() => setConnectors([]));
    getSlackStatus().then(setSlack).catch(() => setSlack(null));
  };
  useEffect(() => {
    refresh();
    // Poll: recent senders/parked arrive over time; sign-in + managed connects finish
    // in the system browser and surface on the next tick.
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  if (detail) {
    const c = connectors.find((x) => x.name === detail);
    const Page = DETAIL_PAGES[detail];
    return (
      <div>
        <button
          className="text-[13px] text-accent mb-3"
          data-testid="connectors-breadcrumb"
          onClick={() => setDetail(null)}
        >
          ‹ Connectors
        </button>
        {!c ? (
          <div className="text-[13px] text-muted">Loading…</div>
        ) : !c.connected ? (
          /* Pre-connect page (§38). When a connect completes, the poll flips
             c.connected and this same route re-renders as the connected page. */
          <AvailableDetail c={c} onChanged={refresh} />
        ) : Page && c.mode !== "mcp" ? (
          <Page c={c} slack={slack} onChanged={refresh} />
        ) : (
          <GenericDetail
            c={c}
           
            slack={slack}
            onChanged={refresh}
            onGone={() => setDetail(null)}
          />
        )}
      </div>
    );
  }

  return (
    <ConnectorsList
      connectors={connectors}
     
      slack={slack}
      onOpen={setDetail}
      onChanged={refresh}
    />
  );
}

// Fallback detail page: status header + the connector's existing config blocks
// (tools; allow-list/parked/listening for two-way) + Disconnect. Bespoke pages
// (Slack/Gmail/HubSpot) replace this one connector at a time.
function GenericDetail({
  c,
  slack: _slack,
  onChanged,
  onGone,
}: DetailProps & { onGone: () => void }) {
  const [connecting, setConnecting] = useState(false);
  return (
    <div>
      <div className="flex items-center gap-3.5 mb-5">
        <ConnectorBadge connector={c} size={44} title={c.title} />
        <div className="min-w-0 flex-1">
          <h2 className="text-[20px] font-semibold tracking-tight leading-tight">{c.title}</h2>
          <div className="text-[12.5px] text-muted flex items-center gap-1.5">
            <span className={"w-2 h-2 rounded-full " + (c.mcp_status === "authorizing" || c.mcp_error || !c.enabled ? "bg-warnInk" : "bg-ok")} />
            {c.mcp_status === "authorizing" ? "Signing in…" : c.mode === "mcp"
                ? c.mcp_error ? "Connection needs attention" : !c.enabled ? "Disabled" : "Connected through MCP"
                : c.account || (c.auth === "none" ? "Built in" : "Connected")}
          </div>
        </div>
        {c.mode === "mcp" && (
          <button className="text-[12.5px] text-accent shrink-0" onClick={() => setConnecting(true)}>
            Reconnect
          </button>
        )}
        {c.auth !== "none" && (
          <button
            className="text-[12.5px] text-danger/80 hover:text-danger shrink-0"
            onClick={async () => {
              await disconnectConnector(c.name);
              onChanged();
              onGone();
            }}
          >
            Disconnect
          </button>
        )}
      </div>

      {c.mcp_error && <div className="text-[12.5px] text-danger mb-3">{c.mcp_error}</div>}
      {connecting && <AddConnectionModal c={c} onChanged={onChanged} onClose={() => setConnecting(false)} />}

      {c.mode === "mcp" && !c.tools.length ? (
        <p className="text-[13px] text-muted">This server's tools load automatically with your next message.</p>
      ) : (
        <div className={GRP}>
          <ConnectorTools c={c} onChanged={onChanged} />
        </div>
      )}

      {c.two_way && (
        <div className={GRP + " mt-4"}>
          <AllowlistBlock c={c} onChanged={onChanged} />
          <UnauthorizedBlock c={c} onChanged={onChanged} />
          {/* Channel subscriptions are a chat-platform concept — GitHub is two_way via the
              relay (inbound mentions) but has no channels. */}
          {c.channels && <ListeningSessionsBlock c={c} />}
        </div>
      )}
    </div>
  );
}
