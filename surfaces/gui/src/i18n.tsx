import { useSyncExternalStore } from "react";

// App languages (owner ask 2026-08-30): English, Chinese, Norwegian, French.
//
// Deliberately a tiny module, not a framework: dictionaries keyed by the ENGLISH
// source string, so call sites read as plain English (`t("Inbox")`) and an
// untranslated string falls back to itself rather than to a broken key. English
// is therefore always complete by construction, and tests that query by English
// text keep passing because the default language is English.
//
// Scope: the app's FRAME — sidebar, settings, composer, onboarding, tour. Deep
// copy (error messages, long settings prose) inherits English until translated;
// Mimi's own replies simply mirror whatever language the user types in.

export type Lang = "en" | "zh" | "no" | "fr";
export const LANGS: { value: Lang; label: string }[] = [
  { value: "en", label: "English" },
  { value: "zh", label: "中文" },
  { value: "no", label: "Norsk" },
  { value: "fr", label: "Français" },
];

// [zh, no, fr] — en is the key itself.
const D: Record<string, [string, string, string]> = {
  // ── sidebar ──
  "Inbox": ["收件箱", "Innboks", "Boîte de réception"],
  "Settings": ["设置", "Innstillinger", "Réglages"],
  "Connectors": ["连接器", "Koblinger", "Connecteurs"],
  "Automations": ["自动化", "Automatiseringer", "Automatisations"],
  "Activity": ["活动", "Aktivitet", "Activité"],
  "Files": ["文件", "Filer", "Fichiers"],
  "Projects": ["项目", "Prosjekter", "Projets"],
  "Sign out of QualiTaTi": ["退出 QualiTaTi", "Logg ut av QualiTaTi", "Se déconnecter de QualiTaTi"],
  // ── permission modes ──
  "Plan": ["规划", "Plan", "Plan"],
  "Ask for approval": ["先问再做", "Spør om godkjenning", "Demander l'approbation"],
  "Full access": ["完全放行", "Full tilgang", "Accès complet"],
  "Explore and propose a plan — nothing runs until you approve": [
    "先探索并提出方案——你批准之前什么都不执行",
    "Utforsk og foreslå en plan — ingenting kjører før du godkjenner",
    "Explorer et proposer un plan — rien ne s'exécute avant votre accord",
  ],
  "Ask before edits and commands": [
    "改动和命令前先询问",
    "Spør før endringer og kommandoer",
    "Demander avant modifications et commandes",
  ],
  "Run everything without asking": [
    "全部直接执行,不再询问",
    "Kjør alt uten å spørre",
    "Tout exécuter sans demander",
  ],
  // ── composer ──
  "Ask the coworker…  (drop or paste files)": [
    "向同事提问……(可拖入或粘贴文件)",
    "Spør medarbeideren …  (slipp eller lim inn filer)",
    "Demandez au coéquipier…  (déposez ou collez des fichiers)",
  ],
  "Stop": ["停止", "Stopp", "Arrêter"],
  // ── settings tabs ──
  "General": ["通用", "Generelt", "Général"],
  "Models": ["模型", "Modeller", "Modèles"],
  "Instructions": ["指令", "Instruksjoner", "Instructions"],
  "Skills": ["技能", "Ferdigheter", "Compétences"],
  "Voice input": ["语音输入", "Taleinndata", "Saisie vocale"],
  "Memory": ["记忆", "Minne", "Mémoire"],
  "Personas": ["角色", "Personaer", "Personas"],
  "Transfer guide": ["迁移指南", "Overføringsguide", "Guide de correspondance"],
  // ── settings ▸ general ──
  "Setup & updates": ["安装与更新", "Oppsett og oppdateringer", "Configuration et mises à jour"],
  "Run setup again": ["重新运行初始设置", "Kjør oppsettet på nytt", "Relancer la configuration"],
  "Show the tour": ["查看引导", "Vis omvisningen", "Voir la visite guidée"],
  "Replay the first-run setup, or the five-step tour of the interface.": [
    "重放首次设置,或界面的五步引导。",
    "Spill av førstegangsoppsettet eller femtrinnsomvisningen på nytt.",
    "Rejouer la configuration initiale ou la visite en cinq étapes.",
  ],
  "Language": ["语言", "Språk", "Langue"],
  "The app's own labels and menus. Mimi replies in whatever language you write.": [
    "应用界面的标签与菜单语言。Mimi 会用你输入的语言回复。",
    "Appens egne etiketter og menyer. Mimi svarer på språket du skriver.",
    "Les libellés et menus de l'app. Mimi répond dans la langue où vous écrivez.",
  ],
  // ── tour ──
  "Ask for the outcome, not the steps": [
    "说出你要的结果,而不是步骤",
    "Be om resultatet, ikke stegene",
    "Demandez le résultat, pas les étapes",
  ],
  "Three gears, one key": ["三个档位,一个按键", "Tre gir, én tast", "Trois vitesses, une touche"],
  "Your folder is the workspace": [
    "你的文件夹就是工作区",
    "Mappen din er arbeidsområdet",
    "Votre dossier est l'espace de travail",
  ],
  "Watch the work happen": ["看着工作进行", "Se arbeidet skje", "Regardez le travail se faire"],
  "Everything else lives here": ["其余一切都在这里", "Alt annet bor her", "Tout le reste vit ici"],
  "Skip tour": ["跳过引导", "Hopp over", "Passer la visite"],
  "Next": ["下一步", "Neste", "Suivant"],
  "Back": ["上一步", "Tilbake", "Retour"],
  "Done": ["完成", "Ferdig", "Terminé"],
  // ── onboarding ──
  "Welcome to MimiWork": ["欢迎使用 MimiWork", "Velkommen til MimiWork", "Bienvenue dans MimiWork"],
  "Skip setup": ["跳过设置", "Hopp over oppsett", "Ignorer la configuration"],
  "skip anyway": ["仍然跳过", "hopp over likevel", "ignorer quand même"],
  "Checking…": ["检查中……", "Sjekker …", "Vérification…"],
  "Create your QualiTaTi account — or sign in — and the Mimi models are ready to work, free tier included. No API keys.": [
    "注册 QualiTaTi 账号(或直接登录),Mimi 模型即刻可用,含每日免费档。无需 API 密钥。",
    "Opprett QualiTaTi-kontoen din — eller logg inn — så er Mimi-modellene klare, gratisnivå inkludert. Ingen API-nøkler.",
    "Créez votre compte QualiTaTi — ou connectez-vous — et les modèles Mimi sont prêts, niveau gratuit inclus. Aucune clé API.",
  ],
  "I'll use my own API key instead (OpenAI, Anthropic, Gemini…)": [
    "我想用自己的 API 密钥(OpenAI、Anthropic、Gemini……)",
    "Jeg bruker heller min egen API-nøkkel (OpenAI, Anthropic, Gemini …)",
    "J'utiliserai plutôt ma propre clé API (OpenAI, Anthropic, Gemini…)",
  ],
  "← Back to QualiTaTi sign-in": [
    "← 返回 QualiTaTi 登录",
    "← Tilbake til QualiTaTi-innlogging",
    "← Retour à la connexion QualiTaTi",
  ],
};

const IDX: Record<Lang, number> = { en: -1, zh: 0, no: 1, fr: 2 };

let current: Lang = "en";
const subs = new Set<() => void>();

export function getLang(): Lang {
  return current;
}
export function setLang(lang: Lang): void {
  if (lang === current) return;
  current = lang;
  subs.forEach((fn) => fn());
}
export function tr(s: string): string {
  if (current === "en") return s;
  const row = D[s];
  return row ? row[IDX[current]] : s;
}
/** Subscribe a component to language changes and get the translator. */
export function useT(): (s: string) => string {
  useSyncExternalStore(
    (cb) => {
      subs.add(cb);
      return () => subs.delete(cb);
    },
    () => current,
  );
  return tr;
}
