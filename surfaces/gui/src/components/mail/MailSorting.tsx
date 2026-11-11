import { useEffect, useState } from "react";
import { getMailSettings, putMailSettings, type MailSettings } from "../../api";
import { useT } from "../../i18n";
import { OFFLINE } from "./mailWork";

const offline = (): MailSettings => ({ ok: false, error: OFFLINE, sorting: false, excluded: [], sort_error: "" });

/** Asked once, the first time Mail is opened with a mailbox connected. Sorting sends the
 *  text of new mail to the model, so it is the user's to turn on, knowing what it does. */
export function MailSortingOffer({ onAnswer }: { onAnswer: (on: boolean) => void }) {
  const t = useT();
  // One answer: a second press, on either button, while the first is being saved is ignored.
  const [answered, setAnswered] = useState(false);
  const answer = (on: boolean) => {
    setAnswered(true);
    onAnswer(on);
  };
  return (
    <div className="mail-offer" role="region" aria-label={t("Let Mimi sort your mail?")} data-testid="mail-sorting-offer">
      <strong>{t("Let Mimi sort your mail?")}</strong>
      <p>
        {t("Mimi reads each new email to sort it into Needs reply, FYI and Newsletters, and writes one line on what it is about. This spends credits, like the rest of the app. It stays off until you turn it on.")}
      </p>
      <div className="mail-offer-actions">
        <button className="btn-primary" data-testid="mail-sorting-yes" disabled={answered} onClick={() => answer(true)}>
          {t("Turn on sorting")}
        </button>
        <button className="btn sm" data-testid="mail-sorting-no" disabled={answered} onClick={() => answer(false)}>
          {t("Not now")}
        </button>
      </div>
    </div>
  );
}

/** Mail's settings: the sorting switch, and whose mail is never sent to be sorted. */
export function MailSortingSettings({ onChanged, onClose }: { onChanged: () => void; onClose: () => void }) {
  const t = useT();
  const [settings, setSettings] = useState<MailSettings | null>(null);
  const [senders, setSenders] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let alive = true;
    getMailSettings()
      .catch(offline)
      .then((reply) => {
        if (!alive) return;
        if (!reply.ok) return setError(reply.error || OFFLINE);
        setSettings(reply);
        setSenders(reply.excluded.join("\n"));
      });
    return () => {
      alive = false;
    };
  }, []);

  const save = async (changes: { sorting?: boolean; excluded?: string[] }) => {
    setSaved(false);
    const reply = await putMailSettings(changes).catch(offline);
    if (!reply.ok) return setError(reply.error || OFFLINE);
    setError("");
    setSettings(reply);
    setSenders(reply.excluded.join("\n"));
    setSaved("excluded" in changes);
    onChanged();
  };

  return (
    <section className="mail-settings" data-testid="mail-settings" aria-label={t("Sorting")}>
      <div className="mail-settings-head">
        <strong>{t("Sorting")}</strong>
        <button className="mail-inline-link" data-testid="mail-settings-close" onClick={onClose}>{t("Close")}</button>
      </div>
      {settings && (
        <>
          <label className="mail-settings-switch">
            <input
              type="checkbox"
              data-testid="mail-sorting-switch"
              checked={settings.sorting}
              onChange={(event) => void save({ sorting: event.target.checked })}
            />
            <span>{t("Let Mimi sort new mail and write one line on each")}</span>
          </label>
          <p className="mail-side-hint">
            {t("Mimi reads each new email to do this, which spends credits like the rest of the app. Turning it off removes what she wrote.")}
          </p>
          <label className="mail-side-label">
            {t("Never send mail from these senders to be sorted")}
            <textarea
              className="tmpl-input mail-comment-note"
              data-testid="mail-excluded"
              rows={3}
              placeholder={"ana@example.com\n@example.com"}
              value={senders}
              onChange={(event) => {
                setSenders(event.target.value);
                setSaved(false);
              }}
            />
          </label>
          <p className="mail-side-hint">{t("One on each line: an address, or @ and a domain for everyone there.")}</p>
          <div className="mail-composer-actions">
            <button
              className="btn sm"
              data-testid="mail-excluded-save"
              onClick={() => void save({ excluded: senders.split("\n").map((line) => line.trim()).filter(Boolean) })}
            >
              {t("Save")}
            </button>
            {saved && <span className="mail-side-hint" role="status">{t("Saved.")}</span>}
          </div>
          {settings.sort_error && (
            <p className="mail-side-hint" data-testid="mail-sort-error" data-no-translate>{settings.sort_error}</p>
          )}
        </>
      )}
      {error && <div className="mail-error" role="alert" data-testid="mail-settings-error">{t(error)}</div>}
    </section>
  );
}
