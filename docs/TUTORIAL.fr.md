# Le tutoriel MimiWork

[English](TUTORIAL.md) · [中文](TUTORIAL.zh.md) · [Norsk](TUTORIAL.no.md) · **Français**

Dix minutes, du premier lancement à votre première automatisation. Tout fonctionne sur une installation neuve — aucune compétence de développeur requise.

L'habitude qui compte le plus : **demandez le résultat, pas les étapes.** Le travail de MimiWork est de vous remettre un fichier terminé. « Lis ces transcriptions d'entretiens et rédige une synthèse thématique en document Word » vous donne `summary.docx`. « Peux-tu m'aider à analyser des entretiens ? » vous donne une conversation.

---

## 0 · Installer (une seule fois)

Téléchargez depuis la [page Releases](https://github.com/lanceyuu/mimiwork/releases/latest) : le `.dmg` pour Mac (Apple Silicon ou Intel), le `-setup.exe` pour Windows. MimiWork n’est pas encore signé auprès d’Apple ni de Microsoft : au premier lancement, le système vous demande de vous porter garant — une seule fois.

- **Mac :** glissez MimiWork dans Applications et double-cliquez. Quand macOS dit qu’il ne peut pas vérifier l’app (ou qu’elle est « endommagée »), cliquez **Terminé**, ouvrez **Réglages Système ▸ Confidentialité et sécurité**, descendez jusqu’à *Sécurité* et cliquez **Ouvrir quand même**, puis rouvrez MimiWork et saisissez votre mot de passe. Pas de bouton ? Ouvrez le Terminal et lancez `xattr -cr /Applications/MimiWork.app`, puis ouvrez l’app normalement.
- **Windows :** si le navigateur retient le téléchargement, choisissez **Conserver ▸ Afficher plus ▸ Conserver quand même** (Edge) ou **Conserver** (Chrome). Lancez l’installateur ; sur l’écran bleu *Windows a protégé votre ordinateur*, cliquez **Informations complémentaires ▸ Exécuter quand même**. Sur un PC professionnel verrouillé : clic droit sur le fichier ▸ Propriétés ▸ cochez **Débloquer**.

Chaque étape, avec le libellé exact de chaque message, est dans la [section Install du README](../README.md#install). Les mises à jour s’installent depuis l’app et ne redemandent rien.

---

## 1 · Connecter un modèle (2 minutes)

Ouvrez **Settings ▸ Models** (Réglages ▸ Modèles). Deux chemins :

- **Connectez-vous avec QualiTaTi** — aucune clé ; les modèles Mimi consomment vos crédits existants. Une fois connecté, la carte affiche les trois niveaux — **Mimi Puppy** (gratuit chaque jour), **Mimi Hound** (rapide), **Mimi Wolf** (le plus capable) — chacun avec un bouton **Test** qui fait un vrai appel, pour vérifier que tout marche avant d'en avoir besoin. Deux réglages à faire au passage :
  - **Model region** (région des modèles) — *Default · US* (crédits moins chers) ou *Strict GDPR · Paris* (les données restent en Europe). S'applique dès le prochain message du compte, sur tous vos appareils.
  - La page **Activity** (barre latérale) montre le coût exact de chaque appel et le solde débité — les chiffres viennent du registre du serveur, pas d'une estimation locale.
- **Collez votre propre clé** — OpenAI, Anthropic, Gemini, Kimi, DeepSeek, Mistral et une dizaine d'autres, ou entièrement local via Ollama. Changez à tout moment depuis le sélecteur du composeur.

## 2 · Donnez-lui un dossier

Cliquez sur la carte de démarrage « dossier » (ou dites simplement « travaille dans mon dossier Projects/interviews »). **Rien en dehors des dossiers que vous accordez n'est lisible** — c'est tout le modèle de confidentialité, alors accordez le dossier où vivent les vrais fichiers. Cliquez sur le nom d'un dossier sous Access pour l'ouvrir dans le Finder ou l'Explorateur.

**Vous ne l'accordez qu'une fois.** Le dossier choisi pendant la configuration est mémorisé, et chaque nouvelle conversation démarre avec ce dossier déjà accordé — plus besoin de le ré-accorder depuis le panneau Access à chaque fois. Modifiez-le ou effacez-le dans Réglages ▸ Fichiers ▸ *Votre dossier*, où une case décide si Mimi peut y **enregistrer** (lecture-écriture) ou seulement lire. Laissez-le en lecture-écriture si vous voulez que les fichiers finis y atterrissent.

Les dossiers accordés au cours d'une conversation restent propres à cette conversation — un accès ponctuel reste ponctuel.

## 3 · La première vraie tâche

Une fois le dossier accordé, essayez (en remplaçant les noms de fichiers par les vôtres) :

> Lis les trois PDF de ce dossier et rédige une synthèse d'une page en `brief.docx` — les chiffres dans un tableau.

> Fais d'abord le profil de `wave2.sav` et dis-moi ce qu'il contient avant toute chose.

> Transforme `results.xlsx` en une présentation de 10 diapositives qui démontre qu'il faut corriger le mobile en priorité. Notes d'intervention pour mon co-présentateur.

Pendant que ça tourne :

- **Toute action à conséquences demande d'abord.** Envoi, écriture hors du dossier, commandes shell, récupération de données sur un serveur — une carte d'approbation apparaît, à chaque fois.
- **Vous pouvez corriger le cap sans arrêter.** Vous la voyez partir du mauvais côté ? Tapez simplement — « utilise la vague de décembre, pas novembre » — et l'instruction atterrit à la prochaine étape sûre. Le travail continue ; rien n'est perdu, rien ne redémarre.
- **Déposez des fichiers directement dans la conversation.** Un fichier d'un dossier accordé devient une `@mention` (travaillé sur place). Un fichier d'ailleurs est copié, visiblement, dans le dossier de la session — à côté de vos autres fichiers — puis ouvert avec le bon outil.
- Les fichiers terminés atterrissent **dans votre dossier** — jamais dans l'espace temporaire de la conversation, dès lors que vous avez accordé un dossier où Mimi peut écrire. Le panneau **Artifacts** liste ce que vous avez demandé — le rapport, le classeur, le graphique — et laisse de côté le script qui l'a produit. La page **Files** rassemble chaque livrable de chaque session.

## 4 · Trois touches à connaître

| Touche | Ce qu'elle fait |
|---|---|
| **`/`** | La palette de commandes : commandes de l'app (`/plan`, `/compact`, `/init`, `/model`…), vos commandes enregistrées, vos compétences |
| **`@`** | Pointer un fichier précis d'un dossier accordé — sans taper de chemin |
| **`⇧⇥`** | Faire défiler les modes : **Plan** (proposer d'abord, ne rien toucher) → **Ask for approval** (par défaut) → **Full access** |

Si vous connaissez Claude Code, Cowork ou Codex, ce sont les mêmes gestes — **Settings ▸ Transfer guide** en donne la correspondance complète.

**Le mode Plan mérite sa propre mention.** Pour tout ce qui a des enjeux — un livrable client, une grosse restructuration de vos données — passez d'abord en Plan avec `⇧⇥`. Mimi propose l'approche complète, vous approuvez ou corrigez, *puis* elle exécute. Une minute à lire un plan vaut mieux que vingt à refaire le travail.

## 5 · Apprenez-lui votre façon de faire — une fois

La différence entre un bon outil et un collègue : le collègue se souvient.

- **Instructions** (Settings ▸ Instructions, ou un `AGENTS.md` dans votre dossier — `CLAUDE.md` fonctionne aussi) : les règles permanentes. « Rapports en anglais britannique. Statistiques toujours avec tailles d'effet. Ne jamais toucher /raw. »
- **Skills** (Settings ▸ Skills) : du savoir-faire empaqueté. La carte de démarrage « Package your style guidelines in a skill » vous guide pour la première — couleurs, polices, règles maison — et ensuite chaque présentation et chaque document sortent conformes sans qu'on le demande. Parcourez **8 400 compétences communautaires**, et lisez les instructions réelles d'une compétence avant de l'installer. Vous avez déjà des compétences dans `~/.claude/skills` ? L'onglet Skills les trouve et les importe.
- **Memory** (Settings ▸ Memory) : ce que Mimi a remarqué et retenu. À consulter, modifier, supprimer.

## 6 · Connectez vos outils de travail

**Settings ▸ Connectors.** Slack (mentionnez Mimi dans un canal, le travail fini revient dans le fil), Gmail/Outlook, Google Agenda et Drive, GitHub, Jira, Notion, Canva, **Qualtrics** (lire le questionnaire pour que `Q4_1` devienne une vraie question, récupérer les réponses en CSV ou en SPSS `.sav` étiqueté — avec votre approbation à chaque téléchargement), et vos données de recherche QualiTaTi (projets, entretiens, questionnaires — chaque récupération demande d'abord). Tout le reste parle [MCP](https://modelcontextprotocol.io/).

## 7 · Faites-la travailler pendant que vous ne travaillez pas

Dites-le avec des mots ordinaires :

> Chaque lundi à 8 h, lis les nouveaux fichiers de `field-notes/` et dépose une synthèse hebdomadaire d'une page dans `reports/`.

Cela devient une **Automation** (barre latérale) — exécutée localement, transcription complète conservée, et tout ce qui exige une décision attend dans votre **Inbox** au lieu de deviner. Surveiller un canal Slack, rafraîchir une présentation hebdomadaire, relancer un jeu de données — même schéma.

## 8 · La petite Mimi flottante

Le petit chien sur votre bureau est un témoin d'état : il montre quand Mimi travaille, ou quand quelque chose vous attend. Glissez-le où vous voulez — il y reste. Cliquez sur l'icône pour ouvrir l'app — cela vaut pour « vu », donc une tâche terminée que vous avez déjà regardée ne sera plus annoncée en boucle. Cliquez sur une bulle pour fermer ce message-là seulement.

---

## Une bonne semaine avec MimiWork, en cinq demandes

1. « Travaille dans ce dossier. Fais le profil de chaque `.sav` et donne-moi un dictionnaire des données en Word. »
2. « Empaquette notre charte graphique dans une compétence » → chaque future présentation est conforme.
3. « Transforme les résultats de la vague 2 en 12 diapositives pour le comité de pilotage — défends la correction mobile, notes d'intervention incluses. » (en **mode Plan**)
4. « Récupère l'enquête de décembre depuis Qualtrics en SPSS et teste si la satisfaction varie selon le canal — tailles d'effet, pas seulement des p-valeurs. »
5. « Chaque vendredi à 16 h, résume la semaine de ce canal Slack dans une note dans `reports/`. »

D'ici vendredi : un dictionnaire des données, une présentation conforme, une vraie analyse et une automatisation permanente — chaque fichier sur votre disque, produit avec vos clés, sous votre approbation.
