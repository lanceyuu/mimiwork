// A persona is "project-scoped" only when it's code-family: an explicit directory the user
// picks, sessions grouped by project in the sidebar. Everything else (knowledge, chat) runs on
// a transparent per-conversation scratch dir, with real folders added as roots when needed —
// no folder gate, ever. (The old workspace enum — git/project/deliverable/none — collapsed
// into family; owner decision 2026-07-03, UX-DECISIONS §16.)
export function isProjectScoped(p?: { workspace?: string; family?: string }): boolean {
  return p?.family === "code";
}

// Persona naming: the product is "MimiWork" and the general persona is "Mimi" (the word
// "Cowork" is Anthropic's product, and it kept surfacing — owner ask 2026-09-16). The others
// are a "Coworker" family — Code Coworker, Ops Coworker: SHORT label (Code / Ops) in lists
// and chrome, FULL family name on the persona page. Backend ids are untouched.

// Short label for the sidebar + top bar: "Mimi" / "Code" / "Ops" / "Chat".
export function shortPersonaName(name?: string, id?: string): string {
  if (id === "cowork") return "Mimi";
  const n = (name || id || "").trim();
  return n.replace(/\s*coworker$/i, "").trim() || n;
}

// Full family name for the persona detail page: "Mimi" / "Code Coworker" / "Ops Coworker".
// Chat isn't a coworker — left as-is.
export function fullPersonaName(name?: string, id?: string): string {
  if (id === "cowork") return "Mimi";
  const n = (name || id || "").trim();
  if (id === "chat" || !n) return n;
  return /coworker$/i.test(n) ? n : `${n} Coworker`;
}
