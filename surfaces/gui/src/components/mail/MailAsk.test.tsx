/** Asking Mimi a question from Mail: what goes to the chat, and when nothing does. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const envelope = (uid: number, from: string, date: number, extra: object = {}) => ({
  folder: "INBOX", uid, message_id: `<${uid}@x>`, from, to: "me@example.com", cc: "",
  subject: "Plan for Friday", date, unread: false, has_attachments: false, ...extra,
});
const FIRST = envelope(1, "Ana Lopez <ana@example.com>", 1_800_000_000);
const REPLY = envelope(7, "Me <me@example.com>", 1_800_003_600, { folder: "Sent", to: "ana@example.com", cc: "li@example.com" });
const TEXT: Record<string, string> = { "INBOX/1": "Shall we meet on Friday at ten?", "Sent/7": "Ten works for me." };

const api = vi.hoisted(() => ({ getMailThread: vi.fn(), getMailMessage: vi.fn() }));
vi.mock("../../api", () => api);

import { MailAsk } from "./MailAsk";

beforeEach(() => {
  api.getMailThread.mockResolvedValue({
    ok: true, key: "k1", subject: "Plan for Friday", in_inbox: true, messages: [FIRST, REPLY],
    answer: { folder: "INBOX", uid: 1, message_id: "<1@x>" }, draft: "",
  });
  api.getMailMessage.mockImplementation(async (folder: string, uid: number) => ({
    ...(folder === "Sent" ? REPLY : FIRST), ok: true, thread_key: "k1", draft: "", html: "",
    text: TEXT[`${folder}/${uid}`],
    attachments: folder === "INBOX" ? [{ filename: "plan.pdf", content_type: "application/pdf", size: 10 }] : [],
  }));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const ask = (question: string) => {
  fireEvent.change(screen.getByTestId("mail-ask-question"), { target: { value: question } });
  fireEvent.click(screen.getByTestId("mail-ask-send"));
};

describe("MailAsk", () => {
  it("with nothing open, sends the question and tells Mimi to look in the mailbox", async () => {
    const onAsk = vi.fn();
    render(<MailAsk about={null} onAsk={onAsk} onClose={() => {}} />);
    expect(screen.getByTestId("mail-ask-scope").textContent).toContain("look in your mailbox");
    ask("  What did Ana ask me for last week?  ");
    await waitFor(() => expect(onAsk).toHaveBeenCalledTimes(1));
    const [text, attachments] = onAsk.mock.calls[0];
    expect(text).toBe("What did Ana ask me for last week?\n\nLook in my mailbox to answer this.");
    expect(attachments).toBeUndefined();
    // Nothing of the mailbox was read to ask about all of it.
    expect(api.getMailThread).not.toHaveBeenCalled();
  });

  it("with a conversation open, hands it over whole: each message with who wrote it, to whom and when", async () => {
    const onAsk = vi.fn();
    render(<MailAsk about={{ kind: "thread", key: "k1" }} onAsk={onAsk} onClose={() => {}} />);
    expect(screen.getByTestId("mail-ask-scope").textContent).toContain("the conversation you have open");
    ask("What do I still owe her?");
    await waitFor(() => expect(onAsk).toHaveBeenCalledTimes(1));
    const [text, attachments] = onAsk.mock.calls[0];
    // The question as typed: the conversation goes along beside it, not inside it.
    expect(text).toBe("What do I still owe her?");
    expect(attachments).toHaveLength(1);
    expect(attachments[0]).toMatchObject({ kind: "text", name: "Plan for Friday.txt", mime: "text/plain" });
    const body: string = attachments[0].text;
    expect(body.startsWith("Email conversation: Plan for Friday")).toBe(true);
    expect(body).toContain("From: Ana Lopez <ana@example.com>\nTo: me@example.com\nDate: 2027-01-15T08:00:00.000Z\nAttached: plan.pdf");
    expect(body).toContain("From: Me <me@example.com>\nTo: ana@example.com\nCc: li@example.com\nDate: 2027-01-15T09:00:00.000Z");
    // Oldest first, as it was written.
    expect(body.indexOf("Shall we meet on Friday at ten?")).toBeLessThan(body.indexOf("Ten works for me."));
  });

  it("hands over a message found by search by itself", async () => {
    const onAsk = vi.fn();
    render(<MailAsk about={{ kind: "message", folder: "INBOX", uid: 1 }} onAsk={onAsk} onClose={() => {}} />);
    ask("Summarise this");
    await waitFor(() => expect(onAsk).toHaveBeenCalledTimes(1));
    expect(onAsk.mock.calls[0][1][0].text).toContain("Shall we meet on Friday at ten?");
    expect(api.getMailThread).not.toHaveBeenCalled();
  });

  it("opens no chat when the conversation cannot be read, says why, and can be tried again", async () => {
    api.getMailMessage.mockResolvedValueOnce({ ok: false, error: "This message is no longer in the mailbox." });
    const onAsk = vi.fn();
    render(<MailAsk about={{ kind: "thread", key: "k1" }} onAsk={onAsk} onClose={() => {}} />);
    ask("What do I still owe her?");
    expect((await screen.findByTestId("mail-ask-error")).textContent).toContain("no longer in the mailbox");
    expect(onAsk).not.toHaveBeenCalled();
    // What was typed is still there.
    expect((screen.getByTestId("mail-ask-question") as HTMLTextAreaElement).value).toBe("What do I still owe her?");
    fireEvent.click(screen.getByTestId("mail-ask-send"));
    await waitFor(() => expect(onAsk).toHaveBeenCalledTimes(1));
  });

  it("asks nothing while the question is empty, and Enter asks while Shift and Enter starts a new line", async () => {
    const onAsk = vi.fn();
    render(<MailAsk about={null} onAsk={onAsk} onClose={() => {}} />);
    const box = screen.getByTestId("mail-ask-question");
    expect((screen.getByTestId("mail-ask-send") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onAsk).not.toHaveBeenCalled();
    fireEvent.change(box, { target: { value: "Anything from Ben?" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(onAsk).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() => expect(onAsk).toHaveBeenCalledTimes(1));
  });
});
