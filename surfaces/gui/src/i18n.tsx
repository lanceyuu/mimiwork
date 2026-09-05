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
  "Mimi Hound uses account credits.": ["Mimi Hound 使用账户积分。", "Mimi Hound bruker kontokreditter.", "Mimi Hound utilise les crédits du compte."],
  "What should we produce?": ["我们要制作什么？", "Hva skal vi lage?", "Que voulez-vous créer ?"],
  "Choose a result, then attach your files or share a folder. You can edit the request before sending.": ["选择成果类型，再添加文件或共享文件夹。发送前可以修改请求。", "Velg et resultat, legg ved filer eller del en mappe. Du kan redigere forespørselen før du sender.", "Choisissez un résultat, puis joignez vos fichiers ou partagez un dossier. Vous pouvez modifier la demande avant de l’envoyer."],
  "Start with a file": ["从文件开始", "Start med en fil", "Commencer avec un fichier"],
  "Summarize into Word": ["汇总成 Word 文档", "Oppsummer i Word", "Résumer dans Word"],
  "Turn interviews or notes into a clear, editable report": ["将访谈或笔记整理为清晰、可编辑的报告", "Gjør intervjuer eller notater til en tydelig, redigerbar rapport", "Transformer des entretiens ou des notes en rapport clair et modifiable"],
  "Clean a spreadsheet": ["清理电子表格", "Rydd et regneark", "Nettoyer un tableur"],
  "Get an organized workbook with a record of changes": ["生成整理后的工作簿并记录修改", "Få en ryddig arbeidsbok med endringslogg", "Obtenir un classeur organisé avec un historique des modifications"],
  "Turn notes into slides": ["将笔记制作成幻灯片", "Gjør notater til lysbilder", "Transformer des notes en diapositives"],
  "Build an editable presentation with a clear story": ["制作条理清晰、可编辑的演示文稿", "Lag en redigerbar presentasjon med en tydelig fortelling", "Créer une présentation modifiable au récit clair"],
  "More ways to start": ["更多开始方式", "Flere måter å starte på", "Autres façons de commencer"],
  "Your files are saved. Open one to review it, or ask for changes.": ["文件已保存。打开查看，或提出修改要求。", "Filene dine er lagret. Åpne en for å se gjennom den, eller be om endringer.", "Vos fichiers sont enregistrés. Ouvrez-en un pour le vérifier ou demandez des modifications."],
  "Revise": ["修改", "Revider", "Réviser"],
  "One task can use several requests.": ["一个任务可能使用多次请求。", "Én oppgave kan bruke flere forespørsler.", "Une tâche peut utiliser plusieurs requêtes."],
  "Account credits": ["账户积分", "Kontokreditter", "Crédits du compte"],
  "Example and requirements": ["示例与要求", "Eksempel og krav", "Exemple et prérequis"],
  "Expected output": ["预期成果", "Forventet resultat", "Résultat attendu"],
  "What you need": ["所需材料与工具", "Dette trenger du", "Ce qu’il vous faut"],
  "Installation checked": ["安装已验证", "Installasjon kontrollert", "Installation vérifiée"],

  "Could not load skills. Try again.": ["无法加载技能，请重试。", "Kunne ikke laste ferdigheter. Prøv igjen.", "Impossible de charger les compétences. Réessayez."],
  "daily limit": ["每日额度", "daglig grense", "limite quotidienne"],
  "Search the skill store": ["搜索技能商店", "Søk i ferdighetsbutikken", "Rechercher dans la boutique de compétences"],
  "Clear search": ["清除搜索", "Tøm søket", "Effacer la recherche"],
  // ── EDGE (ch. 9) and the Five A's (ch. 7) ──
  "Where the value lands": ["价值落在哪里", "Hvor verdien lander", "Où atterrit la valeur"],
  "What makes them possible": ["是什么让它们成为可能", "Hva som gjør dem mulig", "Ce qui les rend possibles"],
  "Doing what you already do, faster and at greater scale": [
    "把本来就在做的事做得更快、规模更大", "Gjøre det du allerede gjør, raskere og i større skala",
    "Faire ce que vous faites déjà, plus vite et à plus grande échelle",
  ],
  "Insight synthesised from complex material, so you can choose": [
    "从复杂材料中综合出洞见,帮你做选择", "Innsikt syntetisert fra komplekst materiale, så du kan velge",
    "Une synthèse tirée de matériaux complexes, pour choisir",
  ],
  "Work that is new and different — the first time you try something": [
    "新产品与新收入——工具内部很难看见", "Nye tilbud og inntekter — sjelden synlig inne i et verktøy",
    "Un travail nouveau et différent — la première fois que vous essayez quelque chose",
  ],
  "What you learned, and what you made permanent": [
    "你学到的东西,以及你把它固定下来的部分", "Det du lærte, og det du gjorde varig",
    "Ce que vous avez appris, et ce que vous avez rendu permanent",
  ],
  "Growth is empty so far — it fills when you reach for something you have not used before, so it grows by trying a new kind of work rather than by doing more of the same.": [
    "Growth 目前是空的——当你去用以前没用过的东西时它才会涨。所以它靠尝试新的工作方式增长,而不是靠把同一件事做更多遍。",
    "Vekst er tom foreløpig — den fylles når du tar i bruk noe du ikke har brukt før, så den vokser ved å prøve en ny type arbeid, ikke ved å gjøre mer av det samme.",
    "La Croissance est encore vide — elle se remplit lorsque vous utilisez quelque chose que vous n'aviez jamais utilisé, elle croît donc en essayant un nouveau type de travail, pas en refaisant la même chose.",
  ],
  "How you work with Mimi": ["你与 Mimi 的协作方式", "Slik jobber du med Mimi", "Votre façon de travailler avec Mimi"],
  "Your turns placed on the Five A's continuum — by what they did, not what they were called.": [
    "把你的每一轮放在 Five A's 连续谱上——按它实际做了什么,而不是叫什么。",
    "Rundene dine plassert på Five A's-kontinuumet — etter hva de gjorde, ikke hva de het.",
    "Vos tours placés sur le continuum des Five A's — selon ce qu'ils ont fait, non leur nom.",
  ],
  "The model on its own, answering you directly": [
    "只有模型本身,直接回答你", "Modellen alene, som svarer deg direkte",
    "Le modèle seul, qui vous répond directement",
  ],
  "Grounded in your own documents, notes and knowledge base": [
    "基于你自己的文档、笔记和知识库", "Forankret i dine egne dokumenter, notater og kunnskapsbase",
    "Ancré dans vos propres documents, notes et base de connaissances",
  ],
  "One fixed recipe, one defined job — a skill or a command": [
    "一份固定配方、一个明确任务——一个技能或一条命令",
    "Én fast oppskrift, én definert jobb — en ferdighet eller en kommando",
    "Une recette fixe, une tâche définie — une compétence ou une commande",
  ],
  "A schedule started it and it followed the path it was given": [
    "由计划触发,并按既定路径执行",
    "En plan startet den, og den fulgte veien den fikk",
    "Un calendrier l'a lancé et il a suivi le chemin donné",
  ],
  "It chose its own next step, or reached across your systems": [
    "它自己决定下一步,或跨系统动了手",
    "Den valgte sitt eget neste steg, eller grep inn på tvers av systemene dine",
    "Il a choisi son étape suivante, ou est intervenu à travers vos systèmes",
  ],
  "more human involvement": ["人的参与更多", "mer menneskelig involvering", "plus d'intervention humaine"],
  "more autonomy": ["自主性更高", "mer autonomi", "plus d'autonomie"],
  "Mostly": ["主要是", "Mest", "Surtout"],
  "More": ["更多", "Mer", "Plus"],
  // ── "is this still alive?" card ──
  "Maintained and current": ["持续维护,保持最新", "Vedlikeholdt og oppdatert", "Maintenu et à jour"],
  "Latest release": ["最新版本", "Siste versjon", "Dernière version"],
  "Before that": ["此前", "Før det", "Avant cela"],
  "models from": ["个模型,来自", "modeller fra", "modèles de"],
  "providers": ["家服务商", "leverandører", "fournisseurs"],
  "the lineup is refreshed with every release": [
    "每次发版都会更新阵容", "utvalget oppdateres med hver utgivelse",
    "la sélection est actualisée à chaque version",
  ],
  "Signed in with QualiTaTi? The model behind each Mimi tier is upgraded for you — nothing to install, nothing to choose.": [
    "用 QualiTaTi 登录了?每个 Mimi 档位背后的模型会自动升级——无需安装,无需选择。",
    "Logget inn med QualiTaTi? Modellen bak hvert Mimi-nivå oppgraderes for deg — ingenting å installere, ingenting å velge.",
    "Connecté avec QualiTaTi ? Le modèle derrière chaque niveau Mimi est mis à niveau pour vous — rien à installer, rien à choisir.",
  ],
  "Built and maintained by": ["开发与维护者", "Laget og vedlikeholdt av", "Conçu et maintenu par"],
  "Source and releases": ["源码与版本", "Kildekode og utgivelser", "Code source et versions"],
  "Tutorial": ["教程", "Veiledning", "Tutoriel"],
  "Everything above is checkable — the release dates come from the public repository.": [
    "以上内容都可核查——发版日期来自公开代码仓库。",
    "Alt over kan etterprøves — utgivelsesdatoene kommer fra det offentlige kodelageret.",
    "Tout ceci est vérifiable — les dates de version proviennent du dépôt public.",
  ],
  "today": ["今天", "i dag", "aujourd'hui"],
  "yesterday": ["昨天", "i går", "hier"],
  "days ago": ["天前", "dager siden", "jours"],
  "last month": ["上个月", "forrige måned", "le mois dernier"],
  "months ago": ["个月前", "måneder siden", "mois"],
  // ── EDGE profile (Efficiency · Decisions · Growth · Empowerment) ──
  "How Mimi helps you": ["Mimi 如何帮到你", "Slik hjelper Mimi deg", "Comment Mimi vous aide"],
  "The same hours, grouped by the kind of help — the EDGE framework.": [
    "同样的时长,按帮助类型分组——EDGE 框架。",
    "De samme timene, gruppert etter typen hjelp — EDGE-rammeverket.",
    "Les mêmes heures, regroupées par type d'aide — le cadre EDGE.",
  ],
  "Efficiency": ["效率", "Effektivitet", "Efficacité"],
  "Decisions": ["决策", "Beslutninger", "Décisions"],
  "Growth": ["增长", "Vekst", "Croissance"],
  "Empowerment": ["赋能", "Myndiggjøring", "Autonomie"],
  "Work that had to happen anyway, done faster": [
    "本来就要做的工作,做得更快", "Arbeid som måtte gjøres uansett, gjort raskere",
    "Le travail à faire de toute façon, fait plus vite",
  ],
  "Evidence gathered and analysed so you can choose": [
    "收集并分析证据,帮你做选择", "Grunnlag samlet og analysert så du kan velge",
    "Des données réunies et analysées pour choisir",
  ],
  "Work aimed outward — decks, messages, delivery": [
    "面向外部的工作——演示、消息、交付", "Arbeid rettet utover — presentasjoner, meldinger, leveranser",
    "Le travail tourné vers l'extérieur — présentations, messages, livraisons",
  ],
  "Capability that outlasts the session": [
    "比这次会话更持久的能力", "Kapasitet som varer lenger enn økten",
    "Des capacités qui survivent à la session",
  ],
  // ── sidebar ──
  "Inbox": ["收件箱", "Innboks", "Boîte de réception"],
  "Settings": ["设置", "Innstillinger", "Réglages"],
  "Connectors": ["连接器", "Koblinger", "Connecteurs"],
  "Automations": ["自动化", "Automatiseringer", "Automatisations"],
  "Activity": ["活动", "Aktivitet", "Activité"],
  "Files": ["文件", "Filer", "Fichiers"],
  "saved so far": ["累计节省", "spart så langt", "gagnées jusqu'ici"],
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
  "Mimi Puppy's free allowance is used up for today": ["Mimi Puppy 今天的免费额度已用完", "Mimi Puppys gratiskvote er brukt opp for i dag", "Le quota gratuit de Mimi Puppy est épuisé pour aujourd'hui"],
  "resets at": ["将于以下时间重置：", "tilbakestilles kl.", "réinitialisé à"],
  "Switch to Mimi Hound": ["切换到 Mimi Hound", "Bytt til Mimi Hound", "Passer à Mimi Hound"],
  "Mimi Puppy": ["Mimi Puppy", "Mimi Puppy", "Mimi Puppy"],
  "free requests left today": ["次免费请求今天剩余", "gratis forespørsler igjen i dag", "requêtes gratuites restantes aujourd'hui"],
  // ── settings tabs ──
  "General": ["通用", "Generelt", "Général"],
  "Models": ["模型", "Modeller", "Modèles"],
  "Instructions": ["指令", "Instruksjoner", "Instructions"],
  "Skills": ["技能", "Ferdigheter", "Compétences"],
  "Search your skills…": ["搜索你的技能…", "Søk i ferdighetene dine…", "Rechercher vos compétences…"],
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
  // ── shared interface language ──
  "Add": ["添加", "Legg til", "Ajouter"],
  "Edit": ["编辑", "Rediger", "Modifier"],
  "Delete": ["删除", "Slett", "Supprimer"],
  "Delete?": ["确认删除?", "Slette?", "Supprimer ?"],
  "Remove": ["移除", "Fjern", "Retirer"],
  "Cancel": ["取消", "Avbryt", "Annuler"],
  "Close": ["关闭", "Lukk", "Fermer"],
  "Save": ["保存", "Lagre", "Enregistrer"],
  "Continue": ["继续", "Fortsett", "Continuer"],
  "Connect": ["连接", "Koble til", "Connecter"],
  "Connected": ["已连接", "Tilkoblet", "Connecté"],
  "Disconnect": ["断开连接", "Koble fra", "Déconnecter"],
  "Enable": ["启用", "Aktiver", "Activer"],
  "Disable": ["停用", "Deaktiver", "Désactiver"],
  "Loading…": ["加载中……", "Laster …", "Chargement…"],
  "Looking…": ["查找中……", "Leter …", "Recherche…"],
  "Search": ["搜索", "Søk", "Rechercher"],
  "Open": ["打开", "Åpne", "Ouvrir"],
  "Refresh": ["刷新", "Oppdater", "Actualiser"],
  "Copy": ["复制", "Kopier", "Copier"],
  "Copied": ["已复制", "Kopiert", "Copié"],
  "Try again": ["重试", "Prøv igjen", "Réessayer"],
  "Learn more": ["了解更多", "Finn ut mer", "En savoir plus"],
  "Coming soon": ["即将推出", "Kommer snart", "Bientôt disponible"],
  "default": ["默认", "standard", "par défaut"],
  "main": ["主目录", "hovedmappe", "principal"],
  "missing": ["缺失", "mangler", "manquant"],
  "Tasks": ["任务", "Oppgaver", "Tâches"],
  "Progress": ["进度", "Fremdrift", "Progression"],
  "Sources": ["来源", "Kilder", "Sources"],
  "Folders": ["文件夹", "Mapper", "Dossiers"],
  "Recommended": ["推荐", "Anbefalt", "Recommandé"],
  "Access": ["访问权限", "Tilgang", "Accès"],
  "Tools": ["工具", "Verktøy", "Outils"],
  "asks first": ["会先询问", "spør først", "demande d'abord"],
  "Coworker": ["同事", "Medarbeider", "Coéquipier"],
  "Search chats": ["搜索对话", "Søk i samtaler", "Rechercher des conversations"],
  "No chats found.": ["未找到对话。", "Ingen samtaler funnet.", "Aucune conversation trouvée."],
  "New session": ["新建会话", "Ny økt", "Nouvelle session"],
  "New project": ["新建项目", "Nytt prosjekt", "Nouveau projet"],
  "Artifacts": ["成果文件", "Resultatfiler", "Livrables"],
  "Try a task": ["试试这项任务", "Prøv en oppgave", "Essayez une tâche"],
  "Show sidebar": ["显示侧边栏", "Vis sidefelt", "Afficher la barre latérale"],
  "Session actions": ["会话操作", "Økthandlinger", "Actions de la session"],
  "Working now": ["正在工作", "Arbeider nå", "En cours"],
  "Sleeping (will wake itself)": ["休眠中(会自动唤醒)", "Sover (våkner av seg selv)", "En veille (se réveillera seul)"],
  "Group & filter conversations": ["分组并筛选对话", "Grupper og filtrer samtaler", "Grouper et filtrer les conversations"],
  "Choose a persona": ["选择角色", "Velg en persona", "Choisir un persona"],
  "Start with a specific persona": ["使用指定角色开始", "Start med en bestemt persona", "Démarrer avec un persona précis"],
  // ── onboarding ──
  "Pick a model provider — MimiWork runs on your own key, and your key and your data stay on this computer.": [
    "选择模型提供商——MimiWork 使用你自己的密钥运行,密钥和数据都保留在这台电脑上。",
    "Velg en modelltilbyder — MimiWork bruker din egen nøkkel, og både nøkkelen og dataene forblir på denne maskinen.",
    "Choisissez un fournisseur de modèles — MimiWork utilise votre propre clé, qui reste sur cet ordinateur avec vos données.",
  ],
  "Nothing works without a model —": ["没有模型就无法运行——", "Ingenting virker uten en modell —", "Rien ne fonctionne sans modèle —"],
  "Models can be enabled or hidden anytime in Settings ▸ Models.": [
    "可随时在“设置 ▸ 模型”中启用或隐藏模型。",
    "Modeller kan aktiveres eller skjules når som helst under Innstillinger ▸ Modeller.",
    "Les modèles peuvent être activés ou masqués à tout moment dans Réglages ▸ Modèles.",
  ],
  "Connect your everyday tools": ["连接常用工具", "Koble til verktøyene du bruker", "Connectez vos outils du quotidien"],
  "Chat can only advise. Connected, your coworker does the actual work:": [
    "聊天只能提供建议。连接后,你的 AI 同事就能实际执行工作:",
    "Chat kan bare gi råd. Når verktøyene er koblet til, gjør medarbeideren selve arbeidet:",
    "Le chat ne peut que conseiller. Une fois connecté, votre coéquipier effectue réellement le travail :",
  ],
  "Stay on top of email": ["掌握邮件动态", "Hold oversikt over e-post", "Gardez le contrôle de vos e-mails"],
  "Keep up with Slack": ["跟进 Slack 消息", "Følg med på Slack", "Suivez ce qui se passe sur Slack"],
  "Ship code": ["交付代码", "Lever kode", "Livrez du code"],
  "Keep your notes in reach": ["随时取用笔记", "Ha notatene for hånden", "Gardez vos notes à portée de main"],
  "Keep the CRM current": ["保持 CRM 最新", "Hold CRM-systemet oppdatert", "Gardez le CRM à jour"],
  "Track every relationship": ["跟进每一段关系", "Følg alle relasjoner", "Suivez chaque relation"],
  "Coming soon — pending Google’s app verification.": ["即将推出——正在等待 Google 应用验证。", "Kommer snart — avventer Googles appverifisering.", "Bientôt disponible — en attente de la validation de l'application par Google."],
  "Connect them when you need them": ["需要时再连接", "Koble dem til når du trenger dem", "Connectez-les quand vous en avez besoin"],
  "Every tool connects from the Connectors page with your own tokens or a local one-click sign-in — nothing goes through a third-party cloud.": [
    "每个工具都可在“连接器”页面使用你自己的令牌或本地一键登录进行连接——数据不会经过第三方云端。",
    "Alle verktøy kobles til fra Koblinger-siden med dine egne tokener eller lokal ettklikksinnlogging — ingenting går via en tredjepartssky.",
    "Chaque outil se connecte depuis la page Connecteurs avec vos propres jetons ou une connexion locale en un clic — rien ne transite par un cloud tiers.",
  ],
  "30+ more tools on the Connectors page — add or remove anytime. Tokens stay on this computer.": [
    "“连接器”页面还有 30 多种工具——可随时添加或移除。令牌保留在这台电脑上。",
    "Du finner over 30 andre verktøy på Koblinger-siden — legg til eller fjern dem når som helst. Tokener forblir på denne maskinen.",
    "Plus de 30 autres outils sont disponibles sur la page Connecteurs — ajoutez-les ou retirez-les à tout moment. Les jetons restent sur cet ordinateur.",
  ],
  "Give Mimi her first task": ["给 Mimi 第一个任务", "Gi Mimi hennes første oppgave", "Confiez sa première tâche à Mimi"],
  "Pick a folder Mimi may look at — everything stays on this computer, and she only ever sees folders you hand her.": [
    "选择一个允许 Mimi 查看的文件夹——所有内容都保留在这台电脑上,她只能看到你交给她的文件夹。",
    "Velg en mappe Mimi kan se i — alt forblir på denne maskinen, og hun ser bare mapper du gir henne tilgang til.",
    "Choisissez un dossier que Mimi peut consulter — tout reste sur cet ordinateur et elle ne voit que les dossiers que vous lui confiez.",
  ],
  "Choose a folder": ["选择文件夹", "Velg en mappe", "Choisir un dossier"],
  "Your course folder, a project, this week's mess — any folder works.": ["课程文件夹、项目或本周堆积的杂乱文件——任何文件夹都可以。", "Kursmappen, et prosjekt eller ukens rot — hvilken som helst mappe fungerer.", "Votre dossier de cours, un projet ou le désordre de la semaine — n'importe quel dossier convient."],
  "Allow Mimi to edit and organize files in it": ["允许 Mimi 编辑和整理其中的文件", "La Mimi redigere og organisere filene i den", "Autoriser Mimi à modifier et organiser les fichiers"],
  "Change": ["更改", "Endre", "Changer"],
  "Now pick her first task:": ["现在选择她的第一个任务:", "Velg nå hennes første oppgave:", "Choisissez maintenant sa première tâche :"],
  "Then pick her first task:": ["然后选择她的第一个任务:", "Velg deretter hennes første oppgave:", "Choisissez ensuite sa première tâche :"],
  "Summarize what's in this folder": ["总结此文件夹中的内容", "Oppsummer innholdet i denne mappen", "Résumer le contenu de ce dossier"],
  "Tidy and organize these files": ["整理这些文件", "Rydd og organiser disse filene", "Ranger et organiser ces fichiers"],
  "Plan my week from what's here": ["根据这里的内容规划本周", "Planlegg uken min ut fra innholdet her", "Planifier ma semaine à partir de ce dossier"],
  "Choose a folder first": ["请先选择文件夹", "Velg en mappe først", "Choisissez d'abord un dossier"],
  "Needs the edit permission above": ["需要启用上方的编辑权限", "Krever redigeringstillatelsen ovenfor", "Nécessite l'autorisation de modification ci-dessus"],
  "Uses the edit permission": ["使用编辑权限", "Bruker redigeringstillatelsen", "Utilise l'autorisation de modification"],
  "Create an automation instead": ["改为创建自动化", "Opprett en automatisering i stedet", "Créer plutôt une automatisation"],
  "Just open a blank session": ["仅打开空白会话", "Bare åpne en tom økt", "Ouvrir simplement une session vide"],
  "Replay this setup anytime: Settings ▸ Appearance ▸ Run setup again.": ["可随时重新运行此设置:“设置 ▸ 外观 ▸ 重新运行初始设置”。", "Kjør dette oppsettet på nytt når som helst: Innstillinger ▸ Utseende ▸ Kjør oppsettet på nytt.", "Relancez cette configuration à tout moment : Réglages ▸ Apparence ▸ Relancer la configuration."],
  // ── files, artifacts and session access ──
  "Nothing produced yet — files Mimi writes appear here.": ["尚未生成任何内容——Mimi 创建的文件会显示在这里。", "Ingenting er laget ennå — filer Mimi skriver vises her.", "Aucun livrable pour l'instant — les fichiers créés par Mimi apparaîtront ici."],
  "Show the folder where these files are saved": ["显示这些文件的保存文件夹", "Vis mappen der filene er lagret", "Afficher le dossier où ces fichiers sont enregistrés"],
  "Refresh artifacts": ["刷新成果文件", "Oppdater resultatfiler", "Actualiser les livrables"],
  "File recovery": ["文件恢复", "Filgjenoppretting", "Récupération de fichiers"],
  "file changed in Mimi's latest recoverable turn.": ["个文件在 Mimi 最近一次可恢复任务中发生了更改。", "fil ble endret i Mimis siste gjenopprettbare runde.", "fichier modifié lors de la dernière action récupérable de Mimi."],
  "files changed in Mimi's latest recoverable turn.": ["个文件在 Mimi 最近一次可恢复任务中发生了更改。", "filer ble endret i Mimis siste gjenopprettbare runde.", "fichiers modifiés lors de la dernière action récupérable de Mimi."],
  "Undo latest file changes": ["撤销最近的文件更改", "Angre siste filendringer", "Annuler les dernières modifications"],
  "Undo Mimi's latest file changes?": ["撤销 Mimi 最近的文件更改？", "Angre Mimis siste filendringer?", "Annuler les dernières modifications de Mimi ?"],
  "Restoring…": ["正在恢复……", "Gjenoppretter …", "Restauration…"],
  "Wait for Mimi to finish before restoring files": ["请等待 Mimi 完成任务后再恢复文件", "Vent til Mimi er ferdig før du gjenoppretter filer", "Attendez que Mimi ait terminé avant de restaurer les fichiers"],
  "Restore modified files and remove files created in that turn": ["恢复被修改的文件，并移除该任务中新建的文件", "Gjenopprett endrede filer og fjern filer som ble opprettet i denne runden", "Restaurer les fichiers modifiés et supprimer ceux créés pendant cette action"],
  "The available file changes have already been restored.": ["可用的文件更改已经恢复。", "De tilgjengelige filendringene er allerede gjenopprettet.", "Les modifications disponibles ont déjà été restaurées."],
  "Files could not be restored.": ["无法恢复文件。", "Filene kunne ikke gjenopprettes.", "Les fichiers n'ont pas pu être restaurés."],
  "Back to artifacts": ["返回成果文件", "Tilbake til resultatfiler", "Retour aux livrables"],
  "Reload preview": ["重新加载预览", "Last inn forhåndsvisningen på nytt", "Recharger l'aperçu"],
  "Open in default app": ["在默认应用中打开", "Åpne i standardappen", "Ouvrir dans l'application par défaut"],
  "Copy path": ["复制路径", "Kopier sti", "Copier le chemin"],
  "Copy full path": ["复制完整路径", "Kopier hele stien", "Copier le chemin complet"],
  "Show in folder": ["在文件夹中显示", "Vis i mappe", "Afficher dans le dossier"],
  "This folder is empty.": ["此文件夹为空。", "Denne mappen er tom.", "Ce dossier est vide."],
  "Empty file.": ["空文件。", "Tom fil.", "Fichier vide."],
  "Rendering PDF…": ["正在渲染 PDF……", "Gjengir PDF …", "Rendu du PDF…"],
  "Parsing spreadsheet…": ["正在解析电子表格……", "Leser regnearket …", "Analyse de la feuille de calcul…"],
  "The agent is requesting access to a folder": ["AI 同事正在请求访问文件夹", "Medarbeideren ber om tilgang til en mappe", "Le coéquipier demande l'accès à un dossier"],
  "Choose or paste a folder path…": ["选择或粘贴文件夹路径……", "Velg eller lim inn en mappesti …", "Choisissez ou collez le chemin d'un dossier…"],
  "Choose location": ["选择位置", "Velg plassering", "Choisir l'emplacement"],
  "Session access": ["会话访问权限", "Økttilgang", "Accès de la session"],
  "Search connectors…": ["搜索连接器……", "Søk i koblinger …", "Rechercher des connecteurs…"],
  "Add a channel": ["添加频道", "Legg til en kanal", "Ajouter un canal"],
  "Stop listening": ["停止监听", "Slutt å lytte", "Arrêter l'écoute"],
  "Back to sources": ["返回来源", "Tilbake til kilder", "Retour aux sources"],
  // ── settings ──
  "How MimiWork looks and behaves on this machine.": ["MimiWork 在这台电脑上的外观与行为。", "Hvordan MimiWork ser ut og oppfører seg på denne maskinen.", "L'apparence et le comportement de MimiWork sur cet ordinateur."],
  "Theme": ["主题", "Tema", "Thème"],
  "Appearance": ["外观", "Utseende", "Apparence"],
  "System": ["跟随系统", "System", "Système"],
  "Light": ["浅色", "Lys", "Clair"],
  "Dark": ["深色", "Mørk", "Sombre"],
  "Auto follows your Mac’s appearance.": ["自动模式会跟随 Mac 的外观设置。", "Auto følger utseendet på Mac-en.", "Le mode Auto suit l'apparence de votre Mac."],
  "Always-on": ["常驻设置", "Alltid på", "Toujours actif"],
  "Open at login": ["登录时打开", "Åpne ved innlogging", "Ouvrir à la connexion"],
  "Launch MimiWork automatically when you sign in.": ["登录时自动启动 MimiWork。", "Start MimiWork automatisk når du logger inn.", "Lancer MimiWork automatiquement à votre connexion."],
  "Keep this system awake": ["保持系统唤醒", "Hold systemet våkent", "Maintenir le système actif"],
  "Prevent idle sleep so scheduled tasks fire on time.": ["防止系统闲置休眠,确保计划任务准时运行。", "Hindre hvilemodus slik at planlagte oppgaver kjører i tide.", "Empêcher la mise en veille afin que les tâches planifiées s'exécutent à l'heure."],
  "Floating Mimi": ["悬浮 Mimi", "Flytende Mimi", "Mimi flottante"],
  "Trusted workspaces": ["受信任的工作区", "Klarerte arbeidsområder", "Espaces de travail approuvés"],
  "No workspaces are trusted.": ["没有受信任的工作区。", "Ingen arbeidsområder er klarert.", "Aucun espace de travail n'est approuvé."],
  "Token savings": ["令牌节省", "Tokenbesparelser", "Économie de jetons"],
  "PDFs on models without native PDF support": ["不原生支持 PDF 的模型如何处理 PDF", "PDF-er på modeller uten innebygd PDF-støtte", "PDF avec les modèles sans prise en charge native"],
  "PDF fallback": ["PDF 后备处理", "PDF-reserveløsning", "Solution de repli PDF"],
  "Extract text": ["提取文本", "Trekk ut tekst", "Extraire le texte"],
  "Render pages": ["渲染页面", "Gjengi sider", "Rendre les pages"],
  "Max pages": ["最大页数", "Maks sider", "Nombre maximal de pages"],
  "Max size": ["最大大小", "Maks størrelse", "Taille maximale"],
  "Context compaction": ["上下文压缩", "Kontekstkomprimering", "Compactage du contexte"],
  "Compact at": ["压缩阈值", "Komprimer ved", "Compacter à"],
  "or at": ["或达到", "eller ved", "ou à"],
  "tokens, whichever is smaller": ["个令牌,以较小者为准", "tokener, avhengig av hva som er minst", "jetons, selon la valeur la plus basse"],
  "Summarizer model": ["摘要模型", "Oppsummeringsmodell", "Modèle de résumé"],
  "Session’s own model (default)": ["会话使用的模型(默认)", "Øktens egen modell (standard)", "Modèle de la session (par défaut)"],
  "Composer": ["输入框", "Meldingsfelt", "Zone de message"],
  "Show the context window bar": ["显示上下文窗口栏", "Vis kontekstvindu-linjen", "Afficher la barre de fenêtre de contexte"],
  "Sidebar": ["侧边栏", "Sidefelt", "Barre latérale"],
  "Conversations shown per coworker": ["每位 AI 同事显示的对话数", "Samtaler som vises per medarbeider", "Conversations affichées par coéquipier"],
  "Pick a folder": ["选择文件夹", "Velg en mappe", "Choisir un dossier"],
  "Providers and the models offered in the composer's picker. Keys are stored only on this computer.": ["提供商及输入框模型选择器中显示的模型。密钥仅存储在这台电脑上。", "Tilbydere og modellene som vises i meldingsfeltets modellvelger. Nøkler lagres bare på denne maskinen.", "Fournisseurs et modèles proposés dans le sélecteur de la zone de message. Les clés sont stockées uniquement sur cet ordinateur."],
  "Voice Input setup is available in the MimiWork desktop app.": ["语音输入设置仅在 MimiWork 桌面应用中提供。", "Oppsett av taleinndata er tilgjengelig i MimiWork-skrivebordsappen.", "La configuration de la saisie vocale est disponible dans l'application de bureau MimiWork."],
  "Private by design.": ["隐私优先设计。", "Privat som standard.", "Confidentiel par conception."],
  "Audio is held in memory only while you record and is transcribed locally.": ["音频仅在录音期间保存在内存中,并在本地转录。", "Lyd lagres bare i minnet mens du tar opp og transkriberes lokalt.", "L'audio n'est conservé en mémoire que pendant l'enregistrement et est transcrit localement."],
  "This device": ["此设备", "Denne enheten", "Cet appareil"],
  "Processor": ["处理器", "Prosessor", "Processeur"],
  "Verified": ["已验证", "Verifisert", "Vérifié"],
  "Repair": ["修复", "Reparer", "Réparer"],
  "Verifying…": ["验证中……", "Verifiserer …", "Vérification…"],
  "Download model": ["下载模型", "Last ned modell", "Télécharger le modèle"],
  "Microphone test": ["麦克风测试", "Mikrofontest", "Test du microphone"],
  // ── automations, files and activity ──
  "Recurring tasks MimiWork runs on a schedule.": ["MimiWork 按计划运行的重复任务。", "Gjentakende oppgaver MimiWork kjører etter en tidsplan.", "Tâches récurrentes exécutées par MimiWork selon un calendrier."],
  "Model": ["模型", "Modell", "Modèle"],
  "Permission": ["权限", "Tillatelse", "Autorisation"],
  "At": ["时间", "Kl.", "À"],
  "Repeat": ["重复", "Gjenta", "Répéter"],
  "Every day": ["每天", "Hver dag", "Tous les jours"],
  "Weekdays": ["工作日", "Ukedager", "Jours de semaine"],
  "Weekends": ["周末", "Helger", "Week-ends"],
  "Works in:": ["工作位置:", "Arbeider i:", "Travaille dans :"],
  "Title": ["标题", "Tittel", "Titre"],
  "Allowed without asking": ["无需询问即可执行", "Tillatt uten å spørre", "Autorisé sans demander"],
  "Runs": ["运行记录", "Kjøringer", "Exécutions"],
  "No runs yet.": ["尚无运行记录。", "Ingen kjøringer ennå.", "Aucune exécution pour l'instant."],
  "new": ["新", "ny", "nouveau"],
  "Delete automation": ["删除自动化", "Slett automatisering", "Supprimer l'automatisation"],
  "No audit events yet.": ["尚无活动记录。", "Ingen aktivitetshendelser ennå.", "Aucun événement d'activité pour l'instant."],
  "Credits": ["积分", "Kreditter", "Crédits"],
  "filter…": ["筛选……", "filtrer …", "filtrer…"],
  "No entries.": ["没有条目。", "Ingen oppføringer.", "Aucune entrée."],
  "file truncated for review": ["文件已截断以供审阅", "filen er forkortet for gjennomgang", "fichier tronqué pour la révision"],
  "No versions yet — save an edit to start history.": ["尚无版本——保存一次编辑即可开始记录历史。", "Ingen versjoner ennå — lagre en endring for å starte historikken.", "Aucune version pour l'instant — enregistrez une modification pour commencer l'historique."],
  // ── home and first session ──
  "Dismiss": ["关闭", "Avvis", "Fermer"],
  "Show sidebar (⌘B)": ["显示侧边栏 (⌘B)", "Vis sidefelt (⌘B)", "Afficher la barre latérale (⌘B)"],
  "Show files this conversation produced": ["显示此对话生成的文件", "Vis filer denne samtalen har laget", "Afficher les fichiers produits par cette conversation"],
  "Work in a folder": ["在文件夹中工作", "Arbeid i en mappe", "Travailler dans un dossier"],
  "I'll read what's there and produce what you need": ["我会读取其中的内容并生成你需要的成果", "Jeg leser innholdet og lager det du trenger", "Je lirai son contenu et produirai ce dont vous avez besoin"],
  "Pick a folder →": ["选择文件夹 →", "Velg en mappe →", "Choisir un dossier →"],
  "Build a deck from my Canva designs": ["根据我的 Canva 设计制作演示文稿", "Lag en presentasjon fra Canva-designene mine", "Créer une présentation à partir de mes designs Canva"],
  "Package your style guidelines into a skill": ["将风格指南打包为技能", "Pakk stilretningslinjene dine som en ferdighet", "Transformer vos règles de style en compétence"],
  "Start →": ["开始 →", "Start →", "Commencer →"],
  // ── accounts, models and skills ──
  "QualiTaTi account": ["QualiTaTi 账户", "QualiTaTi-konto", "Compte QualiTaTi"],
  "Your QualiTaTi work is available here.": ["你在 QualiTaTi 中的工作可在此访问。", "QualiTaTi-arbeidet ditt er tilgjengelig her.", "Votre travail QualiTaTi est disponible ici."],
  "Model region": ["模型区域", "Modellregion", "Région du modèle"],
  "MFA code": ["多重验证代码", "MFA-kode", "Code MFA"],
  "Account": ["账户", "Konto", "Compte"],
  "Username": ["用户名", "Brukernavn", "Nom d'utilisateur"],
  "Password": ["密码", "Passord", "Mot de passe"],
  "Email": ["电子邮箱", "E-post", "E-mail"],
  "Confirm password": ["确认密码", "Bekreft passord", "Confirmer le mot de passe"],
  "Invite code (optional)": ["邀请码(可选)", "Invitasjonskode (valgfritt)", "Code d'invitation (facultatif)"],
  "Not set up": ["未设置", "Ikke konfigurert", "Non configuré"],
  "Copy command": ["复制命令", "Kopier kommando", "Copier la commande"],
  "Runs one read-only check, then saves.": ["运行一次只读检查,然后保存。", "Kjører én skrivebeskyttet kontroll og lagrer deretter.", "Effectue une vérification en lecture seule, puis enregistre."],
  "Test & save": ["测试并保存", "Test og lagre", "Tester et enregistrer"],
  "Included models": ["包含的模型", "Inkluderte modeller", "Modèles inclus"],
  "In the composer's picker": ["在输入框的模型选择器中", "I modellvelgeren i meldingsfeltet", "Dans le sélecteur de la zone de message"],
  "Enable this server": ["启用此服务器", "Aktiver denne serveren", "Activer ce serveur"],
  "waiting for browser…": ["等待浏览器……", "venter på nettleseren …", "en attente du navigateur…"],
  "No tools.": ["没有工具。", "Ingen verktøy.", "Aucun outil."],
  "Paste server JSON (name → config):": ["粘贴服务器 JSON(名称 → 配置):", "Lim inn server-JSON (navn → konfigurasjon):", "Collez le JSON du serveur (nom → configuration) :"],
  "Tools exposed to MimiWork": ["向 MimiWork 提供的工具", "Verktøy som er tilgjengelige for MimiWork", "Outils mis à disposition de MimiWork"],
  "or connect manually:": ["或手动连接:", "eller koble til manuelt:", "ou connecter manuellement :"],
  "Write it myself": ["自己编写", "Skriv den selv", "L'écrire moi-même"],
  "Import a file": ["导入文件", "Importer en fil", "Importer un fichier"],
  "Create with MimiWork": ["使用 MimiWork 创建", "Lag med MimiWork", "Créer avec MimiWork"],
  "Import from Claude Code": ["从 Claude Code 导入", "Importer fra Claude Code", "Importer depuis Claude Code"],
  "Browse the skill store": ["浏览技能商店", "Bla i ferdighetsbutikken", "Parcourir la boutique de compétences"],
  "Upload a skill archive": ["上传技能压缩包", "Last opp et ferdighetsarkiv", "Téléverser une archive de compétence"],
  "Skill store": ["技能商店", "Ferdighetsbutikk", "Boutique de compétences"],
  "Search skills… (e.g. seo audit, meeting notes, resume)": ["搜索技能……(例如 SEO 审计、会议记录、简历)", "Søk etter ferdigheter … (f.eks. SEO-revisjon, møtereferat, CV)", "Rechercher des compétences… (p. ex. audit SEO, notes de réunion, CV)"],
  "Close preview": ["关闭预览", "Lukk forhåndsvisning", "Fermer l'aperçu"],
  "Wants to use:": ["需要使用:", "Ønsker å bruke:", "Souhaite utiliser :"],
  "Review before installing": ["安装前审阅", "Se gjennom før installasjon", "Vérifier avant l'installation"],
  "One line the worker uses to decide when this applies": ["用一句话说明何时使用此技能", "Én linje medarbeideren bruker for å avgjøre når dette gjelder", "Une phrase permettant au coéquipier de décider quand l'utiliser"],
  "Show folder": ["显示文件夹", "Vis mappe", "Afficher le dossier"],
  // ── memory, personas and projects ──
  "Remember new things about you": ["记住关于你的新信息", "Husk nye ting om deg", "Mémoriser de nouvelles informations à votre sujet"],
  "Remember new things about me": ["记住关于我的新信息", "Husk nye ting om meg", "Mémoriser de nouvelles informations à mon sujet"],
  "What I've learned about you": ["我对你的了解", "Det jeg har lært om deg", "Ce que j'ai appris à votre sujet"],
  "Your instructions": ["你的指令", "Instruksjonene dine", "Vos instructions"],
  "Fix this": ["修正此项", "Rett dette", "Corriger ceci"],
  "Delete this memory": ["删除此记忆", "Slett dette minnet", "Supprimer ce souvenir"],
  "Default for new sessions": ["新会话的默认角色", "Standard for nye økter", "Par défaut pour les nouvelles sessions"],
  "Delete this persona": ["删除此角色", "Slett denne personaen", "Supprimer ce persona"],
  "Add personas": ["添加角色", "Legg til personaer", "Ajouter des personas"],
  "GitHub URL": ["GitHub 网址", "GitHub-URL", "URL GitHub"],
  "Local directory": ["本地目录", "Lokal mappe", "Répertoire local"],
  "Change emoji": ["更改表情符号", "Endre emoji", "Changer l'emoji"],
  "Project name": ["项目名称", "Prosjektnavn", "Nom du projet"],
  "Open in your file manager": ["在文件管理器中打开", "Åpne i filbehandleren", "Ouvrir dans le gestionnaire de fichiers"],
  "What Mimi remembers about this project": ["Mimi 对此项目的记忆", "Det Mimi husker om dette prosjektet", "Ce que Mimi retient de ce projet"],
  "Edit memory": ["编辑记忆", "Rediger minne", "Modifier le souvenir"],
  "Forget": ["忘记", "Glem", "Oublier"],
  "Forget memory": ["删除记忆", "Glem minnet", "Oublier le souvenir"],
  "Add a fact about this project…": ["添加关于此项目的信息……", "Legg til et faktum om dette prosjektet …", "Ajouter une information sur ce projet…"],
  "Conversations": ["对话", "Samtaler", "Conversations"],
  // ── connectors ──
  "MCP servers": ["MCP 服务器", "MCP-servere", "Serveurs MCP"],
  "Available": ["可用", "Tilgjengelig", "Disponibles"],
  "Nothing matches.": ["没有匹配项。", "Ingen treff.", "Aucun résultat."],
  "Not connected": ["未连接", "Ikke tilkoblet", "Non connecté"],
  "Accounts": ["账户", "Kontoer", "Comptes"],
  "Portals": ["门户", "Portaler", "Portails"],
  "Default": ["默认", "Standard", "Par défaut"],
  "Sandbox": ["沙盒", "Sandkasse", "Bac à sable"],
  "private app": ["私有应用", "privat app", "application privée"],
  "Add an account": ["添加账户", "Legg til en konto", "Ajouter un compte"],
  "Add a portal": ["添加门户", "Legg til en portal", "Ajouter un portail"],
  "Add an installation": ["添加安装", "Legg til en installasjon", "Ajouter une installation"],
  "Add a workspace": ["添加工作区", "Legg til et arbeidsområde", "Ajouter un espace de travail"],
  "Disconnect this account": ["断开此账户", "Koble fra denne kontoen", "Déconnecter ce compte"],
  "Disconnect this mailbox": ["断开此邮箱", "Koble fra denne postboksen", "Déconnecter cette boîte mail"],
  "Disconnect this portal": ["断开此门户", "Koble fra denne portalen", "Déconnecter ce portail"],
  "Never show agents": ["绝不向 AI 同事显示", "Vis aldri til medarbeidere", "Ne jamais montrer aux coéquipiers"],
  "Access & privacy": ["访问与隐私", "Tilgang og personvern", "Accès et confidentialité"],
  "Hidden fields": ["隐藏字段", "Skjulte felt", "Champs masqués"],
  "Property name, e.g. salary": ["属性名称,例如 salary", "Egenskapsnavn, f.eks. lønn", "Nom de propriété, p. ex. salaire"],
  "People": ["人员", "Personer", "Personnes"],
  "Waiting": ["等待中", "Venter", "En attente"],
  "Listening": ["监听中", "Lytter", "À l'écoute"],
  "Approvals": ["审批", "Godkjenninger", "Approbations"],
  "Type a name…": ["输入姓名……", "Skriv inn et navn …", "Saisissez un nom…"],
  "no matches": ["无匹配项", "ingen treff", "aucun résultat"],
  "Pick from the workspace directory": ["从工作区目录中选择", "Velg fra arbeidsområdekatalogen", "Choisir dans l'annuaire de l'espace de travail"],
  "Set by the workspace installer.": ["由工作区安装者设置。", "Angitt av den som installerte arbeidsområdet.", "Défini par la personne ayant installé l'espace de travail."],
  "Recent senders": ["最近的发送者", "Nylige avsendere", "Expéditeurs récents"],
  "Allowed to message": ["获准发送消息", "Har lov til å sende meldinger", "Autorisés à envoyer des messages"],
  // ── remaining controls and secondary views ──
  "In the message box": ["在消息输入框中", "I meldingsfeltet", "Dans la zone de message"],
  "In MimiWork": ["在 MimiWork 中", "I MimiWork", "Dans MimiWork"],
  "Persona": ["角色", "Persona", "Persona"],
  "Enable this persona": ["启用此角色", "Aktiver denne personaen", "Activer ce persona"],
  "About": ["关于", "Om", "À propos"],
  "Built-in capabilities": ["内置能力", "Innebygde funksjoner", "Fonctionnalités intégrées"],
  "Connections for full benefit": ["充分发挥作用所需的连接", "Tilkoblinger for full nytte", "Connexions pour en profiter pleinement"],
  "core": ["核心", "kjerne", "essentiel"],
  "New sessions get by default": ["新会话的默认设置", "Nye økter får som standard", "Paramètres par défaut des nouvelles sessions"],
  "Default mode": ["默认模式", "Standardmodus", "Mode par défaut"],
  "Workspace": ["工作区", "Arbeidsområde", "Espace de travail"],
  "Model family": ["模型系列", "Modellfamilie", "Famille de modèles"],
  "Add another model…": ["添加其他模型……", "Legg til en annen modell …", "Ajouter un autre modèle…"],
  "Channels this session listens to": ["此会话监听的频道", "Kanaler denne økten lytter til", "Canaux écoutés par cette session"],
  "Not subscribed to any channel.": ["未订阅任何频道。", "Abonnerer ikke på noen kanal.", "Aucun abonnement à un canal."],
  "Unsubscribe": ["取消订阅", "Avslutt abonnement", "Se désabonner"],
  "Trust this workspace’s commands?": ["信任此工作区的命令?", "Stole på kommandoene i dette arbeidsområdet?", "Faire confiance aux commandes de cet espace de travail ?"],
  "Repository": ["代码仓库", "Kodelager", "Dépôt"],
  "Topics to follow": ["关注主题", "Emner å følge", "Sujets à suivre"],
  "e.g. AI in consumer research; qualitative methods": ["例如 消费者研究中的 AI;定性研究方法", "f.eks. KI i forbrukerforskning; kvalitative metoder", "p. ex. IA dans les études consommateurs ; méthodes qualitatives"],
  "Post to channel": ["发布到频道", "Publiser i kanal", "Publier dans le canal"],
  "When": ["时间", "Når", "Quand"],
  "Time": ["时间", "Tid", "Heure"],
  "Deliver to": ["发送到", "Lever til", "Livrer à"],
  "Stop this session": ["停止此会话", "Stopp denne økten", "Arrêter cette session"],
  "The agent proposed a plan": ["AI 同事提出了一个计划", "Medarbeideren foreslo en plan", "Le coéquipier a proposé un plan"],
  "What should change about the plan?": ["计划需要做哪些更改?", "Hva bør endres i planen?", "Que faut-il modifier dans le plan ?"],
  "Unrouted": ["未路由", "Ikke rutet", "Non acheminés"],
  "Unattended approvals": ["无人处理的审批", "Ubetjente godkjenninger", "Approbations sans surveillance"],
  "Direct messages": ["私信", "Direktemeldinger", "Messages directs"],
  "No session — park DMs": ["无会话——暂存私信", "Ingen økt — parker direktemeldinger", "Aucune session — mettre les messages directs en attente"],
  "Channel subscriptions": ["频道订阅", "Kanalabonnementer", "Abonnements aux canaux"],
  "Session": ["会话", "Økt", "Session"],
  "Listens to": ["监听", "Lytter til", "Écoute"],
  "Inbox routes to": ["收件箱路由到", "Innboks ruter til", "La boîte de réception achemine vers"],
  "Choose a session…": ["选择会话……", "Velg en økt …", "Choisir une session…"],
  "Source": ["来源", "Kilde", "Source"],
  "Reason": ["原因", "Årsak", "Raison"],
  "Message": ["消息", "Melding", "Message"],
  "Update available": ["有可用更新", "Oppdatering tilgjengelig", "Mise à jour disponible"],
  "Off = read-only. Tick to let the agent write here.": ["关闭 = 只读。勾选后允许 AI 同事在此写入。", "Av = skrivebeskyttet. Kryss av for å la medarbeideren skrive her.", "Désactivé = lecture seule. Cochez pour autoriser le coéquipier à écrire ici."],
  "Previous question": ["上一个问题", "Forrige spørsmål", "Question précédente"],
  "Copy message": ["复制消息", "Kopier melding", "Copier le message"],
  "assistant": ["AI 同事", "medarbeider", "coéquipier"],
  "proposed plan": ["建议的计划", "foreslått plan", "plan proposé"],
  "Retry": ["重试", "Prøv igjen", "Réessayer"],
  "more…": ["更多……", "mer …", "plus…"],
  "less…": ["收起……", "mindre …", "moins…"],
  "Thought process": ["思考过程", "Tankeprosess", "Raisonnement"],
  "Thinking…": ["思考中……", "Tenker …", "Réflexion…"],
  "Granted folder access": ["已授予文件夹访问权限", "Mappetilgang innvilget", "Accès au dossier accordé"],
  "Declined folder access": ["已拒绝文件夹访问权限", "Mappetilgang avslått", "Accès au dossier refusé"],
  "Plan approved": ["计划已批准", "Plan godkjent", "Plan approuvé"],
  "Sent back with feedback": ["已退回并附上反馈", "Sendt tilbake med tilbakemelding", "Renvoyé avec des commentaires"],
  "Click to dismiss": ["点击关闭", "Klikk for å avvise", "Cliquer pour fermer"],
  "Open MimiWork (drag to move)": ["打开 MimiWork(拖动可移动)", "Åpne MimiWork (dra for å flytte)", "Ouvrir MimiWork (faire glisser pour déplacer)"],
  "Hide floating Mimi": ["隐藏悬浮 Mimi", "Skjul flytende Mimi", "Masquer Mimi flottante"],
  "Enabled for this session — tap to mute here": ["已为此会话启用——点击可在此会话中静音", "Aktivert for denne økten — trykk for å dempe her", "Activé pour cette session — cliquez pour désactiver ici"],
  "Commands and skills": ["命令和技能", "Kommandoer og ferdigheter", "Commandes et compétences"],
  "Looking for files…": ["正在查找文件……", "Leter etter filer …", "Recherche de fichiers…"],
  "Attach": ["附加文件", "Legg ved", "Joindre"],
  "Transcribing…": ["转录中……", "Transkriberer …", "Transcription…"],
  "Connect a model": ["连接模型", "Koble til en modell", "Connecter un modèle"],
  "No model connected — connect a model": ["未连接模型——连接模型", "Ingen modell er tilkoblet — koble til en modell", "Aucun modèle connecté — connecter un modèle"],
  "No model": ["无模型", "Ingen modell", "Aucun modèle"],
  "Fetching the model list from the server": ["正在从服务器获取模型列表", "Henter modellisten fra serveren", "Récupération de la liste des modèles depuis le serveur"],
  "Loading models…": ["加载模型中……", "Laster modeller …", "Chargement des modèles…"],
  "Send": ["发送", "Send", "Envoyer"],
  "Token usage": ["令牌用量", "Tokenbruk", "Utilisation des jetons"],
  "Total": ["总计", "Totalt", "Total"],
  "Mode": ["模式", "Modus", "Mode"],
  "Send approvals to Inbox": ["将审批发送到收件箱", "Send godkjenninger til Innboks", "Envoyer les approbations dans la boîte de réception"],
  "Send approvals to the Inbox": ["将审批发送到收件箱", "Send godkjenninger til Innboks", "Envoyer les approbations dans la boîte de réception"],
  "Click again to permanently delete": ["再次点击将永久删除", "Klikk igjen for å slette permanent", "Cliquez à nouveau pour supprimer définitivement"],
  "New project (pick a folder)": ["新建项目(选择文件夹)", "Nytt prosjekt (velg en mappe)", "Nouveau projet (choisir un dossier)"],
  "Group and filter conversations": ["分组并筛选对话", "Grupper og filtrer samtaler", "Grouper et filtrer les conversations"],
  "Signed in to QualiTaTi": ["已登录 QualiTaTi", "Logget inn på QualiTaTi", "Connecté à QualiTaTi"],
  "Open qualitati.com": ["打开 qualitati.com", "Åpne qualitati.com", "Ouvrir qualitati.com"],
  "Powered by": ["技术支持:", "Drevet av", "Propulsé par"],
  "Reload": ["重新加载", "Last inn på nytt", "Recharger"],
  "Loading...": ["加载中……", "Laster …", "Chargement…"],
  "Empty sheet.": ["空工作表。", "Tomt ark.", "Feuille vide."],
};

