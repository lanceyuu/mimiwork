/** The frame an email is shown in: what it is given, and what it is never given. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

vi.mock("./disarm", async (original) => {
  const real = await original<typeof import("./disarm")>();
  return {
    ...real,
    // Stands in for an email that cannot be made inert.
    disarmEmail: (html: string, opts?: { images?: boolean }) =>
      html.includes("CANNOT-BE-MADE-SAFE") ? null : real.disarmEmail(html, opts),
  };
});

import { linkTarget, MailFrame } from "./MailFrame";

afterEach(cleanup);

const frame = () => screen.getByTestId("mail-frame") as HTMLIFrameElement;

describe("MailFrame", () => {
  it("turns scripts off in the frame and hands it only the disarmed email", () => {
    render(<MailFrame html='<p>Hi <a href="https://example.com/x">link</a></p>' text="Hi link" />);
    expect(frame().getAttribute("sandbox")).toBe("allow-same-origin");
    const given = frame().getAttribute("srcdoc")!;
    expect(given).toContain("Content-Security-Policy");
    expect(given).toContain('data-mail-href="https://example.com/x"');
    expect(given).not.toMatch(/\shref=/);
  });

  it("keeps remote images out until Show images is pressed", () => {
    render(<MailFrame html='<p><img src="https://x.example/logo.png"></p>' text="" />);
    expect(frame().getAttribute("srcdoc")).toContain("img-src data:;");
    fireEvent.click(screen.getByTestId("mail-show-images"));
    expect(frame().getAttribute("srcdoc")).toContain("img-src data: https:;");
    expect(screen.queryByTestId("mail-show-images")).toBeNull();
  });

  it("does not offer Show images for an email with nothing remote to show", () => {
    render(<MailFrame html='<p><img src="data:image/png;base64,AAAA"></p>' text="" />);
    expect(screen.queryByTestId("mail-show-images")).toBeNull();
  });

  it("shows the plain text, and no frame, for an email that cannot be made inert", () => {
    render(<MailFrame html="<p>CANNOT-BE-MADE-SAFE</p>" text="Only the words." />);
    expect(screen.queryByTestId("mail-frame")).toBeNull();
    expect(screen.getByTestId("mail-plain").textContent).toContain("Only the words.");
  });
});

describe("linkTarget", () => {
  it("shows a web address the way the browser reads it, and lets it be opened", () => {
    expect(linkTarget("HTTPS://Example.com/a b")).toEqual({ shown: "https://example.com/a%20b", openable: true });
    expect(linkTarget("mailto:ana@example.com").openable).toBe(true);
  });

  it("shows a look-alike host for what it is", () => {
    // The first letter is the Cyrillic letter that looks like a Latin a.
    expect(linkTarget("https://\u0430pple.com/").shown).toBe("https://xn--pple-43d.com/");
  });

  it("shows anything else without offering to open it, and without hidden marks", () => {
    expect(linkTarget("javascript:alert(1)")).toEqual({ shown: "javascript:alert(1)", openable: false });
    expect(linkTarget("#top")).toEqual({ shown: "#top", openable: false });
    expect(linkTarget("file\u202egpj.exe")).toEqual({ shown: "filegpj.exe", openable: false });
  });
});
