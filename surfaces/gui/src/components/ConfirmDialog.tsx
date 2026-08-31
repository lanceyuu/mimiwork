import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";
import { useT } from "../i18n";

// One dialog for every destructive answer the app needs.
//
// Deleting used to be answered by the word "Delete?" appearing where "Delete" had been: the
// mouse was already over the button, so the second click was the one the hand had already
// started. Some deletes had no question at all — an automation card's trash icon removed it
// on a single click, from a list you scroll past. This asks properly: a modal, the thing's
// own name in the sentence so you can see WHICH one, Cancel focused, Esc to leave.
//
// Focus starts on Cancel, not Confirm, and Enter is not bound to the destructive action:
// the safe answer should be the one a reflex produces.
export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  destructive = true,
  onConfirm,
  onCancel,
  children,
}: {
  title: string;
  /** Optional second line — the specific consequence, in plain words. */
  body?: string;
  confirmLabel: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  /** Extra controls that change what the confirm DOES — e.g. "also delete its
   *  conversations". Anything here must be a choice, never more prose. */
  children?: ReactNode;
}) {
  const t = useT();
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCancel();
      }
    };
    // Capture: a dialog opened from inside a row menu must swallow Esc before the
    // menu's own handler closes the menu and leaves the dialog stranded.
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onCancel]);

  return createPortal(
    <div className="fixed inset-0 z-[60]" data-testid="confirm-dialog" role="alertdialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/30 backdrop-blur-[1px]" onClick={onCancel} />
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[420px] max-w-[92vw] rounded-xl2 border border-line bg-panel shadow-2xl overflow-hidden">
        <div className="px-5 pt-4 pb-3 flex items-start gap-3">
          {destructive && (
            <span className="mt-0.5 shrink-0 text-danger">
              <Icon name="trash" size={16} />
            </span>
          )}
          <div className="min-w-0">
            <div className="text-[13.5px] font-semibold text-ink">{title}</div>
            {body && <div className="mt-1 text-[12.5px] text-muted leading-relaxed">{body}</div>}
            {children}
          </div>
        </div>
        <div className="px-5 py-3 border-t border-line flex items-center justify-end gap-2">
          <button
            ref={cancelRef}
            className="btn sm"
            data-testid="confirm-cancel"
            onClick={onCancel}
          >
            {t("Cancel")}
          </button>
          <button
            className={"btn sm" + (destructive ? " danger-btn" : "")}
            data-testid="confirm-accept"
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
