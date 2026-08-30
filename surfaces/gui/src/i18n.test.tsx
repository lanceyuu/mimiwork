import { describe, it, expect, afterEach } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { LANGS, getLang, installDomTranslations, setLang, tr, useT } from "./i18n";

afterEach(() => {
  setLang("en");
  cleanup();
});

function Probe({ s }: { s: string }) {
  const t = useT();
  return <span>{t(s)}</span>;
}

describe("i18n", () => {
  it("defaults to English and returns the source string untouched", () => {
    expect(getLang()).toBe("en");
    expect(tr("Inbox")).toBe("Inbox");
  });

  it("translates the frame strings in every language", () => {
    setLang("zh");
    expect(tr("Inbox")).toBe("收件箱");
    setLang("no");
    expect(tr("Ask for approval")).toBe("Spør om godkjenning");
    setLang("fr");
    expect(tr("Files")).toBe("Fichiers");
  });

  it("falls back to English for strings not yet translated", () => {
    setLang("zh");
    expect(tr("Some deep error message nobody translated")).toBe(
      "Some deep error message nobody translated",
    );
  });

  it("re-renders subscribed components when the language changes", () => {
    render(<Probe s="Settings" />);
    expect(screen.getByText("Settings")).toBeTruthy();
    act(() => setLang("fr"));
    expect(screen.getByText("Réglages")).toBeTruthy();
  });

  it("offers exactly the four owner-requested languages", () => {
    expect(LANGS.map((l) => l.value).sort()).toEqual(["en", "fr", "no", "zh"]);
  });

  it("localizes legacy interface text and accessibility labels", async () => {
    const { container } = render(
      <section>
        <button title="Choose location" aria-label="New session">Choose a folder</button>
        <input placeholder="Search chats" />
        <p data-no-translate>Settings</p>
      </section>,
    );
    const uninstall = installDomTranslations(container);

    act(() => setLang("fr"));
    await Promise.resolve();

    expect(screen.getByText("Choisir un dossier")).toBeTruthy();
    expect(screen.getByTitle("Choisir l'emplacement")).toBeTruthy();
    expect(screen.getByLabelText("Nouvelle session")).toBeTruthy();
    expect(screen.getByPlaceholderText("Rechercher des conversations")).toBeTruthy();
    expect(screen.getByText("Settings")).toBeTruthy();

    const lateButton = document.createElement("button");
    lateButton.textContent = "Delete";
    container.appendChild(lateButton);
    await waitFor(() => expect(screen.getByText("Supprimer")).toBeTruthy());
    uninstall();
  });

  it("can switch a legacy literal directly between translated languages", () => {
    const { container } = render(<span>Settings</span>);
    const uninstall = installDomTranslations(container);

    act(() => setLang("zh"));
    expect(screen.getByText("设置")).toBeTruthy();
    act(() => setLang("no"));
    expect(screen.getByText("Innstillinger")).toBeTruthy();
    uninstall();
  });
});
