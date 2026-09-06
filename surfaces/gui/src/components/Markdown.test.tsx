import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Markdown, OPEN_ARTIFACT_EVENT } from "./Markdown";

afterEach(cleanup);

// §34 (UX-016): [Title](artifact:path) renders as a chip that opens the artifact viewer via
// a window event; ordinary links keep the open-externally treatment.
describe("Markdown artifact links", () => {
  it("renders an artifact: link as a chip and dispatches the open event with the path", () => {
    const seen: string[] = [];
    const listener = (e: Event) => seen.push((e as CustomEvent).detail.path);
    window.addEventListener(OPEN_ARTIFACT_EVENT, listener);

    render(<Markdown text="Done — [Semiconductor dashboard](artifact:reports/semi.html)" />);
    const chip = screen.getByTestId("artifact-chip");
    expect(chip.textContent).toContain("Semiconductor dashboard");
    expect(chip.textContent).toContain("semi.html"); // filename shown under the title
    fireEvent.click(chip);
    expect(seen).toEqual(["reports/semi.html"]);

    window.removeEventListener(OPEN_ARTIFACT_EVENT, listener);
  });

  it("ordinary links stay external and never become chips", () => {
    const { container } = render(<Markdown text="see [the docs](https://example.com)" />);
    expect(screen.queryByTestId("artifact-chip")).toBeNull();
    const a = container.querySelector("a")!;
    expect(a.getAttribute("target")).toBe("_blank");
    expect(a.getAttribute("href")).toBe("https://example.com");
  });

  it("chip title falls back to the filename when the link text is empty", () => {
    vi.spyOn(window, "dispatchEvent");
    render(<Markdown text="[](artifact:out/report.pdf)" />);
    expect(screen.getByTestId("artifact-chip").textContent).toContain("report.pdf");
  });

  it("carries an absolute path through, spaces and all", () => {
    // The real link from a deliverable written into a granted folder (owner report
    // 2026-08-24): an absolute path with spaces in it must survive the markdown pipeline.
    const seen: string[] = [];
    const listener = (e: Event) => seen.push((e as CustomEvent).detail.path);
    window.addEventListener(OPEN_ARTIFACT_EVENT, listener);
    const path = "/Users/yu/HEC/Online marketing course/Debrief Module 2.docx";
    render(<Markdown text={`[Open the debrief](<artifact:${path}>)`} />);
    fireEvent.click(screen.getByTestId("artifact-chip"));
    expect(seen).toEqual([path]);
    window.removeEventListener(OPEN_ARTIFACT_EVENT, listener);
  });

  it("leaves a filename's own percent sign alone", () => {
    // decodeURI would throw on "50%" — the chip must still open "Q3 50% growth.md".
    const seen: string[] = [];
    const listener = (e: Event) => seen.push((e as CustomEvent).detail.path);
    window.addEventListener(OPEN_ARTIFACT_EVENT, listener);
    render(<Markdown text="[stats](<artifact:reports/Q3 50% growth.md>)" />);
    fireEvent.click(screen.getByTestId("artifact-chip"));
    expect(seen[0].endsWith("growth.md")).toBe(true);
    expect(seen[0]).toContain("50%");
    window.removeEventListener(OPEN_ARTIFACT_EVENT, listener);
  });
});

