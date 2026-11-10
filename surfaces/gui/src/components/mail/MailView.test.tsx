/** The Mail section: what it shows when nothing is connected, the list, and its actions. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const STATUS = {
  ok: true, connected: true, address: "me@example.com", syncing: false, revision: 1,
  last_sync: 0, last_error: "", can_archive: true, can_bin: true,
};
const ROW = { key: "k1", subject: "Plan for Friday", sender: "Ana <ana@example.com>", date: 0, unread: false, count: 1, has_attachments: false };
const ENVELOPE = {
  folder: "INBOX", uid: 1, message_id: "<1@x>", from: "Ana <ana@example.com>", to: "me@example.com",
  cc: "", subject: "Plan for Friday", date: 0, unread: false, has_attachments: false,
};

const api = vi.hoisted(() => ({
  getMailStatus: vi.fn(),
  getMailThreads: vi.fn(),
  syncMail: vi.fn(),
  archiveMailThread: vi.fn(),
  binMailThread: vi.fn(),
  markMailThread: vi.fn(),
  searchMail: vi.fn(),
  getMailThread: vi.fn(),
  getMailMessage: vi.fn(),
  markMailMessageRead: vi.fn(),
  saveMailAttachment: vi.fn(),
  getMailComments: vi.fn(),
  putMailComments: vi.fn(),
  getMailDrafts: vi.fn(),
  createMailDraft: vi.fn(),
  getMailDraft: vi.fn(),
  updateMailDraft: vi.fn(),
  deleteMailDraft: vi.fn(),
  writeMailReply: vi.fn(),
  sendMailDraft: vi.fn(),
  reportProblem: vi.fn(),
}));
const DRAFT = {
  id: "d1", thread_key: "", to: "ben@example.com", cc: "", subject: "Lunch on Thursday", body: "Noon?",
  answers: "", answers_id: "", reply: false, interrupted: false, updated_at: 0,
};
vi.mock("../../api", () => api);

import { MailView } from "./MailView";

beforeEach(() => {
  api.getMailStatus.mockResolvedValue(STATUS);
  api.getMailThreads.mockResolvedValue([ROW]);
  api.syncMail.mockResolvedValue({ ok: true });
  api.archiveMailThread.mockResolvedValue({ ok: true });
  api.binMailThread.mockResolvedValue({ ok: true });
  api.markMailThread.mockResolvedValue({ ok: true });
  api.markMailMessageRead.mockResolvedValue({ ok: true });
  api.getMailThread.mockResolvedValue({
    ok: true, key: "k1", subject: "Plan for Friday", in_inbox: true, messages: [ENVELOPE],
    answer: { folder: "INBOX", uid: 1, message_id: "<1@x>" }, draft: "",
  });
  api.getMailMessage.mockResolvedValue({ ...ENVELOPE, ok: true, thread_key: "k1", draft: "", html: "<p>Shall we?</p>", text: "Shall we?", attachments: [] });
  api.getMailComments.mockResolvedValue({ ok: true, comments: [], note: "" });
  api.putMailComments.mockResolvedValue({ ok: true });
  api.getMailDrafts.mockResolvedValue([]);
  api.createMailDraft.mockResolvedValue({ ok: true, draft: { ...DRAFT, id: "d2", to: "", subject: "", body: "" } });
  api.getMailDraft.mockImplementation(async (id: string) => ({ ok: true, draft: { ...DRAFT, id } }));
  api.updateMailDraft.mockResolvedValue({ ok: true });
  api.deleteMailDraft.mockResolvedValue({ ok: true });
  api.sendMailDraft.mockResolvedValue({ ok: true, note: "" });
  api.searchMail.mockResolvedValue({ ok: true, results: [{ ...ENVELOPE, folder: "Archive", uid: 9, subject: "Invoice January" }] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("MailView", () => {
  it("explains what to connect when no mailbox is connected, and syncs nothing", async () => {
    api.getMailStatus.mockResolvedValue({ ...STATUS, connected: false, address: "" });
    const onOpenConnectors = vi.fn();
    render(<MailView onOpenConnectors={onOpenConnectors} />);
    expect((await screen.findByTestId("mail-not-connected")).textContent).toContain("Connectors, Email");
    fireEvent.click(screen.getByTestId("mail-open-connectors"));
    expect(onOpenConnectors).toHaveBeenCalled();
    expect(api.syncMail).not.toHaveBeenCalled();
    expect(api.getMailThreads).not.toHaveBeenCalled();
  });

  it("lists the inbox and starts one sync when it opens", async () => {
    render(<MailView onOpenConnectors={() => {}} />);
    expect((await screen.findByTestId("mail-row")).textContent).toContain("Plan for Friday");
    expect(screen.getByTestId("mail-sync-line").textContent).toContain("me@example.com");
    await waitFor(() => expect(api.syncMail).toHaveBeenCalledTimes(1));
  });

  it("shows why the last sync failed while still listing what it has", async () => {
    api.getMailStatus.mockResolvedValue({ ...STATUS, last_error: "could not reach the mail server: offline" });
    render(<MailView onOpenConnectors={() => {}} />);
    expect((await screen.findByTestId("mail-error")).textContent).toContain("could not reach the mail server");
    expect(screen.getByTestId("mail-row")).toBeTruthy();
  });

  it("archiving takes the conversation out of the list at once", async () => {
    render(<MailView onOpenConnectors={() => {}} />);
    fireEvent.click(await screen.findByTestId("mail-row"));
    api.getMailThreads.mockResolvedValue([]);
    fireEvent.click(await screen.findByTestId("mail-archive"));
    await waitFor(() => expect(screen.queryByTestId("mail-row")).toBeNull());
    expect(api.archiveMailThread).toHaveBeenCalledWith("k1");
    expect(screen.queryByTestId("mail-reader")).toBeNull();
  });

  it("a refused archive brings the conversation back with the reason on its row", async () => {
    api.archiveMailThread.mockResolvedValue({ ok: false, error: "this mailbox cannot move mail" });
    render(<MailView onOpenConnectors={() => {}} />);
    fireEvent.click(await screen.findByTestId("mail-row"));
    fireEvent.click(await screen.findByTestId("mail-archive"));
    expect((await screen.findByRole("alert")).textContent).toBe("this mailbox cannot move mail");
    expect(screen.getByTestId("mail-row").textContent).toContain("Plan for Friday");
  });

  it("moving to the bin and marking unread each call their own action", async () => {
    render(<MailView onOpenConnectors={() => {}} />);
    fireEvent.click(await screen.findByTestId("mail-row"));
    fireEvent.click(await screen.findByTestId("mail-unread"));
    await waitFor(() => expect(api.markMailThread).toHaveBeenCalledWith("k1", false));
    expect(screen.getByTestId("mail-row")).toBeTruthy(); // still listed: it was only marked

    fireEvent.click(screen.getByTestId("mail-row"));
    api.getMailThreads.mockResolvedValue([]);
    fireEvent.click(await screen.findByTestId("mail-bin"));
    await waitFor(() => expect(screen.queryByTestId("mail-row")).toBeNull());
    expect(api.binMailThread).toHaveBeenCalledWith("k1");
  });

  it("offers Archive and Bin only when the mailbox can move mail", async () => {
    api.getMailStatus.mockResolvedValue({ ...STATUS, can_archive: false, can_bin: false });
    render(<MailView onOpenConnectors={() => {}} />);
    fireEvent.click(await screen.findByTestId("mail-row"));
    expect(await screen.findByTestId("mail-unread")).toBeTruthy();
    expect(screen.queryByTestId("mail-archive")).toBeNull();
    expect(screen.queryByTestId("mail-bin")).toBeNull();
  });

  it("search lists what the server found, opens a result alone, and goes back to the inbox", async () => {
    render(<MailView onOpenConnectors={() => {}} />);
    await screen.findByTestId("mail-row");
    fireEvent.change(screen.getByTestId("mail-search"), { target: { value: "invoice" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() => expect(screen.getByTestId("mail-row").textContent).toContain("Invoice January"));
    expect(api.searchMail).toHaveBeenCalledWith("invoice");
    expect(screen.getByTestId("mail-row").textContent).toContain("Archive");

    fireEvent.click(screen.getByTestId("mail-row"));
    await waitFor(() => expect(api.getMailMessage).toHaveBeenCalledWith("Archive", 9));
    await waitFor(() => expect(api.markMailMessageRead).toHaveBeenCalledWith("Archive", 9));
    expect(screen.queryByTestId("mail-archive")).toBeNull();

    fireEvent.click(screen.getByTestId("mail-search-clear"));
    await waitFor(() => expect(screen.getByTestId("mail-row").textContent).toContain("Plan for Friday"));
  });

  it("a search that fails shows the reason in place of results", async () => {
    api.searchMail.mockResolvedValue({ ok: false, error: "the mail server could not search this folder" });
    render(<MailView onOpenConnectors={() => {}} />);
    await screen.findByTestId("mail-row");
    fireEvent.change(screen.getByTestId("mail-search"), { target: { value: "invoice" } });
    fireEvent.submit(screen.getByRole("search"));
    expect((await screen.findByTestId("mail-search-error")).textContent).toContain("could not search");
    expect(screen.queryByTestId("mail-list-empty")).toBeNull();
    expect(screen.queryByTestId("mail-row")).toBeNull();
  });

  it("an answer to a search that was left does not replace the inbox", async () => {
    let answer: (reply: unknown) => void = () => {};
    api.searchMail.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    render(<MailView onOpenConnectors={() => {}} />);
    await screen.findByTestId("mail-row");
    fireEvent.change(screen.getByTestId("mail-search"), { target: { value: "invoice" } });
    fireEvent.submit(screen.getByRole("search"));
    fireEvent.change(screen.getByTestId("mail-search"), { target: { value: "" } });
    fireEvent.submit(screen.getByRole("search"));
    answer({ ok: true, results: [{ ...ENVELOPE, folder: "Archive", uid: 9, subject: "Invoice January" }] });
    await waitFor(() => expect(screen.getByTestId("mail-row").textContent).toContain("Plan for Friday"));
    expect(screen.queryByText("Search results")).toBeNull();
  });

  it("lists unsent drafts under their own tab, with how many there are", async () => {
    api.getMailDrafts.mockResolvedValue([DRAFT]);
    render(<MailView onOpenConnectors={() => {}} />);
    await screen.findByTestId("mail-row");
    await waitFor(() => expect(screen.getByTestId("mail-tab-drafts").textContent).toBe("Drafts1"));
    fireEvent.click(screen.getByTestId("mail-tab-drafts"));
    expect(screen.getByTestId("mail-row").textContent).toContain("ben@example.com");
    expect(screen.getByTestId("mail-row").textContent).toContain("Lunch on Thursday");
    fireEvent.click(screen.getByTestId("mail-tab-all"));
    expect(screen.getByTestId("mail-row").textContent).toContain("Plan for Friday");
  });

  it("New message opens an empty draft in the editor, under Drafts", async () => {
    render(<MailView onOpenConnectors={() => {}} />);
    await screen.findByTestId("mail-row");
    fireEvent.click(screen.getByTestId("mail-new"));
    expect(await screen.findByTestId("mail-composer")).toBeTruthy();
    expect(api.createMailDraft).toHaveBeenCalledWith();
    expect(api.getMailDraft).toHaveBeenCalledWith("d2");
    expect(screen.getByTestId("mail-tab-drafts").getAttribute("aria-pressed")).toBe("true");
  });

  it("a draft sent from the editor closes it and says so", async () => {
    api.getMailDrafts.mockResolvedValue([DRAFT]);
    render(<MailView onOpenConnectors={() => {}} />);
    await screen.findByTestId("mail-row");
    fireEvent.click(screen.getByTestId("mail-tab-drafts"));
    fireEvent.click(await screen.findByTestId("mail-row"));
    api.getMailDrafts.mockResolvedValue([]);
    fireEvent.click(await screen.findByTestId("mail-send"));
    expect((await screen.findByTestId("mail-notice")).textContent).toBe("Sent.");
    expect(api.sendMailDraft).toHaveBeenCalledWith("d1");
    expect(screen.queryByTestId("mail-composer")).toBeNull();
    await waitFor(() => expect(screen.getByTestId("mail-list-empty").textContent).toBe("No drafts."));
  });

  it("a send the server refuses keeps the draft open with the reason", async () => {
    api.getMailDrafts.mockResolvedValue([DRAFT]);
    api.sendMailDraft.mockResolvedValue({ ok: false, error: "The mail server did not accept the message: mailbox unavailable" });
    render(<MailView onOpenConnectors={() => {}} />);
    await screen.findByTestId("mail-row");
    fireEvent.click(screen.getByTestId("mail-tab-drafts"));
    fireEvent.click(await screen.findByTestId("mail-row"));
    fireEvent.click(await screen.findByTestId("mail-send"));
    expect((await screen.findByTestId("mail-draft-error")).textContent).toContain("mailbox unavailable");
    expect(screen.getByTestId("mail-draft-body")).toHaveProperty("value", "Noon?");
    expect(screen.queryByTestId("report-problem")).toBeNull();
  });

  it("a send that ends after the user has moved on leaves what they are reading open", async () => {
    api.getMailDrafts.mockResolvedValue([DRAFT]);
    let answer: (reply: unknown) => void = () => {};
    api.sendMailDraft.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    render(<MailView onOpenConnectors={() => {}} />);
    await screen.findByTestId("mail-row");
    fireEvent.click(screen.getByTestId("mail-tab-drafts"));
    fireEvent.click(await screen.findByTestId("mail-row"));
    fireEvent.click(await screen.findByTestId("mail-send"));
    await waitFor(() => expect(api.sendMailDraft).toHaveBeenCalled());
    // The user does not wait: they go and read a conversation.
    fireEvent.click(screen.getByTestId("mail-tab-all"));
    fireEvent.click(await screen.findByTestId("mail-row"));
    await screen.findByTestId("mail-subject");
    answer({ ok: false, error: "The mail server did not accept the message: 550 mailbox unavailable" });
    // The editor that would have shown the reason is gone, so the section says it.
    const notice = await screen.findByTestId("mail-notice");
    expect(notice.textContent).toBe(
      "Your message was not sent. The mail server did not accept the message: 550 mailbox unavailable It is under Drafts.",
    );
    expect(notice.getAttribute("role")).toBe("alert");
    expect(screen.getByTestId("mail-subject")).toBeTruthy();
  });

  it("a reply draft opens with its conversation while that is in the inbox, and alone once it is not", async () => {
    const reply = { ...DRAFT, id: "d3", thread_key: "k1", reply: true, answers: "Ana <ana@example.com>", subject: "Re: Plan for Friday" };
    api.getMailDrafts.mockResolvedValue([reply]);
    api.getMailThread.mockResolvedValue({
      ok: true, key: "k1", subject: "Plan for Friday", in_inbox: true, messages: [ENVELOPE],
      answer: { folder: "INBOX", uid: 1, message_id: "<1@x>" }, draft: "d3",
    });
    render(<MailView onOpenConnectors={() => {}} />);
    await screen.findByTestId("mail-row");
    fireEvent.click(screen.getByTestId("mail-tab-drafts"));
    fireEvent.click(await screen.findByTestId("mail-row"));
    expect(await screen.findByTestId("mail-subject")).toBeTruthy();
    expect(await screen.findByTestId("mail-composer")).toBeTruthy();
    expect(screen.getByTestId("mail-comments")).toBeTruthy();
    cleanup();

    api.getMailThreads.mockResolvedValue([]); // archived since
    render(<MailView onOpenConnectors={() => {}} />);
    fireEvent.click(await screen.findByTestId("mail-tab-drafts"));
    fireEvent.click(await screen.findByTestId("mail-row"));
    expect(await screen.findByTestId("mail-draft-pane")).toBeTruthy();
    expect(await screen.findByTestId("mail-composer")).toBeTruthy();
    expect(screen.queryByTestId("mail-comments")).toBeNull();
  });
});