const IDX: Record<Lang, number> = { en: -1, zh: 0, no: 1, fr: 2 };
const SOURCE_BY_TRANSLATION = new Map<string, string>();
for (const [source, translations] of Object.entries(D)) {
  SOURCE_BY_TRANSLATION.set(source, source);
  translations.forEach((translation) => SOURCE_BY_TRANSLATION.set(translation, source));
}

let current: Lang = "en";
const subs = new Set<() => void>();

export function getLang(): Lang {
  return current;
}
export function setLang(lang: Lang): void {
  if (lang === current) return;
  current = lang;
  if (typeof document !== "undefined") {
    document.documentElement.lang = lang === "no" ? "nb" : lang === "zh" ? "zh-CN" : lang;
    translateSubtree(document.body);
  }
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

const ATTRS = ["aria-label", "placeholder", "title"] as const;
let observer: MutationObserver | null = null;

function englishSource(value: string): string {
  return SOURCE_BY_TRANSLATION.get(value) ?? value;
}

function translatedValue(value: string): string {
  const leading = value.match(/^\s*/)?.[0] ?? "";
  const trailing = value.match(/\s*$/)?.[0] ?? "";
  const core = value.slice(leading.length, value.length - trailing.length);
  if (!core) return value;
  const translated = tr(englishSource(core));
  return translated === core ? value : leading + translated + trailing;
}

function translateElement(element: Element): void {
  if (element.closest("[data-no-translate]")) return;
  for (const attr of ATTRS) {
    const value = element.getAttribute(attr);
    if (value) {
      const next = translatedValue(value);
      if (next !== value) element.setAttribute(attr, next);
    }
  }
}

function translateSubtree(root: Node | null): void {
  if (!root) return;
  if (root.nodeType === Node.TEXT_NODE) {
    const parent = root.parentElement;
    if (!parent || parent.closest("[data-no-translate], pre, code, textarea")) return;
    const value = root.nodeValue ?? "";
    const next = translatedValue(value);
    if (next !== value) root.nodeValue = next;
    return;
  }
  if (!(root instanceof Element)) return;
  translateElement(root);
  if (root.closest("[data-no-translate]")) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    if (node.nodeType === Node.TEXT_NODE) {
      const parent = node.parentElement;
      if (parent && !parent.closest("[data-no-translate], pre, code, textarea")) {
        const value = node.nodeValue ?? "";
        const next = translatedValue(value);
        if (next !== value) node.nodeValue = next;
      }
    } else {
      translateElement(node as Element);
    }
    node = walker.nextNode();
  }
}

/**
 * Localize legacy interface literals while components are migrated to useT.
 * Only phrases present in D are touched, so user content and deep prose retain
 * the documented English fallback. The observer also covers dialogs mounted later.
 */
export function installDomTranslations(root: HTMLElement): () => void {
  observer?.disconnect();
  translateSubtree(root);
  observer = new MutationObserver((records) => {
    for (const record of records) {
      if (record.type === "attributes") translateSubtree(record.target);
      record.addedNodes.forEach(translateSubtree);
      if (record.type === "characterData") translateSubtree(record.target);
    }
  });
  observer.observe(root, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: [...ATTRS],
  });
  return () => {
    observer?.disconnect();
    observer = null;
  };
}