describe("right-click on a produced file (owner ask 2026-08-31)", () => {
  afterEach(() => cleanup());

  it("offers Open and Show in Finder, and asks for the right one", async () => {
    const events: any[] = [];
    const onReveal = (e: Event) => events.push((e as CustomEvent).detail);
    window.addEventListener("ocw-reveal-artifact", onReveal);

    render(<Markdown text="Done — [Brief](artifact:reports/brief.docx)" />);
    fireEvent.contextMenu(screen.getByTestId("artifact-chip"));

    const menu = screen.getByTestId("artifact-menu");
    expect(menu.textContent).toContain("Open file");
    // jsdom's userAgent is not a Mac, so this is the generic wording; the Mac label is
    // chosen by platformOS() at runtime.
    expect(menu.textContent).toMatch(/Show in (Finder|File Explorer|folder)/);

    fireEvent.click(screen.getByTestId("artifact-menu-reveal"));
    expect(events).toEqual([{ path: "reports/brief.docx", mode: "reveal" }]);
    expect(screen.queryByTestId("artifact-menu")).toBeNull();
    window.removeEventListener("ocw-reveal-artifact", onReveal);
  });

  it("Open file asks for open, not reveal", async () => {
    const events: any[] = [];
    const onReveal = (e: Event) => events.push((e as CustomEvent).detail);
    window.addEventListener("ocw-reveal-artifact", onReveal);

    render(<Markdown text="[Deck](artifact:out/deck.pptx)" />);
    fireEvent.contextMenu(screen.getByTestId("artifact-chip"));
    fireEvent.click(screen.getByTestId("artifact-menu-open"));

    expect(events).toEqual([{ path: "out/deck.pptx", mode: "open" }]);
    window.removeEventListener("ocw-reveal-artifact", onReveal);
  });

  it("left-click still opens the in-app preview — the menu adds, it does not replace", async () => {
    const opens: any[] = [];
    const onOpen = (e: Event) => opens.push((e as CustomEvent).detail);
    window.addEventListener("ocw-open-artifact", onOpen);

    render(<Markdown text="[Brief](artifact:reports/brief.docx)" />);
    fireEvent.click(screen.getByTestId("artifact-chip"));

    expect(opens).toEqual([{ path: "reports/brief.docx" }]);
    expect(screen.queryByTestId("artifact-menu")).toBeNull();
    window.removeEventListener("ocw-open-artifact", onOpen);
  });

  it("a path with spaces reaches the menu decoded", async () => {
    const events: any[] = [];
    const onReveal = (e: Event) => events.push((e as CustomEvent).detail);
    window.addEventListener("ocw-reveal-artifact", onReveal);

    render(<Markdown text="[Debrief](<artifact:Online marketing course/Debrief Module 2.docx>)" />);
    fireEvent.contextMenu(screen.getByTestId("artifact-chip"));
    fireEvent.click(screen.getByTestId("artifact-menu-reveal"));

    expect(events[0].path).toBe("Online marketing course/Debrief Module 2.docx");
    window.removeEventListener("ocw-reveal-artifact", onReveal);
  });
});

describe("a plain link to a produced file (owner-hit 2026-08-31)", () => {
  afterEach(() => cleanup());

  it("becomes a chip, so it opens and offers the right-click menu", () => {
    // What the model actually wrote in the owner's session — not the artifact: form the
    // instructions ask for. These arrived as ordinary web links: nothing on click, no
    // menu on right-click.
    render(<Markdown text="- [Wix API Guide](Wix_API_Guide.md) — capability catalog" />);
    const chip = screen.getByTestId("artifact-chip");
    expect(chip.textContent).toContain("Wix API Guide");

    const events: any[] = [];
    const onReveal = (e: Event) => events.push((e as CustomEvent).detail);
    window.addEventListener("ocw-reveal-artifact", onReveal);
    fireEvent.contextMenu(chip);
    fireEvent.click(screen.getByTestId("artifact-menu-reveal"));
    expect(events).toEqual([{ path: "Wix_API_Guide.md", mode: "reveal" }]);
    window.removeEventListener("ocw-reveal-artifact", onReveal);
  });

  it("handles a nested path and a file:// URL the same way", () => {
    render(<Markdown text="[a](reports/out.pdf) and [b](file:///tmp/x.docx)" />);
    const chips = screen.getAllByTestId("artifact-chip");
    expect(chips).toHaveLength(2);
    expect(chips[0].getAttribute("title")).toBe("reports/out.pdf");
    expect(chips[1].getAttribute("title")).toBe("/tmp/x.docx");
  });

  it("leaves real web links alone", () => {
    const { container } = render(
      <Markdown text="[docs](https://example.com) [mail](mailto:a@b.com) [top](#section)" />,
    );
    expect(screen.queryByTestId("artifact-chip")).toBeNull();
    const hrefs = [...container.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual(["https://example.com", "mailto:a@b.com", "#section"]);
  });

  it("a protocol-relative URL is a web link, not a path", () => {
    const { container } = render(<Markdown text="[cdn](//cdn.example.com/x.js)" />);
    expect(screen.queryByTestId("artifact-chip")).toBeNull();
    expect(container.querySelector("a")?.getAttribute("href")).toBe("//cdn.example.com/x.js");
  });
});

// A ```mermaid fence is drawn (the show-me skill's "Show me how" answer); the library is
// mocked — what matters is that the fence reaches the renderer and its SVG lands in the DOM.
vi.mock("mermaid", () => ({
  default: { initialize: vi.fn(), render: vi.fn(async () => ({ svg: "<svg data-mock></svg>" })) },
}));
describe("Markdown mermaid fences", () => {
  it("renders a mermaid fence as a diagram, and other fences as code", async () => {
    vi.useFakeTimers();
    const { container } = render(<Markdown text={"```mermaid\nflowchart LR\n  A-->B\n```\n\n```text\nplain\n```"} />);
    expect(container.querySelector("pre code")?.textContent).toContain("A-->B"); // raw until drawn
    await vi.advanceTimersByTimeAsync(300);
    vi.useRealTimers();
    expect(container.querySelector('[data-testid="mermaid"] svg')).toBeTruthy();
    expect(container.querySelectorAll("pre").length).toBe(1); // the text fence stays a code block
  });
});
