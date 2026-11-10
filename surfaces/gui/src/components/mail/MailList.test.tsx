/** The rows of the Mail list. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { formatMailDate, MailList, senderName, type MailRow } from "./MailList";

afterEach(cleanup);

const ROWS: MailRow[] = [
  { id: "k1", sender: "Ana Lopez <ana@example.com>", subject: "Plan for Friday", date: 0, unread: true, count: 3 },
  { id: "k2", sender: "billing@example.com", subject: "", date: 0, unread: false, error: "this mailbox cannot move mail" },
];

describe("MailList", () => {
  it("shows who it is from, the subject, and which rows are unread or selected", () => {
    render(<MailList rows={ROWS} selected="k2" onOpen={() => {}} empty="No mail here yet." />);
    const [first, second] = screen.getAllByTestId("mail-row");
    expect(first.textContent).toContain("Ana Lopez");
    expect(first.textContent).not.toContain("ana@example.com");
    expect(first.textContent).toContain("Plan for Friday");
    expect(first.textContent).toContain("3");
    expect(first.className).toContain("unread");
    expect(first.textContent).toContain("Unread");
    expect(second.textContent).toContain("billing@example.com");
    expect(second.className).not.toContain("unread");
    expect(second.getAttribute("aria-current")).toBe("true");
  });

  it("shows on the row why a change to it did not go through", () => {
    render(<MailList rows={ROWS} selected="" onOpen={() => {}} empty="" />);
    expect(screen.getByRole("alert").textContent).toBe("this mailbox cannot move mail");
  });

  it("opens the row that is clicked", () => {
    const onOpen = vi.fn();
    render(<MailList rows={ROWS} selected="" onOpen={onOpen} empty="" />);
    fireEvent.click(screen.getAllByTestId("mail-row")[0]);
    expect(onOpen).toHaveBeenCalledWith("k1");
  });

  it("says so when there is nothing to list", () => {
    render(<MailList rows={[]} selected="" onOpen={() => {}} empty="No mail here yet." />);
    expect(screen.getByTestId("mail-list-empty").textContent).toBe("No mail here yet.");
  });
});

describe("senderName", () => {
  it("is the name when there is one, and the address when there is not", () => {
    expect(senderName('"Ana Lopez" <ana@example.com>')).toBe("Ana Lopez");
    expect(senderName("Ana <ana@example.com>")).toBe("Ana");
    expect(senderName("<ana@example.com>")).toBe("ana@example.com");
    expect(senderName("ana@example.com")).toBe("ana@example.com");
  });
});

describe("formatMailDate", () => {
  it("is a time for today, a day for this year, and empty for no date", () => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 9, 5).getTime() / 1000;
    expect(formatMailDate(today)).toMatch(/9.05/);
    expect(formatMailDate(new Date(2001, 2, 4).getTime() / 1000)).toContain("2001");
    expect(formatMailDate(0)).toBe("");
  });
});
