import { useEffect, useState } from "react";
import { connectMcpBacked, getConnectors, type Connector } from "../../api";
import { PILL_ACCENT, TAG_ACCENT } from "./ui";

// One-click pane for MCP-BACKED connectors (monday, asana, jira — §42): the sidecar
// runs a fully LOCAL OAuth flow against the vendor's hosted MCP server (DCR — no
// client secret, no broker, no MimiWork sign-in required). Poll until the card
// flips to connected, then close.
export function McpOneClick({ c, onConnected }: { c: Connector; onConnected: () => void }) {
  const [waiting, setWaiting] = useState(c.mcp_status === "authorizing");
  const [error, setError] = useState<string | null>(c.mcp_error || null);
  useEffect(() => {
    if (!waiting) return;
    const t = setInterval(async () => {
      try {
        const list = await getConnectors();
        const connector = list.find((x) => x.name === c.name);
        if (connector?.mcp_status === "authorizing") return;
        if (connector?.mcp_error) {
          setWaiting(false);
          setError(connector.mcp_error);
        } else if (connector?.connected) onConnected();
      } catch {
        /* keep polling */
      }
    }, 2000);
    return () => clearInterval(t);
  }, [waiting, c.name, onConnected]);
  const go = async () => {
    setError(null);
    setWaiting(true);
    try {
      const res = await connectMcpBacked(c.name);
      if (!res.ok) {
        setWaiting(false);
        setError(res.error || "Could not start sign-in. Try again.");
      }
    } catch {
      setWaiting(false);
      setError("Could not start sign-in. Try again.");
    }
  };
  return (
    <div className="px-5 py-4 space-y-3">
      <p className="text-[13px] text-muted">
        Opens {c.title} in your browser. Sign in and approve access there. The
        sign-in runs entirely on this computer.
      </p>
      <button
        className={PILL_ACCENT + " w-full !py-2"}
        data-testid="modal-mcp-one-click"
        onClick={go}
        disabled={waiting}
      >
        {waiting ? "Check your browser…" : `Connect ${c.title}`}
      </button>
      {error && <div className="text-[12.5px] text-danger">{error}</div>}
      <p className="text-[12px] text-faint text-center flex items-center justify-center gap-1.5">
        <span className={TAG_ACCENT}>Recommended</span> {c.title} tools load with your next message,
        tokens stay on this computer
      </p>
    </div>
  );
}

