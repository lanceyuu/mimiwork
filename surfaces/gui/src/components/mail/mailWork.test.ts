/** Saving as it is typed: what reaches the sidecar, in what order, and what never does. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  createMailDraft: vi.fn(),
  deleteMailDraft: vi.fn(),
  getMailComments: vi.fn(),
  getMailDraft: vi.fn(),
  putMailComments: vi.fn(),
  sendMailDraft: vi.fn(),
  updateMailDraft: vi.fn(),
  writeMailReply: vi.fn(),
}));
vi.mock("../../api", () => api);

import { useAutosave, useMailComments, useMailDraft } from "./mailWork";

const DRAFT = {
  id: "d1", thread_key: "k1", to: "ana@example.com", cc: "", subject: "Re: Plan", body: "",
  answers: "Ana <ana@example.com>", answers_id: "<1@x>", reply: true, interrupted: false, updated_at: 0,
};
const ANSWER = { folder: "INBOX", uid: 1, message_id: "<1@x>" };
const OK = { ok: true };
const FAILED = { ok: false, error: "Could not reach MimiWork. Try again." };

/** A call that answers only when told to, so a test can decide the order of answers. */
function held() {
  const waiting: Array<(reply: unknown) => void> = [];
  const call = vi.fn(() => new Promise((resolve) => waiting.push(resolve)));
  return { call, answer: (index: number, reply: unknown) => waiting[index](reply), count: () => waiting.length };
}

