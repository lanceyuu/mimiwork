import { Component, type ErrorInfo, type ReactNode } from "react";

// The last line of defence: a render crash must never leave a blank window.
//
// This exists because of a real failure. When the local server rejected the app's
// token — a sidecar whose token rotated, a version mismatch, anything that returns
// an error body instead of the expected payload — an unguarded read of that body
// threw during render and React unmounted the whole tree. The user got a white
// screen: no message, no retry, nothing to report. Guarding the individual reads is
// right and was done, but it is whack-a-mole; this makes the whole CLASS non-fatal.
//
// What it deliberately does NOT do is hide the problem. The message is shown, not
// swallowed, and it names the most likely cause in plain words, because "MimiWork
// can't reach its own server" is something a user can act on and report.

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Keep it in the console for a bug report; the panel stays plain-language.
    console.error("MimiWork crashed while rendering:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div
        style={{
          height: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--paper, #FAFAFA)",
          color: "var(--ink, #111111)",
          fontFamily: '"Avenir Next", "Nunito", "Helvetica Neue", Arial, sans-serif',
          padding: 24,
        }}
        data-testid="error-boundary"
      >
        <div style={{ maxWidth: 460 }}>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>
            MimiWork hit an unexpected error
          </div>
          <div style={{ fontSize: 13, color: "var(--muted, #555)", lineHeight: 1.5 }}>
            This is usually the app losing touch with its own local server — it can
            happen after an update, when the app is newer than the server still
            running. Reopening MimiWork normally fixes it. Your files and
            conversations are on disk and are not affected.
          </div>
          <pre
            style={{
              fontSize: 11,
              color: "var(--muted, #555)",
              background: "var(--panel, #fff)",
              border: "1px solid var(--line, #E6E6E6)",
              borderRadius: 8,
              padding: "8px 10px",
              marginTop: 12,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {String(this.state.error?.message || this.state.error)}
          </pre>
          <button
            style={{
              marginTop: 12,
              padding: "8px 16px",
              borderRadius: 999,
              border: "none",
              background: "var(--accent, #0D9488)",
              color: "#fff",
              fontSize: 13,
              cursor: "pointer",
            }}
            onClick={() => window.location.reload()}
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
