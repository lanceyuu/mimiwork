/** The comments column: adding a comment from a selection, editing, removing, and when a reply can be written. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MailComments, type Picked } from "./MailComments";

afterEach(cleanup);

const FRIDAY = { message_id: "<1@x>", quote: "meet on Friday", note: "Ten works." };
const BUDGET = { message_id: "<1@x>", quote: "the budget", note: "" };

function show(props: Partial<Parameters<typeof MailComments>[0]> = {}) {
  const onChange = vi.fn();
  const onWrite = vi.fn();
  render(
    <MailComments
      comments={[]} note="" picked={null} ready writing={false} locked={false} error=""
      onChange={onChange} onWrite={onWrite} {...props}
    />,
  );
  return { onChange, onWrite };
}

describe("MailComments", () => {
  it("offers Comment only while something is selected, and adds the selection as a comment", () => {
    const picked: Picked = { messageId: "<1@x>", quote: "meet on Friday" };
    const { onChange } = show({ picked });
    fireEvent.click(screen.getByTestId("mail-comment-add"));
    expect(onChange).toHaveBeenCalledWith({ comments: [{ message_id: "<1@x>", quote: "meet on Friday", note: "" }], note: "" });
    cleanup();
    show();
    expect(screen.getByTestId("mail-comment-add")).toHaveProperty("disabled", true);
  });

  it("comments on what was selected when the press began, even if the selection is gone by the click", () => {
    const picked: Picked = { messageId: "<1@x>", quote: "the budget" };
    const onChange = vi.fn();
    const props = { comments: [], note: "", ready: true, writing: false, locked: false, error: "", onChange, onWrite: vi.fn() };
    const { rerender } = render(<MailComments {...props} picked={picked} />);
    fireEvent.pointerDown(screen.getByTestId("mail-comment-add"));
    // The webview dropped the selection as the button was pressed.
    rerender(<MailComments {...props} picked={null} />);
    fireEvent.click(screen.getByTestId("mail-comment-add"));
    expect(onChange).toHaveBeenCalledWith({ comments: [{ message_id: "<1@x>", quote: "the budget", note: "" }], note: "" });
    // A press that slides off the button without a click holds nothing.
    fireEvent.pointerDown(screen.getByTestId("mail-comment-add"));
    fireEvent.pointerLeave(screen.getByTestId("mail-comment-add"));
    expect(screen.getByTestId("mail-comment-add")).toHaveProperty("disabled", true);
  });

  it("does not add the same passage twice, or anything before the saved comments have loaded", () => {
    const picked: Picked = { messageId: "<1@x>", quote: "meet on Friday" };
    show({ comments: [FRIDAY], picked });
    expect(screen.getByTestId("mail-comment-add")).toHaveProperty("disabled", true);
    cleanup();
    show({ picked: { messageId: "<1@x>", quote: "something else" }, ready: false });
    expect(screen.getByTestId("mail-comment-add")).toHaveProperty("disabled", true);
    expect(screen.getByTestId("mail-free-note")).toHaveProperty("disabled", true);
  });

  it("edits a note, removes a comment and keeps the free note apart", () => {
    const { onChange } = show({ comments: [FRIDAY, BUDGET], note: "Say hello." });
    expect(screen.getAllByTestId("mail-comment")[0].textContent).toContain("meet on Friday");
    fireEvent.change(screen.getAllByTestId("mail-comment-note")[1], { target: { value: "Thursday." } });
    expect(onChange).toHaveBeenLastCalledWith({ comments: [FRIDAY, { ...BUDGET, note: "Thursday." }], note: "Say hello." });
    fireEvent.click(screen.getAllByTestId("mail-comment-remove")[0]);
    expect(onChange).toHaveBeenLastCalledWith({ comments: [BUDGET], note: "Say hello." });
    fireEvent.change(screen.getByTestId("mail-free-note"), { target: { value: "Say hello to Ben." } });
    expect(onChange).toHaveBeenLastCalledWith({ comments: [FRIDAY, BUDGET], note: "Say hello to Ben." });
  });

  it("writes a reply only when some note says what to say, and says so otherwise", () => {
    const { onWrite } = show({ comments: [BUDGET] });
    expect(screen.getByTestId("mail-write-reply")).toHaveProperty("disabled", true);
    expect(screen.getByTestId("mail-write-hint").textContent).toContain("Add a note");
    cleanup();
    const second = show({ comments: [FRIDAY] });
    expect(screen.queryByTestId("mail-write-hint")).toBeNull();
    fireEvent.click(screen.getByTestId("mail-write-reply"));
    expect(second.onWrite).toHaveBeenCalledTimes(1);
    expect(onWrite).not.toHaveBeenCalled();
    cleanup();
    show({ note: "Just say thanks." });
    expect(screen.getByTestId("mail-write-reply")).toHaveProperty("disabled", false);
  });

  it("cannot be asked twice while Mimi is writing, and shows why comments could not be saved", () => {
    show({ comments: [FRIDAY], writing: true, locked: true, error: "Could not reach MimiWork. Try again." });
    const button = screen.getByTestId("mail-write-reply");
    expect(button).toHaveProperty("disabled", true);
    expect(button.textContent).toBe("Writing the reply…");
    expect(screen.getByTestId("mail-comments-error").textContent).toContain("Could not reach MimiWork");
  });

  it("holds still while a reply is being written or sent", () => {
    // A note typed during a send would be saved after the send had cleared the comments.
    show({ comments: [FRIDAY], note: "x", picked: { messageId: "<1@x>", quote: "new" }, locked: true });
    for (const id of ["mail-comment-add", "mail-comment-note", "mail-comment-remove", "mail-free-note", "mail-write-reply"]) {
      expect(screen.getByTestId(id)).toHaveProperty("disabled", true);
    }
    expect(screen.getByTestId("mail-write-reply").textContent).toBe("Write reply");
  });

  it("names each remove button after its passage, and never translates the passage", () => {
    show({ comments: [FRIDAY, BUDGET] });
    const buttons = screen.getAllByTestId("mail-comment-remove");
    expect(buttons.map((b) => b.getAttribute("aria-label"))).toEqual([
      "Remove comment: meet on Friday", "Remove comment: the budget",
    ]);
    expect(screen.getAllByTestId("mail-comment")[0].querySelector("blockquote")!.hasAttribute("data-no-translate")).toBe(true);
  });
});
