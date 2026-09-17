/** The keyboard shortcuts, in one place: the "?" overlay and the transfer guide read the
 *  same list, so what is advertised is what works (owner ask 2026-09-17: most of these
 *  existed, nobody knew). */
import { useEffect } from "react";

export const SHORTCUTS: { keys: string; what: string }[] = [
  { keys: "/", what: "Commands and skills" },
  { keys: "@", what: "Point at a file" },
  { keys: "⇧⇥", what: "Cycle Default → Accept edits → Plan" },
  { keys: "⏎", what: "Send · ⇧⏎ new line" },
  { keys: "Esc", what: "Stop the current task · close a popup" },
  { keys: "y · a · n", what: "Answer an approval: yes · yes, always · no" },
  { keys: "⌘K", what: "Search conversations" },
  { keys: "⌘B", what: "Hide or show the sidebar" },
  { keys: "⌘,", what: "Settings" },
  { keys: "?", what: "This sheet" },
];

export function ShortcutsSheet({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-[60] grid place-items-center bg-black/30" onClick={onClose} data-testid="shortcuts-sheet">
      <div
        className="w-[380px] max-w-[92vw] rounded-2xl border border-line bg-panel shadow-2xl p-5"
        role="dialog"
        aria-label="Keyboard shortcuts"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-[15px] font-semibold mb-3">Keyboard shortcuts</div>
        <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
          {SHORTCUTS.map((s) => (
            <div key={s.keys} className="contents">
              <kbd className="justify-self-start px-1.5 py-0.5 rounded-md border border-line bg-paper text-[12px] tabular-nums whitespace-nowrap">
                {s.keys}
              </kbd>
              <span className="text-muted self-center">{s.what}</span>
            </div>
          ))}
        </div>
        <div className="text-[11.5px] text-faint mt-4">Press ? anywhere outside a text box to open this.</div>
      </div>
    </div>
  );
}
