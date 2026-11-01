/** The "?" notes beside each choice when building a team of agents. */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { FieldTip, HelpTip } from "./HelpTip";

afterEach(cleanup);

describe("HelpTip", () => {
  it("opens its note on click and closes it with Escape or a click elsewhere", () => {
    render(
      <div>
        <HelpTip title="Thinking effort" testId="tip">How hard the model thinks.</HelpTip>
        <p>outside</p>
      </div>,
    );
    const btn = screen.getByTestId("tip");
    expect(screen.queryByRole("note")).toBeNull();
    fireEvent.click(btn);
    expect(screen.getByRole("note").textContent).toContain("How hard the model thinks.");
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("note")).toBeNull();
    fireEvent.click(btn);
    fireEvent.mouseDown(screen.getByText("outside"));
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("inside a field's label, opening the note does not focus the field", () => {
    render(
      <label>
        <span>
          Model <FieldTip field="model" />
        </span>
        <input data-testid="field" />
      </label>,
    );
    fireEvent.click(screen.getByTestId("help-model"));
    expect(document.activeElement).not.toBe(screen.getByTestId("field"));
    expect(screen.getByRole("note").textContent).toContain("credits");
  });
});
