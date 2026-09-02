/** Click a node of the flow diagram: rename, remove or add a step through one precise
 *  revise request; change settings in place; or take it to a conversation. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { FlowNodePanel } from "./FlowNodePanel";
import type { Automation } from "../api";

afterEach(cleanup);

const TASK: Automation = {
  id: "task-1",
  title: "Morning news",
  instructions: "Search the web for AI news. Write a 5-bullet briefing. Save it as markdown.",
  schedule: "Every day at ~8:00 AM",
  schedule_raw: { kind: "cron", cron: "0 8 * * *" },
  workspace: "/u/news",
  agent: "cowork",
  enabled: true,
  next_run: null,
  last_run: null,
  last_status: null,
  run_count: 0,
  notify_on_completion: true,
  always_allowed: [{ entry: "e1", tool: "send_message", target: "slack:C9" }],
};

function mount(nodeId: string) {
  const props = {
    task: TASK,
    nodeId,
    models: ["a:b"],
    defaultModel: "a:b",
    onClose: vi.fn(),
    onRevise: vi.fn(async (_title: string, _comment: string) => ({ ok: true })),
    onPatch: vi.fn(async (_changes: Record<string, unknown>) => undefined),
    onRevoke: vi.fn(async (_entry: string) => undefined),
    onDiscuss: vi.fn((_prompt: string) => undefined),
  };
  render(<FlowNodePanel {...props} />);
  return props;
}

describe("FlowNodePanel", () => {
  it("renames a step with one precise request to Mimi", async () => {
    const p = mount("step-0");
    fireEvent.click(screen.getByTestId("flow-rename"));
    fireEvent.change(screen.getByTestId("flow-note-text"), { target: { value: "Scan yesterday's AI news" } });
    fireEvent.click(screen.getByTestId("flow-note-submit"));
    await waitFor(() => expect(p.onRevise).toHaveBeenCalled());
    const [title, comment] = p.onRevise.mock.calls[0];
    expect(title).toBe("Search the web");
    expect(comment).toContain('Rename the step "Search the web" to "Scan yesterday\'s AI news"');
  });

  it("removes a step only after a second click", async () => {
    const p = mount("step-1");
    fireEvent.click(screen.getByTestId("flow-remove"));
    expect(p.onRevise).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("flow-remove-confirm"));
    await waitFor(() => expect(p.onRevise).toHaveBeenCalled());
    expect(p.onRevise.mock.calls[0][1]).toContain('Remove the step "Write a 5-bullet"');
  });

  it("changes the schedule in place, without the model", async () => {
    const p = mount("trigger");
    fireEvent.change(screen.getByDisplayValue("Every day"), { target: { value: "weekdays" } });
    fireEvent.click(screen.getByTestId("flow-trigger-save"));
    await waitFor(() => expect(p.onPatch).toHaveBeenCalledWith({ cron: "0 8 * * 1-5" }));
    expect(p.onRevise).not.toHaveBeenCalled();
  });

  it("switches the finish note and revokes a grant in place", async () => {
    const p = mount("output");
    fireEvent.click(screen.getByTestId("flow-notify"));
    await waitFor(() => expect(p.onPatch).toHaveBeenCalledWith({ notify_on_completion: false }));
    cleanup();
    const q = mount("grant-0");
    fireEvent.click(screen.getByTestId("flow-revoke"));
    await waitFor(() => expect(q.onRevoke).toHaveBeenCalledWith("e1"));
  });

  it("can take the same context into a conversation instead", () => {
    const p = mount("step-2");
    fireEvent.change(screen.getByTestId("flow-note-text"), { target: { value: "make it a PDF" } });
    fireEvent.click(screen.getByTestId("flow-note-discuss"));
    const prompt = p.onDiscuss.mock.calls[0][0];
    expect(prompt).toContain('automation "Morning news"');
    expect(prompt).toContain("make it a PDF");
    expect(prompt).toContain("update_scheduled_task");
    expect(p.onClose).toHaveBeenCalled();
  });
});
