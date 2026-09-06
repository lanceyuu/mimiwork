import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";
import { Mermaid } from "./Mermaid";
import { platformOS } from "../tauri";
import { useT } from "../i18n";

// §34 (UX-016): the agent ends a deliverable turn with plain markdown —
// [Title](artifact:relative/path) — and the renderer turns it into a chip that opens the
// artifact viewer in place. Plumbing is a window event (the viewer lives in RightRail;
// this component renders deep inside the transcript): RightRail resolves the path against
// the session's artifact list, App un-hides the rail.
export const OPEN_ARTIFACT_EVENT = "ocw-open-artifact";
// Right-click on a produced file (owner ask 2026-08-31). The chip is rendered deep in the
// transcript and has no session id, so — like OPEN_ARTIFACT_EVENT above — it asks by event
// and RightRail, which knows the session, does the work.
export const REVEAL_ARTIFACT_EVENT = "ocw-reveal-artifact";

// Markdown URLs are percent-encoded on the way through the parser, so a real path — and
// a knowledge worker's paths are full of spaces — arrives as
// "Online%20marketing%20course/Debrief%20Module%202.docx" and the file lookup fails on a
// name nothing on disk has (owner report 2026-08-24). decodeURI, not decodeURIComponent:
// it leaves a lone "%" in a filename alone instead of throwing, and the catch covers the
// malformed rest.
function decodePath(raw: string): string {
  try {
    return decodeURI(raw);
  } catch {
    return raw;
  }
}

function ArtifactChip({ path: raw, title }: { path: string; title: string }) {
  const t = useT();
  const path = decodePath(raw);
  const file = path.split("/").pop() || path;
  // Right-click offers the two things you actually want from a file the app just made:
  // open it in whatever program owns it, or show it where it lives. Left-click keeps its
  // meaning (the in-app preview), so the menu adds without taking anything away.
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const reveal = (mode: "open" | "reveal") => {
    setMenu(null);
    window.dispatchEvent(
      new CustomEvent(REVEAL_ARTIFACT_EVENT, { detail: { path, mode } }),
    );
  };
  return (
    <>
    <button
      className="art-chip"
      data-testid="artifact-chip"
      title={path}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setMenu({ x: e.clientX, y: e.clientY });
      }}
      onClick={() =>
        window.dispatchEvent(new CustomEvent(OPEN_ARTIFACT_EVENT, { detail: { path } }))
      }
    >
      <span className="art-chip-ico">
        <Icon name="file" size={14} />
      </span>
      <span className="art-chip-meta">
        <b>{title || file}</b>
        {title && title !== file && <span>{file}</span>}
      </span>
      <span className="art-chip-open">{t("Open")} ›</span>
    </button>
    {menu && <ArtifactMenu x={menu.x} y={menu.y} onPick={reveal} onClose={() => setMenu(null)} />}
    </>
  );
}

/** The chip's right-click menu. Positioned at the cursor and closed by anything else —
 *  a menu that outlives its click is a menu in the way. */
