/** Mail's sorting settings: the switch, and the senders whose mail is never sent to be sorted. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({ getMailSettings: vi.fn(), putMailSettings: vi.fn() }));
vi.mock("../../api", () => api);

import { MailSortingOffer, MailSortingSettings } from "./MailSorting";

const SETTINGS = { ok: true, sorting: true, excluded: ["@bank.example"], sort_error: "" };

beforeEach(() => {
  api.getMailSettings.mockResolvedValue(SETTINGS);
  api.putMailSettings.mockImplementation(async (changes: object) => ({ ...SETTINGS, ...changes }));
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("MailSortingOffer", () => {
  it("says what sorting does and what it costs before anything is turned on", () => {
    const onAnswer = vi.fn();
    render(<MailSortingOffer onAnswer={onAnswer} />);
    const text = screen.getByTestId("mail-sorting-offer").textContent!;
    expect(text).toContain("reads each new email");
    expect(text).toContain("spends credits");
    fireEvent.click(screen.getByTestId("mail-sorting-yes"));
    // It is answered once: a second press, on either button, does nothing.
    fireEvent.click(screen.getByTestId("mail-sorting-yes"));
    fireEvent.click(screen.getByTestId("mail-sorting-no"));
    expect(onAnswer.mock.calls).toEqual([[true]]);
    expect(screen.getByRole("region", { name: "Let Mimi sort your mail?" })).toBeTruthy();
  });
});

describe("MailSortingSettings", () => {
  it("shows the switch and the senders as saved, and saves a change to each", async () => {
    const onChanged = vi.fn();
    render(<MailSortingSettings onChanged={onChanged} onClose={() => {}} />);
    const box = (await screen.findByTestId("mail-excluded")) as HTMLTextAreaElement;
    expect(box.value).toBe("@bank.example");
    expect(screen.getByTestId("mail-sorting-switch")).toHaveProperty("checked", true);

    fireEvent.change(box, { target: { value: " @bank.example \n\nana@example.com\n" } });
    fireEvent.click(screen.getByTestId("mail-excluded-save"));
    await waitFor(() => expect(api.putMailSettings).toHaveBeenCalledWith({ excluded: ["@bank.example", "ana@example.com"] }));
    expect(await screen.findByText("Saved.")).toBeTruthy();

    fireEvent.click(screen.getByTestId("mail-sorting-switch"));
    await waitFor(() => expect(api.putMailSettings).toHaveBeenLastCalledWith({ sorting: false }));
    await waitFor(() => expect(screen.getByTestId("mail-sorting-switch")).toHaveProperty("checked", false));
    expect(onChanged).toHaveBeenCalledTimes(2);
  });

  it("shows why a list was refused and keeps what was typed", async () => {
    api.putMailSettings.mockResolvedValue({ ok: false, error: '"ana" is not an address or a domain.' });
    render(<MailSortingSettings onChanged={() => {}} onClose={() => {}} />);
    const box = (await screen.findByTestId("mail-excluded")) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "ana" } });
    fireEvent.click(screen.getByTestId("mail-excluded-save"));
    expect((await screen.findByTestId("mail-settings-error")).textContent).toContain("is not an address or a domain");
    expect(box.value).toBe("ana");
  });

  it("says quietly why the last sorting did not work, and closes", async () => {
    api.getMailSettings.mockResolvedValue({ ...SETTINGS, sort_error: "Mimi could not sort new mail. Out of quota." });
    const onClose = vi.fn();
    render(<MailSortingSettings onChanged={() => {}} onClose={onClose} />);
    expect((await screen.findByTestId("mail-sort-error")).textContent).toContain("Out of quota");
    fireEvent.click(screen.getByTestId("mail-settings-close"));
    expect(onClose).toHaveBeenCalled();
  });
});
