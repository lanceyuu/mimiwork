import { useState } from "react";
import { reportProblem } from "../api";
import { useT } from "../i18n";
import { ConfirmDialog } from "./ConfirmDialog";

// "Report this problem" next to an error: one click, one confirmation naming exactly what
// leaves the machine, then the sidecar mails it to the QualiTaTi team (owner ask 2026-09-21).
export function ReportProblem({ error, context }: { error: string; context: string }) {
  const t = useT();
  const [state, setState] = useState<"idle" | "asking" | "sending" | "sent" | "failed">("idle");
  const send = async () => {
    setState("sending");
    const res = await reportProblem(error, context).catch(() => ({ ok: false }));
    setState(res.ok ? "sent" : "failed");
  };
  if (state === "sent") return <span className="ml-2 text-faint">{t("Sent — thank you.")}</span>;
  if (state === "failed")
    return <span className="ml-2 text-faint">{t("Couldn't send. Settings → Copy diagnostic log works offline.")}</span>;
  return (
    <>
      <button className="btn ml-2" data-testid="report-problem" disabled={state === "sending"} onClick={() => setState("asking")}>
        {state === "sending" ? t("Sending…") : t("Report this problem")}
      </button>
      {state === "asking" && (
        <ConfirmDialog
          title={t("Send this error to the QualiTaTi team?")}
          body={t("What goes: the error, your app version and platform, your QualiTaTi username if signed in, and the last part of the app log. Nothing from your conversation.")}
          confirmLabel={t("Send report")}
          destructive={false}
          onConfirm={() => void send()}
          onCancel={() => setState("idle")}
        />
      )}
    </>
  );
}
