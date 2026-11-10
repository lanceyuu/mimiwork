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
}));
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
  api.getMailThread.mockResolvedValue({ ok: true, key: "k1", subject: "Plan for Friday", in_inbox: true, messages: [ENVELOPE] });
  api.getMailMessage.mockResolvedValue({ ...ENVELOPE, ok: true, thread_key: "k1", html: "<p>Shall we?</p>", text: "Shall we?", attachments: [] });
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
});
