/** Credits — whose work MimiWork stands on, in the app (owner rule 2026-09-03: always
 *  credit the projects we learn from and the skills we use). The list comes from the
 *  sidecar (coworker/credits.py), the same source CREDITS.md is generated from, so the
 *  page and the file never disagree. Sections fold; the origin stays open. */
import { useEffect, useState } from "react";
import { getAbout, type CreditSection } from "../api";
import { openExternal } from "../tauri";
import { Icon } from "./Icon";

export function CreditsCard({ card, label }: { card: string; label: string }) {
  const [sections, setSections] = useState<CreditSection[] | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  useEffect(() => {
    getAbout()
      .then((a) => setSections(Array.isArray(a?.credits) ? a.credits : []))
      .catch(() => setSections([]));
  }, []);
  if (!sections || sections.length === 0) return null;

  return (
    <div className={card + " p-4 mt-4"} data-testid="credits-card">
      <div className={label + " mb-1"}>Credits</div>
      <p className="text-[12.5px] text-muted mb-3">
        MimiWork stands on other people&rsquo;s work. This is whose, and what we took from each — the same
        list as CREDITS.md in the repository.
      </p>
      <div className="credits-sections">
        {sections.map((section, i) => {
          const isOpen = open[section.title] ?? i === 0;
          return (
            <div className="credits-section" key={section.title}>
              <button
                type="button"
                className="credits-head"
                aria-expanded={isOpen}
                data-testid="credits-section"
                onClick={() => setOpen((cur) => ({ ...cur, [section.title]: !isOpen }))}
              >
                <Icon name={isOpen ? "chevronDown" : "chevronRight"} size={14} className="text-faint shrink-0" />
                <span className="credits-title">{section.title}</span>
                <span className="credits-count">{section.items.length}</span>
              </button>
              {isOpen && (
                <div className="credits-body">
                  {section.blurb && <div className="credits-blurb">{section.blurb}</div>}
                  <ul className="credits-list">
                    {section.items.map((item) => (
                      <li key={item.name} className="credits-item">
                        {item.url ? (
                          <button type="button" className="credits-name" onClick={() => openExternal(item.url!)}>
                            {item.name}
                          </button>
                        ) : (
                          <span className="credits-name">{item.name}</span>
                        )}
                        {item.license && <span className="credits-license">{item.license}</span>}
                        {item.what && <span className="credits-what">{item.what}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
