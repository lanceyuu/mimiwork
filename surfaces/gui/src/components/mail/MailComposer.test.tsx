/** The draft editor: what it hands back as it is typed in, and what it refuses while busy. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

vi.mock("../../api", () => ({ reportProblem: vi.fn() }));

import type { MailDraft } from "../../api";
import { MailComposer, MailDraftError } from "./MailComposer";

afterEach(cleanup);

const REPLY: MailDraft = {
  id: "d1", thread_key: "k1", to: "Ana Lopez <ana@example.com>", cc: "", subject: "Re: Plan",
  body: "Ten works.", answers: "Ana Lopez <ana@example.com>", answers_id: "<1@x>", reply: true, interrupted: false, updated_at: 0,
};

function show(draft: MailDraft = REPLY, busy: "" | "writing" | "sending" = "", rewrite = true) {
  const calls = { onEdit: vi.fn(), onSend: vi.fn(), onDiscard: vi.fn(), onRewrite: vi.fn() };
  render(<MailComposer draft={draft} busy={busy} {...calls} onRewrite={rewrite ? calls.onRewrite : undefined} />);
  return calls;
}

describe("MailComposer", () => {
  it("hands back each field as it is typed", () => {
    const { onEdit } = show();
    fireEvent.change(screen.getByTestId("mail-draft-to"), { target: { value: "ben@example.com" } });
    fireEvent.change(screen.getByTestId("mail-draft-cc"), { target: { value: "cy@example.com" } });
    fireEvent.change(screen.getByTestId("mail-draft-subject"), { target: { value: "Friday" } });
    fireEvent.change(screen.getByTestId("mail-draft-body"), { target: { value: "Ten works. See you." } });
    expect(onEdit.mock.calls.map((call) => call[0])).toEqual([
      { to: "ben@example.com" }, { cc: "cy@example.com" }, { subject: "Friday" }, { body: "Ten works. See you." },
    ]);
    expect(screen.getByTestId("mail-composer").textContent).toContain("In reply to Ana Lopez");
  });

  it("sends once: the button and the fields are off from the press until the answer", () => {
    const { onSend } = show();
    fireEvent.click(screen.getByTestId("mail-send"));
    expect(onSend).toHaveBeenCalledTimes(1);
    cleanup();
    const sending = show(REPLY, "sending");
    const button = screen.getByTestId("mail-send");
    expect(button).toHaveProperty("disabled", true);
    expect(button.textContent).toBe("Sending…");
    fireEvent.click(button);
    expect(sending.onSend).not.toHaveBeenCalled();
    for (const id of ["mail-draft-to", "mail-draft-body", "mail-discard", "mail-rewrite"]) {
      expect(screen.getByTestId(id)).toHaveProperty("disabled", true);
    }
  });

  it("cannot send to nobody", () => {
    show({ ...REPLY, to: "  " });
    expect(screen.getByTestId("mail-send")).toHaveProperty("disabled", true);
  });

  it("warns when an earlier send of this draft was cut short, and still lets it be sent", () => {
    show({ ...REPLY, interrupted: true });
    expect(screen.getByTestId("mail-draft-interrupted").textContent).toContain("Check Sent before sending again");
    expect(screen.getByTestId("mail-send")).toHaveProperty("disabled", false);
  });

  it("asks Mimi to rewrite with the one line of guidance, for a reply only", () => {
    const { onRewrite } = show();
    fireEvent.change(screen.getByTestId("mail-rewrite-guidance"), { target: { value: "shorter" } });
    fireEvent.click(screen.getByTestId("mail-rewrite"));
    expect(onRewrite).toHaveBeenCalledWith("shorter");
    cleanup();
    show({ ...REPLY, reply: false, thread_key: "", answers: "" }, "", false);
    expect(screen.queryByTestId("mail-rewrite")).toBeNull();
    expect(screen.getByTestId("mail-composer").textContent).not.toContain("quoted beneath");
  });

  it("says when the reply answers an earlier message, and offers the user's own text back after a rewrite", () => {
    const onRestore = vi.fn();
    render(
      <MailComposer draft={REPLY} busy="" onEdit={vi.fn()} onSend={vi.fn()} onDiscard={vi.fn()} older onRestore={onRestore} />,
    );
    expect(screen.getByTestId("mail-draft-older").textContent).toContain("answers an earlier message");
    fireEvent.click(screen.getByTestId("mail-restore"));
    expect(onRestore).toHaveBeenCalledTimes(1);
    cleanup();
    show();
    expect(screen.queryByTestId("mail-draft-older")).toBeNull();
    expect(screen.queryByTestId("mail-restore")).toBeNull();
  });

  it("discards only after being asked", () => {
    const { onDiscard } = show();
    fireEvent.click(screen.getByTestId("mail-discard"));
    expect(onDiscard).not.toHaveBeenCalled();
    // The dialog's own Discard, not the one that opened it.
    const buttons = screen.getAllByRole("button", { name: "Discard" });
    fireEvent.click(buttons[buttons.length - 1]);
    expect(onDiscard).toHaveBeenCalledTimes(1);
  });
});

describe("MailDraftError", () => {
  it("shows the reason, and offers to report it only when Mimi was the one who failed", () => {
    render(<MailDraftError error="Mimi could not write the reply. No model is set up." report />);
    expect(screen.getByTestId("mail-draft-error").textContent).toContain("Mimi could not write the reply.");
    expect(screen.getByTestId("report-problem")).toBeTruthy();
    cleanup();
    render(<MailDraftError error="Add at least one recipient." report={false} />);
    expect(screen.queryByTestId("report-problem")).toBeNull();
    cleanup();
    const { container } = render(<MailDraftError error="" report={false} />);
    expect(container.textContent).toBe("");
  });
});
