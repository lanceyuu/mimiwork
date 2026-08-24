/** One folder row in Access ▸ Folders: the name opens the folder, the rest still works. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { RootRow } from "./RootRow";
import type { RootInfo } from "../api";

afterEach(cleanup);

const ROOT: RootInfo = {
  path: "/Users/me/HEC/Online marketing course",
  label: "Online marketing course",
  writable: true,
  primary: false,
  exists: true,
};

describe("RootRow", () => {
  it("opens the folder when its name is clicked", () => {
    const onOpen = vi.fn();
    render(<RootRow root={ROOT} onToggle={() => {}} onRemove={() => {}} onOpen={onOpen} />);
    const name = screen.getByTestId(`root-open-${ROOT.path}`);
    expect(name.textContent).toContain("Online marketing course");
    fireEvent.click(name);
    expect(onOpen).toHaveBeenCalledWith(ROOT);
  });

  it("stays plain text when there is nothing to open", () => {
    // No handler (older callers) — and a folder that is gone: clicking either would lie.
    const { rerender } = render(<RootRow root={ROOT} onToggle={() => {}} onRemove={() => {}} />);
    expect(screen.queryByTestId(`root-open-${ROOT.path}`)).toBeNull();
    rerender(
      <RootRow
        root={{ ...ROOT, exists: false }}
        onToggle={() => {}}
        onRemove={() => {}}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.queryByTestId(`root-open-${ROOT.path}`)).toBeNull();
    expect(screen.getByText("missing")).toBeTruthy();
  });

  it("keeps the access toggle and remove button working next to it", () => {
    const onToggle = vi.fn();
    const onRemove = vi.fn();
    render(
      <RootRow root={ROOT} onToggle={onToggle} onRemove={onRemove} onOpen={vi.fn()} />,
    );
    fireEvent.click(screen.getByText("Read-write"));
    expect(onToggle).toHaveBeenCalledWith(ROOT);
    fireEvent.click(screen.getByTitle("Remove"));
    expect(onRemove).toHaveBeenCalledWith(ROOT.path);
  });
});
