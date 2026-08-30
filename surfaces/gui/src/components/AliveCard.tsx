import { useEffect, useState } from "react";
import { getAbout, type AboutInfo } from "../api";
import { openExternal } from "../tauri";
import { useT } from "../i18n";

// "Is this thing still alive?" — answered with evidence, not adjectives.
//
// A week after installing, a user wonders three things: is anyone still working on
// this, will my models fall behind, and who is behind it. Marketing copy cannot
// answer any of them credibly; a release list with real dates can. So this card
// shows what is checkable — the last releases and when they shipped, how big the
// model catalogue is, and a named maintainer — and says the one genuinely reassuring
// structural fact: a signed-in QualiTaTi account's models are upgraded server-side,
// so "falling behind" is not something the user has to act on.
//
// It fetches only when Settings is open (never on boot), from the same GitHub host
// the updater already contacts, and shows the local facts alone when offline.

function when(iso: string, t: (s: string) => string): string {
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return t("today");
  if (days === 1) return t("yesterday");
  if (days < 30) return `${days} ${t("days ago")}`;
  const months = Math.round(days / 30);
  return months <= 1 ? t("last month") : `${months} ${t("months ago")}`;
}

export function AliveCard({ card, label, help }: { card: string; label: string; help: string }) {
  const t = useT();
  const [about, setAbout] = useState<AboutInfo | null>(null);

  useEffect(() => {
    getAbout().then(setAbout).catch(() => setAbout(null));
  }, []);

  if (!about) return null;
  const latest = about.releases[0];

  return (
    <div className={card + " p-4 mt-4"} data-testid="alive-card">
      <div className={label + " mb-2"}>{t("Maintained and current")}</div>

      {latest && (
        <div className="text-[12.5px] text-ink">
          {t("Latest release")}: <span className="font-medium">{latest.tag}</span>{" "}
          <span className="text-muted">· {when(latest.published_at, t)}</span>
        </div>
      )}
      {about.releases.length > 1 && (
        <div className="text-[11.5px] text-muted mt-0.5" data-testid="release-history">
          {t("Before that")}:{" "}
          {about.releases.slice(1, 4).map((r, i) => (
            <span key={r.tag}>
              {i > 0 && " · "}
              {r.tag} <span className="text-faint">{when(r.published_at, t)}</span>
            </span>
          ))}
        </div>
      )}

      <div className="text-[12.5px] text-ink mt-2.5">
        {about.models} {t("models from")} {about.providers} {t("providers")}
        <span className="text-muted"> · {t("the lineup is refreshed with every release")}</span>
      </div>
      <div className="text-[11.5px] text-muted mt-0.5">
        {t("Signed in with QualiTaTi? The model behind each Mimi tier is upgraded for you — nothing to install, nothing to choose.")}
      </div>

      <div className="text-[11.5px] text-muted mt-2.5 flex flex-wrap items-center gap-x-1.5">
        <span>
          {t("Built and maintained by")} <span className="text-ink">{about.maintainer}</span>
        </span>
        <span className="text-faint">·</span>
        <button className="text-accent hover:underline" onClick={() => openExternal(about.repo_url)}>
          {t("Source and releases")}
        </button>
        <span className="text-faint">·</span>
        <button className="text-accent hover:underline" onClick={() => openExternal(about.tutorial_url)}>
          {t("Tutorial")}
        </button>
      </div>
      <div className={help}>{t("Everything above is checkable — the release dates come from the public repository.")}</div>
    </div>
  );
}