function ArtifactMenu({
  x,
  y,
  onPick,
  onClose,
}: {
  x: number;
  y: number;
  onPick: (mode: "open" | "reveal") => void;
  onClose: () => void;
}) {
  const t = useT();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Ignore presses INSIDE the menu. mousedown precedes click, so a blanket handler
    // unmounted the menu before its own button could be clicked — the item then did
    // nothing at all. Invisible to a unit test firing click() alone; a real browser
    // shows it immediately.
    const away = (e: Event) => {
      if (ref.current?.contains(e.target as Node)) return;
      onClose();
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    // Capture, and on the NEXT frame: the contextmenu that opened this is still
    // unwinding, and a listener added synchronously would catch it and close at once.
    const id = requestAnimationFrame(() => {
      window.addEventListener("mousedown", away, true);
      window.addEventListener("contextmenu", away, true);
      window.addEventListener("scroll", away, true);
      window.addEventListener("keydown", key, true);
    });
    return () => {
      cancelAnimationFrame(id);
      window.removeEventListener("mousedown", away, true);
      window.removeEventListener("contextmenu", away, true);
      window.removeEventListener("scroll", away, true);
      window.removeEventListener("keydown", key, true);
    };
  }, [onClose]);

  // "Show in Finder" on a Mac, "Show in File Explorer" on Windows — the name the person
  // in front of the machine already uses for it.
  const os = platformOS();
  const showLabel =
    os === "macos" ? t("Show in Finder") : os === "windows" ? t("Show in File Explorer") : t("Show in folder");

  const MENU_W = 190;
  const MENU_H = 76;
  const left = Math.min(x, Math.max(8, window.innerWidth - MENU_W - 8));
  const top = Math.min(y, Math.max(8, window.innerHeight - MENU_H - 8));

  return createPortal(
    <div
      ref={ref}
      className="fixed z-[70] w-[190px] py-1 rounded-xl2 border border-line bg-panel shadow-xl"
      style={{ left, top }}
      role="menu"
      data-testid="artifact-menu"
    >
      <button
        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-[12.5px] text-left text-ink hover:bg-paper"
        role="menuitem"
        data-testid="artifact-menu-open"
        onClick={() => onPick("open")}
      >
        <Icon name="file" size={13} className="shrink-0 text-faint" />
        {t("Open file")}
      </button>
      <button
        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-[12.5px] text-left text-ink hover:bg-paper"
        role="menuitem"
        data-testid="artifact-menu-reveal"
        onClick={() => onPick("reveal")}
      >
        <Icon name="folder" size={13} className="shrink-0 text-faint" />
        {showLabel}
      </button>
    </div>,
    document.body,
  );
}

// Assistant messages rendered as GitHub-flavored markdown (headings, lists, tables, code,
// links). Links open externally — never navigate the app shell — except artifact: links,
// which open the session's artifact viewer.
/** Does this link point at a file the session produced?
 *
 *  `artifact:` is the form the instructions ask for, but models write the obvious thing —
 *  `[Wix API Guide](Wix_API_Guide.md)` — and those arrived as ordinary web links: they
 *  opened nothing on click and offered no right-click menu, because the chip was the only
 *  thing that had one (owner-hit 2026-08-31). A relative path in an assistant message is a
 *  produced file; treat it as one rather than insisting the model phrase it our way.
 *
 *  Deliberately NOT files: anything with a scheme the web owns (http, https, mailto),
 *  in-page anchors, and protocol-relative URLs.
 */
function filePath(href: string | undefined): string | null {
  const raw = (href || "").trim();
  if (!raw) return null;
  if (raw.startsWith("artifact:")) return raw.slice("artifact:".length);
  if (raw.startsWith("file://")) return raw.slice("file://".length);
  if (raw.startsWith("#") || raw.startsWith("//")) return null;
  if (/^[a-z][a-z0-9+.-]*:/i.test(raw)) return null; // any other scheme: leave it alone
  return raw;
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="md" data-no-translate>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        // artifact: and bare relative paths are ours — keep them through the sanitizer,
        // which would otherwise drop what it does not recognise as a web URL.
        urlTransform={(url) => (filePath(url) ? url : defaultUrlTransform(url))}
        components={{
          // A ```mermaid fence becomes a drawn diagram instead of a code block.
          pre: ({ node, children, ...props }) => {
            const code: any = (node as any)?.children?.[0];
            const cls: string[] = code?.properties?.className || [];
            const text = code?.children?.[0]?.value;
            if (cls.includes("language-mermaid") && typeof text === "string") return <Mermaid chart={text} />;
            return <pre {...props}>{children}</pre>;
          },
          a: ({ node: _n, href, children, ...props }) => {
            const path = filePath(href);
            if (path) {
              const title = Array.isArray(children) ? children.join("") : String(children ?? "");
              return <ArtifactChip path={path} title={title} />;
            }
            return (
              <a href={href} {...props} target="_blank" rel="noreferrer">
                {children}
              </a>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
