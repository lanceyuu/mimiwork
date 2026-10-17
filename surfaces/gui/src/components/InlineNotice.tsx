// What replaced window.alert(): a native modal froze the whole window and carried the
// server's own wording. This sits next to what the user just did and stays until dismissed.
export function InlineNotice({
  text,
  tone = "error",
  onDismiss,
}: {
  text: string;
  tone?: "error" | "info";
  onDismiss: () => void;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      data-testid="inline-notice"
      className={
        "flex items-start gap-3 rounded-lg border px-3 py-2 my-2 text-[12.5px] " +
        (tone === "error" ? "border-red-200 bg-red-50 text-red-700" : "border-line bg-panel text-ink")
      }
    >
      <span className="flex-1 break-words">{text}</span>
      <button className="text-[12px] opacity-70 hover:opacity-100 px-0.5" title="Dismiss" onClick={onDismiss}>
        ✕
      </button>
    </div>
  );
}
