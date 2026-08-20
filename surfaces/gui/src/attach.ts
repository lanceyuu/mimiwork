import type { Attachment } from "./types";

const MAX_BYTES = 10 * 1024 * 1024; // skip files larger than ~10MB
const TEXT_RE =
  /\.(txt|md|markdown|csv|tsv|json|ya?ml|log|ini|toml|py|js|ts|tsx|jsx|rs|go|java|c|h|cpp|sh|html?|css|sql|xml)$/i;
// Office & friends: sent as kind "file" — the server saves them into the workspace
// and the agent opens them with its Word/Excel/PowerPoint tools (owner ask
// 2026-08-20: dropping a Word file silently did nothing).
const OFFICE_RE = /\.(docx?|xlsx?|pptx?|odt|ods|odp|rtf|key|numbers|pages|epub)$/i;

// Read a File into an Attachment (image/PDF/office → data URL, text → inline text). Returns
// null for unsupported types or oversized files. Shared by the composer and the start panel.
export const isPdfFile = (file: File) =>
  file.type === "application/pdf" || /\.pdf$/i.test(file.name);

export function readFile(file: File): Promise<Attachment | null> {
  const isImage = file.type.startsWith("image/");
  const isPdf = isPdfFile(file);
  const isText = !isPdf && (file.type.startsWith("text/") || TEXT_RE.test(file.name));
  const isOffice = !isImage && !isPdf && !isText && OFFICE_RE.test(file.name);
  if (isOffice && file.size <= MAX_BYTES) {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onerror = () => resolve(null);
      reader.onload = () =>
        resolve({
          kind: "file",
          name: file.name,
          mime: file.type || "application/octet-stream",
          data_url: String(reader.result),
        });
      reader.readAsDataURL(file);
    });
  }
  if ((!isImage && !isPdf && !isText) || file.size > MAX_BYTES) return Promise.resolve(null);
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onerror = () => resolve(null);
    reader.onload = () =>
      resolve(
        isImage
          ? { kind: "image", name: file.name || "image", mime: file.type, data_url: String(reader.result) }
          : isPdf
            ? { kind: "pdf", name: file.name || "file.pdf", mime: "application/pdf", data_url: String(reader.result) }
            : { kind: "text", name: file.name || "file.txt", mime: file.type, text: String(reader.result) },
      );
    if (isImage || isPdf) reader.readAsDataURL(file);
    else reader.readAsText(file);
  });
}