beforeEach(() => {
  api.getMailDraft.mockResolvedValue({ ok: true, draft: DRAFT });
  api.getMailComments.mockResolvedValue({ ok: true, comments: [], note: "" });
  api.putMailComments.mockResolvedValue(OK);
  api.updateMailDraft.mockResolvedValue(OK);
  api.deleteMailDraft.mockResolvedValue(OK);
  api.sendMailDraft.mockResolvedValue({ ok: true, note: "" });
  api.writeMailReply.mockResolvedValue({ ok: true, text: "MIMI'S TEXT" });
  api.createMailDraft.mockResolvedValue({ ok: true, draft: DRAFT });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("useAutosave", () => {
  it("sends saves one at a time, so an older one cannot land on a newer one", async () => {
    const save = held();
    const { result } = renderHook(() => useAutosave<string>(save.call as never));
    act(() => result.current.queue("A"));
    const first = result.current.flush();
    act(() => result.current.queue("AB"));
    const second = result.current.flush();
    await waitFor(() => expect(save.count()).toBe(1));
    // "AB" has not gone out while "A" is unanswered.
    expect(save.call.mock.calls).toEqual([["A"]]);
    save.answer(0, FAILED);
    await waitFor(() => expect(save.count()).toBe(2));
    save.answer(1, OK);
    expect(await first).toBe(false);
    expect(await second).toBe(true);
    // The failed "A" was not kept: something newer had been typed.
    expect(await result.current.flush()).toBe(true);
    expect(save.call.mock.calls).toEqual([["A"], ["AB"]]);
  });

  it("flush waits for a save already on its way and tries a failed one again", async () => {
    const save = held();
    const { result } = renderHook(() => useAutosave<string>(save.call as never));
    act(() => result.current.queue("A"));
    void result.current.flush();
    await waitFor(() => expect(save.count()).toBe(1));
    let settled: boolean | null = null;
    void result.current.flush().then((ok) => (settled = ok));
    await Promise.resolve();
    expect(settled).toBeNull(); // nothing is waiting, but "A" is still on its way
    save.answer(0, FAILED);
    await waitFor(() => expect(save.count()).toBe(2));
    expect(save.call.mock.calls[1]).toEqual(["A"]);
    save.answer(1, OK);
    await waitFor(() => expect(settled).toBe(true));
  });

  it("lets go of a save that fails after what it belonged to was dropped", async () => {
    const save = held();
    const { result } = renderHook(() => useAutosave<string>(save.call as never));
    act(() => result.current.queue("old text"));
    void result.current.flush();
    await waitFor(() => expect(save.count()).toBe(1));
    act(() => result.current.drop());
    save.answer(0, FAILED);
    expect(await result.current.flush()).toBe(true);
    expect(save.call).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBe("");
  });
});

describe("useMailComments", () => {
  it("offers nothing to add to until the saved comments have loaded, and says why when they cannot", async () => {
    api.getMailComments.mockResolvedValue({ ok: false, error: "Email is not connected." });
    const { result } = renderHook(() => useMailComments("k1"));
    await waitFor(() => expect(result.current.error).toBe("Email is not connected."));
    expect(result.current.loaded).toBe(false);
    expect(api.putMailComments).not.toHaveBeenCalled();
  });
});

describe("useMailDraft", () => {
  const open = async (saveNotes = vi.fn(async () => true)) => {
    const onSent = vi.fn();
    const onSendFailed = vi.fn();
    const hook = renderHook(() => useMailDraft("d1", saveNotes, onSent, onSendFailed));
    await waitFor(() => expect(hook.result.current.draft).not.toBeNull());
    return { ...hook, onSent, onSendFailed, saveNotes };
  };

  it("does not ask Mimi when what was typed could not be saved", async () => {
    const { result } = await open();
    api.updateMailDraft.mockResolvedValueOnce(FAILED);
    act(() => result.current.edit({ body: "typed by hand" }));
    await act(() => result.current.write(ANSWER));
    expect(api.writeMailReply).not.toHaveBeenCalled();
    expect(result.current.draft!.body).toBe("typed by hand");
    expect(result.current.error).toContain("Could not reach MimiWork");
    // Nor when the comments could not be saved: she reads the saved ones.
    const second = await open(vi.fn(async () => false));
    await act(() => second.result.current.write(ANSWER));
    expect(api.writeMailReply).not.toHaveBeenCalled();
  });

  it("keeps what the user had written so it can be put back after Mimi writes over it", async () => {
    const { result } = await open();
    act(() => result.current.edit({ body: "typed by hand" }));
    await act(() => result.current.write(ANSWER, "shorter"));
    expect(api.writeMailReply).toHaveBeenCalledWith("d1", "shorter");
    expect(result.current.draft!.body).toBe("MIMI'S TEXT");
    expect(api.updateMailDraft).toHaveBeenLastCalledWith("d1", { body: "MIMI'S TEXT" });
    expect(result.current.canRestore).toBe(true);
    act(() => result.current.restore());
    expect(result.current.draft!.body).toBe("typed by hand");
    expect(result.current.canRestore).toBe(false);
  });

  it("starts the reply again when the one it has was left empty on an earlier message", async () => {
    const { result } = await open();
    const newest = { folder: "INBOX", uid: 2, message_id: "<2@x>" };
    api.createMailDraft.mockResolvedValue({ ok: true, draft: { ...DRAFT, id: "d2", answers_id: "<2@x>" } });
    await act(() => result.current.write(newest));
    expect(api.createMailDraft).toHaveBeenCalledWith({ folder: "INBOX", uid: 2, reply_all: false });
    expect(api.writeMailReply).toHaveBeenCalledWith("d2", "");
    expect(result.current.draft!.id).toBe("d2");
  });

  it("does not leave an empty reply behind when Mimi could not write it", async () => {
    api.writeMailReply.mockResolvedValue({ ok: false, error: "Mimi could not write the reply. No model is set up." });
    const onSent = vi.fn();
    const { result } = renderHook(() => useMailDraft("", async () => true, onSent, vi.fn()));
    await act(() => result.current.write(ANSWER));
    expect(api.deleteMailDraft).toHaveBeenCalledWith("d1");
    expect(result.current.draft).toBeNull();
    expect(result.current.modelFailed).toBe(true);
    // An answer with no text in it is a failure too, not an empty reply.
    api.writeMailReply.mockResolvedValue({ ok: true, text: "" });
    await act(() => result.current.write(ANSWER));
    expect(result.current.draft).toBeNull();
  });

  it("sends only once what is on screen is saved, and waits for a save already on its way", async () => {
    const save = held();
    api.updateMailDraft.mockImplementation(save.call);
    const { result, onSent } = await open();
    act(() => result.current.edit({ body: "final words" }));
    let sending: Promise<void> = Promise.resolve();
    act(() => {
      sending = result.current.send();
    });
    await waitFor(() => expect(save.count()).toBe(1));
    expect(api.sendMailDraft).not.toHaveBeenCalled();
    expect(result.current.busy).toBe("sending");
    save.answer(0, OK);
    await act(() => sending);
    expect(save.call.mock.calls[0]).toEqual(["d1", { to: "ana@example.com", cc: "", subject: "Re: Plan", body: "final words" }]);
    expect(api.sendMailDraft).toHaveBeenCalledWith("d1");
    expect(onSent).toHaveBeenCalledWith("");
  });

  it("does not send when the last words could not be saved", async () => {
    const { result, onSent } = await open();
    api.updateMailDraft.mockResolvedValue(FAILED);
    act(() => result.current.edit({ body: "final words" }));
    await act(() => result.current.send());
    expect(api.sendMailDraft).not.toHaveBeenCalled();
    expect(onSent).not.toHaveBeenCalled();
    expect(result.current.busy).toBe("");
  });

  it("tells the section why a send failed when the editor has been left", async () => {
    const send = held();
    api.sendMailDraft.mockImplementation(send.call);
    const { result, unmount, onSendFailed, onSent } = await open();
    let sending: Promise<void> = Promise.resolve();
    act(() => {
      sending = result.current.send();
    });
    await waitFor(() => expect(send.count()).toBe(1));
    unmount();
    send.answer(0, { ok: false, error: "The mail server did not accept the message: 550 no" });
    await sending;
    expect(onSendFailed).toHaveBeenCalledWith("The mail server did not accept the message: 550 no");
    expect(onSent).not.toHaveBeenCalled();
  });

  it("a discarded draft's unsaved text never reaches the next draft", async () => {
    const save = held();
    api.updateMailDraft.mockImplementation(save.call);
    const { result } = await open();
    act(() => result.current.edit({ body: "old draft text" }));
    // The save goes out by itself a moment after the last keystroke; given room on a busy machine.
    await waitFor(() => expect(save.count()).toBe(1), { timeout: 5000 });
    await act(async () => void (await result.current.discard()));
    save.answer(0, { ok: false, error: "This draft no longer exists." });
    expect(result.current.error).toBe("");
    // A new reply is started and sent: only its own text is saved.
    api.createMailDraft.mockResolvedValue({ ok: true, draft: { ...DRAFT, id: "d2" } });
    await act(async () => void (await result.current.start(ANSWER)));
    api.updateMailDraft.mockResolvedValue(OK);
    await act(() => result.current.send());
    expect(save.call.mock.calls.filter((call) => (call as unknown[])[0] === "d2")).toEqual([]);
    expect(api.sendMailDraft).toHaveBeenCalledWith("d2");
  });
});
