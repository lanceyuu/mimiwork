/** "Report this problem": confirm names what leaves the machine, then the sidecar mails it. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReportProblem } from "./ReportProblem";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function stub(ok: boolean) {
  const calls: any[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, body: JSON.parse(String(init?.body)) });
    return { ok: true, json: async () => ({ ok }) } as Response;
  }));
  return calls;
}

describe("ReportProblem", () => {
  it("asks first, then posts the error and where it happened", async () => {
    const calls = stub(true);
    render(<ReportProblem error="Error: engine exploded" context="connection" />);
    fireEvent.click(screen.getByTestId("report-problem"));
    expect(calls).toHaveLength(0); // nothing sent before confirming
    fireEvent.click(screen.getByText("Send report"));
    await waitFor(() => expect(screen.getByText(/Sent/)).toBeTruthy());
    expect(calls[0].url).toContain("/v1/report");
    expect(calls[0].body).toEqual({ error: "Error: engine exploded", context: "connection" });
  });

  it("points at the offline path when sending fails", async () => {
    stub(false);
    render(<ReportProblem error="x" context="c" />);
    fireEvent.click(screen.getByTestId("report-problem"));
    fireEvent.click(screen.getByText("Send report"));
    await waitFor(() => expect(screen.getByText(/Copy diagnostic log/)).toBeTruthy());
  });
});
