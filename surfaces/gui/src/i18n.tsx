import { useSyncExternalStore } from "react";

// App languages (owner ask 2026-08-30, five more 2026-09-17): English, Chinese, Norwegian,
// French, Spanish, Japanese, Arabic, German, Portuguese.
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

export type Lang = "en" | "zh" | "no" | "fr" | "es" | "ja" | "ar" | "de" | "pt";
export const LANGS: { value: Lang; label: string }[] = [
  { value: "en", label: "English" },
  { value: "zh", label: "中文" },
  { value: "no", label: "Norsk" },
  { value: "fr", label: "Français" },
  { value: "es", label: "Español" },
  { value: "ja", label: "日本語" },
  { value: "ar", label: "العربية" },
  { value: "de", label: "Deutsch" },
  { value: "pt", label: "Português" },
];

// [zh, no, fr, es, ja, ar, de, pt] — en is the key itself.
const D: Record<string, string[]> = {
  "Mimi style": ["Mimi 外观", "Mimi-utseende", "Apparence de Mimi", "Estilo Mimi", "Mimiスタイル", "نمط Mimi", "Mimi-Stil", "Estilo Mimi"],
  "Classic Mimi": ["经典 Mimi", "Klassisk Mimi", "Mimi classique", "Mimi clásico", "クラシックMimi", "Mimi الكلاسيكي", "Klassisches Mimi", "Mimi clássico"],
  "Teal Mimi": ["青绿 Mimi", "Turkis Mimi", "Mimi turquoise", "Mimi verde azulado", "ティールMimi", "Mimi تركوازي", "Blaugrün Mimi", "Mimi verde-azulado"],
  "Choose the look of your floating desktop companion.": ["选择桌面悬浮伙伴的外观。", "Velg utseendet til den flytende skrivebordsvennen din.", "Choisissez l’apparence de votre compagnon flottant.", "Elige el aspecto de tu compañero flotante de escritorio.", "デスクトップのフローティングコンパニオンの外観を選択してください。", "اختر مظهر رفيق سطح المكتب العائم الخاص بك.", "Wähle das Aussehen deines schwebenden Desktop-Begleiters.", "Escolha a aparência do seu companheiro flutuante de desktop."],
  "Show Mimi when the app is minimized, with a signal when work finishes or needs your attention.": ["应用最小化时显示 Mimi，并在工作完成或需要你处理时提醒。", "Vis Mimi når appen er minimert, med et signal når arbeidet er ferdig eller trenger din oppmerksomhet.", "Affichez Mimi lorsque l’application est réduite, avec un signal lorsque le travail est terminé ou demande votre attention.", "Mostrar a Mimi cuando la aplicación esté minimizada, con una señal cuando el trabajo termine o necesite tu atención.", "アプリが最小化されているときにMimiを表示し、作業が完了したときや注意が必要なときに信号を送ります。", "أظهر Mimi عندما يكون التطبيق مصغرًا، مع إشارة عند انتهاء العمل أو الحاجة إلى انتباهك.", "Zeige Mimi, wenn die App minimiert ist, mit einem Signal, wenn die Arbeit abgeschlossen ist oder deine Aufmerksamkeit benötigt.", "Mostrar Mimi quando o aplicativo estiver minimizado, com um sinal quando o trabalho terminar ou precisar da sua atenção."],
  "Stop task": ["停止任务", "Stopp oppgaven", "Arrêter la tâche", "Detener tarea", "タスクを停止", "إيقاف المهمة", "Aufgabe stoppen", "Parar tarefa"],
  "Force stop": ["强制停止", "Tving stopp", "Forcer l’arrêt", "Forzar detención", "強制停止", "إيقاف قسري", "Erzwingen", "Forçar parada"],
  "Stopping…": ["正在停止…", "Stopper…", "Arrêt en cours…", "Deteniendo…", "停止中…", "جارٍ الإيقاف…", "Wird gestoppt…", "Parando…"],
  "Steer": ["调整方向", "Endre retning", "Réorienter", "Dirigir", "操縦", "توجيه", "Steuern", "Direcionar"],
  "Stop the current task (Esc)": ["停止当前任务（Esc）", "Stopp den gjeldende oppgaven (Esc)", "Arrêter la tâche en cours (Échap)", "Detener la tarea actual (Esc)", "現在のタスクを停止（Esc）", "إيقاف المهمة الحالية (Esc)", "Aktuelle Aufgabe stoppen (Esc)", "Parar a tarefa atual (Esc)"],
  "Waiting for the model…": ["正在等待模型…", "Venter på modellen…", "En attente du modèle…", "Esperando al modelo…", "モデルを待っています…", "في انتظار النموذج…", "Warten auf das Modell…", "Aguardando o modelo…"],
  "Writing a response…": ["正在撰写回复…", "Skriver et svar…", "Rédaction de la réponse…", "Escribiendo una respuesta…", "応答を書いています…", "جارٍ كتابة الرد…", "Antwort wird geschrieben…", "Escrevendo uma resposta…"],
  "Running a step…": ["正在执行步骤…", "Utfører et trinn…", "Exécution d’une étape…", "Ejecutando un paso…", "ステップを実行中…", "جارٍ تنفيذ خطوة…", "Schritt wird ausgeführt…", "Executando uma etapa…"],
  "Waiting for your response…": ["正在等待你的回复…", "Venter på svaret ditt…", "En attente de votre réponse…", "Esperando tu respuesta…", "あなたの応答を待っています…", "في انتظار ردك…", "Warten auf deine Antwort…", "Aguardando sua resposta…"],
  "Summarizing earlier messages…": ["正在总结之前的消息…", "Oppsummerer tidligere meldinger…", "Résumé des messages précédents…", "Resumiendo mensajes anteriores…", "以前のメッセージを要約しています…", "جارٍ تلخيص الرسائل السابقة…", "Frühere Nachrichten werden zusammengefasst…", "Resumindo mensagens anteriores…"],
  "Updating the task with your message…": ["正在根据你的消息调整任务…", "Oppdaterer oppgaven med meldingen din…", "Mise à jour de la tâche avec votre message…", "Actualizando la tarea con tu mensaje…", "あなたのメッセージでタスクを更新しています…", "جارٍ تحديث المهمة برسالتك…", "Aufgabe wird mit deiner Nachricht aktualisiert…", "Atualizando a tarefa com sua mensagem…"],
  "Stopping the current task…": ["正在停止当前任务…", "Stopper den gjeldende oppgaven…", "Arrêt de la tâche en cours…", "Deteniendo la tarea actual…", "現在のタスクを停止しています…", "جارٍ إيقاف المهمة الحالية…", "Aktuelle Aufgabe wird gestoppt…", "Parando a tarefa atual…"],
  "Connection lost. Reconnecting…": ["连接已断开，正在重连…", "Tilkoblingen er brutt. Kobler til igjen…", "Connexion perdue. Reconnexion…", "Conexión perdida. Reconectando…", "接続が切れました。再接続中…", "انقطع الاتصال. جارٍ إعادة الاتصال…", "Verbindung verloren. Wird neu verbunden…", "Conexão perdida. Reconectando…"],
  "Connection active. No new output for": ["连接正常。没有新输出的时间：", "Tilkoblingen er aktiv. Ingen nye resultater på", "Connexion active. Aucune nouvelle sortie depuis", "Conexión activa. Sin nueva salida durante", "接続アクティブ。新しい出力はありません", "الاتصال نشط. لا يوجد مخرجات جديدة لمدة", "Verbindung aktiv. Keine neue Ausgabe für", "Conexão ativa. Sem nova saída por"],
  "The task may still be running. You can still try Stop task.": ["任务可能仍在运行。你仍可以尝试停止任务。", "Oppgaven kan fortsatt kjøre. Du kan fortsatt prøve å stoppe den.", "La tâche peut encore être en cours. Vous pouvez toujours essayer de l’arrêter.", "La tarea puede seguir en ejecución. Aún puedes intentar detenerla.", "タスクはまだ実行中かもしれません。それでもタスクの停止を試みることができます。", "قد تكون المهمة لا تزال قيد التشغيل. يمكنك محاولة إيقاف المهمة.", "Die Aufgabe läuft möglicherweise noch. Du kannst trotzdem versuchen, sie zu stoppen.", "A tarefa ainda pode estar em execução. Você ainda pode tentar parar a tarefa."],
  "Mimi Wolf uses account credits.": ["Mimi Wolf 使用账户积分。", "Mimi Wolf bruker kontokreditter.", "Mimi Wolf utilise les crédits du compte.", "Mimi Wolf usa créditos de la cuenta.", "Mimi Wolfはアカウントのクレジットを使用します。", "يستخدم Mimi Wolf رصيد الحساب.", "Mimi Wolf verwendet Kontoguthaben.", "Mimi Wolf usa créditos da conta."],
  "shared with Mimi Hound": ["与 Mimi Hound 共用", "delt med Mimi Hound", "partagée avec Mimi Hound", "compartido con Mimi Hound", "Mimi Houndと共有", "مشارك مع Mimi Hound", "Mit Mimi Hound geteilt", "compartilhado com Mimi Hound"],
  "shared with Mimi Puppy": ["与 Mimi Puppy 共用", "delt med Mimi Puppy", "partagée avec Mimi Puppy", "compartido con Mimi Puppy", "Mimi Puppyと共有", "مشارك مع Mimi Puppy", "Mit Mimi Puppy geteilt", "compartilhado com Mimi Puppy"],
  "What should we produce?": ["我们要制作什么？", "Hva skal vi lage?", "Que voulez-vous créer ?", "¿Qué deberíamos producir?", "何を生成しますか？", "ماذا يجب أن ننتج؟", "Was sollen wir erstellen?", "O que devemos produzir?"],
  "Choose a result, then attach your files or share a folder. You can edit the request before sending.": ["选择成果类型，再添加文件或共享文件夹。发送前可以修改请求。", "Velg et resultat, legg ved filer eller del en mappe. Du kan redigere forespørselen før du sender.", "Choisissez un résultat, puis joignez vos fichiers ou partagez un dossier. Vous pouvez modifier la demande avant de l’envoyer.", "Elige un resultado y luego adjunta tus archivos o comparte una carpeta. Puedes editar la solicitud antes de enviarla.", "結果を選択し、ファイルを添付するかフォルダを共有してください。送信前にリクエストを編集できます。", "اختر نتيجة، ثم أرفق ملفاتك أو شارك مجلدًا. يمكنك تعديل الطلب قبل الإرسال.", "Wähle ein Ergebnis und füge dann deine Dateien hinzu oder teile einen Ordner. Du kannst die Anfrage vor dem Senden bearbeiten.", "Escolha um resultado e anexe seus arquivos ou compartilhe uma pasta. Você pode editar a solicitação antes de enviar."],
  "Start with a file": ["从文件开始", "Start med en fil", "Commencer avec un fichier", "Comenzar con un archivo", "ファイルから始める", "ابدأ بملف", "Mit einer Datei beginnen", "Começar com um arquivo"],
  "Summarize into Word": ["汇总成 Word 文档", "Oppsummer i Word", "Résumer dans Word", "Resumir en Word", "Wordに要約", "تلخيص في Word", "In Word zusammenfassen", "Resumir em Word"],
  "Turn interviews or notes into a clear, editable report": ["将访谈或笔记整理为清晰、可编辑的报告", "Gjør intervjuer eller notater til en tydelig, redigerbar rapport", "Transformer des entretiens ou des notes en rapport clair et modifiable", "Convierte entrevistas o notas en un informe claro y editable", "インタビューやメモを明確で編集可能なレポートに変換", "حوّل المقابلات أو الملاحظات إلى تقرير واضح وقابل للتحرير", "Verwandle Interviews oder Notizen in einen klaren, bearbeitbaren Bericht", "Transforme entrevistas ou notas em um relatório claro e editável"],
  "Clean a spreadsheet": ["清理电子表格", "Rydd et regneark", "Nettoyer un tableur", "Limpiar una hoja de cálculo", "スプレッドシートを整理", "نظّف جدول بيانات", "Eine Tabelle bereinigen", "Limpar uma planilha"],
  "Get an organized workbook with a record of changes": ["生成整理后的工作簿并记录修改", "Få en ryddig arbeidsbok med endringslogg", "Obtenir un classeur organisé avec un historique des modifications", "Obtén un libro de trabajo organizado con un registro de cambios", "変更の記録付きの整理されたワークブックを取得", "احصل على مصنف منظم مع سجل بالتغييرات", "Erhalte eine organisierte Arbeitsmappe mit einem Änderungsprotokoll", "Obtenha uma pasta de trabalho organizada com um registro de alterações"],
  "Turn notes into slides": ["将笔记制作成幻灯片", "Gjør notater til lysbilder", "Transformer des notes en diapositives", "Convertir notas en diapositivas", "メモをスライドに変換", "حوّل الملاحظات إلى شرائح", "Notizen in Folien verwandeln", "Transformar notas em slides"],
  "Build an editable presentation with a clear story": ["制作条理清晰、可编辑的演示文稿", "Lag en redigerbar presentasjon med en tydelig fortelling", "Créer une présentation modifiable au récit clair", "Crea una presentación editable con una historia clara", "明確なストーリーを持つ編集可能なプレゼンテーションを作成", "أنشئ عرضًا تقديميًا قابلًا للتحرير بقصة واضحة", "Erstelle eine bearbeitbare Präsentation mit einer klaren Geschichte", "Crie uma apresentação editável com uma história clara"],
  "More ways to start": ["更多开始方式", "Flere måter å starte på", "Autres façons de commencer", "Más formas de comenzar", "その他の開始方法", "طرق بدء أخرى", "Weitere Startmöglichkeiten", "Mais maneiras de começar"],
  "Your files are saved. Open one to review it, or ask for changes.": ["文件已保存。打开查看，或提出修改要求。", "Filene dine er lagret. Åpne en for å se gjennom den, eller be om endringer.", "Vos fichiers sont enregistrés. Ouvrez-en un pour le vérifier ou demandez des modifications.", "Tus archivos están guardados. Abre uno para revisarlo o pide cambios.", "ファイルは保存されています。レビューするにはファイルを開くか、変更を依頼してください。", "تم حفظ ملفاتك. افتح أحدها لمراجعته أو اطلب تغييرات.", "Deine Dateien sind gespeichert. Öffne eine zur Überprüfung oder bitte um Änderungen.", "Seus arquivos estão salvos. Abra um para revisá-lo ou peça alterações."],
  "Revise": ["修改", "Revider", "Réviser", "Revisar", "改訂", "مراجعة", "Überarbeiten", "Revisar"],
  "Visualize this task": ["可视化这个任务", "Visualiser denne oppgaven", "Visualiser cette tâche", "Visualizar esta tarea", "このタスクを視覚化", "تصور هذه المهمة", "Diese Aufgabe visualisieren", "Visualizar esta tarefa"],
  "One task can use several requests.": ["一个任务可能使用多次请求。", "Én oppgave kan bruke flere forespørsler.", "Une tâche peut utiliser plusieurs requêtes.", "Una tarea puede usar varias solicitudes.", "1つのタスクで複数のリクエストを使用できます。", "يمكن أن تستخدم المهمة الواحدة عدة طلبات.", "Eine Aufgabe kann mehrere Anfragen verwenden.", "Uma tarefa pode usar várias solicitações."],
  "Account credits": ["账户积分", "Kontokreditter", "Crédits du compte", "Créditos de la cuenta", "アカウントのクレジット", "رصيد الحساب", "Kontoguthaben", "Créditos da conta"],
  "Example and requirements": ["示例与要求", "Eksempel og krav", "Exemple et prérequis", "Ejemplo y requisitos", "例と要件", "مثال ومتطلبات", "Beispiel und Anforderungen", "Exemplo e requisitos"],
  "Expected output": ["预期成果", "Forventet resultat", "Résultat attendu", "Salida esperada", "期待される出力", "المخرجات المتوقعة", "Erwartete Ausgabe", "Saída esperada"],
  "What you need": ["所需材料与工具", "Dette trenger du", "Ce qu’il vous faut", "Lo que necesitas", "必要なもの", "ما تحتاجه", "Was du brauchst", "O que você precisa"],
  "Installation checked": ["安装已验证", "Installasjon kontrollert", "Installation vérifiée", "Instalación comprobada", "インストール確認済み", "تم التحقق من التثبيت", "Installation geprüft", "Instalação verificada"],

  "Could not load skills. Try again.": ["无法加载技能，请重试。", "Kunne ikke laste ferdigheter. Prøv igjen.", "Impossible de charger les compétences. Réessayez.", "No se pudieron cargar las habilidades. Inténtalo de nuevo.", "スキルを読み込めませんでした。もう一度お試しください。", "تعذر تحميل المهارات. حاول مرة أخرى.", "Fähigkeiten konnten nicht geladen werden. Versuche es erneut.", "Não foi possível carregar as habilidades. Tente novamente."],
  "daily limit": ["每日额度", "daglig grense", "limite quotidienne", "límite diario", "1日の制限", "الحد اليومي", "Tageslimit", "limite diário"],
  "Search the skill store": ["搜索技能商店", "Søk i ferdighetsbutikken", "Rechercher dans la boutique de compétences", "Buscar en la tienda de habilidades", "スキルストアを検索", "البحث في متجر المهارات", "Fähigkeiten-Store durchsuchen", "Pesquisar na loja de habilidades"],
  "Clear search": ["清除搜索", "Tøm søket", "Effacer la recherche", "Borrar búsqueda", "検索をクリア", "مسح البحث", "Suche löschen", "Limpar pesquisa"],
  // ── EDGE (ch. 9) and the Five A's (ch. 7) ──
  "Where the value lands": ["价值落在哪里", "Hvor verdien lander", "Où atterrit la valeur", "Dónde aterriza el valor", "価値が届く場所", "أين تتحقق القيمة", "Wo der Wert ankommt", "Onde o valor chega"],
  "What makes them possible": ["是什么让它们成为可能", "Hva som gjør dem mulig", "Ce qui les rend possibles", "Qué los hace posibles", "それらを可能にするもの", "ما الذي يجعلها ممكنة", "Was sie ermöglicht", "O que os torna possíveis"],
  "Doing what you already do, faster and at greater scale": ["把本来就在做的事做得更快、规模更大", "Gjøre det du allerede gjør, raskere og i større skala", "Faire ce que vous faites déjà, plus vite et à plus grande échelle", "Hacer lo que ya haces, más rápido y a mayor escala", "すでに行っていることを、より速く、より大規模に行う", "القيام بما تفعله بالفعل، بشكل أسرع وعلى نطاق أوسع", "Das tun, was du bereits tust, schneller und in größerem Umfang", "Fazer o que você já faz, mais rápido e em maior escala"],
  "Insight synthesised from complex material, so you can choose": ["从复杂材料中综合出洞见,帮你做选择", "Innsikt syntetisert fra komplekst materiale, så du kan velge", "Une synthèse tirée de matériaux complexes, pour choisir", "Información sintetizada de material complejo, para que puedas elegir", "複雑な資料から統合された洞察で、選択できるように", "رؤية مستخلصة من مواد معقدة، لتتمكن من الاختيار", "Erkenntnisse aus komplexem Material synthetisiert, damit du wählen kannst", "Insight sintetizado a partir de material complexo, para que você possa escolher"],
  "Work that is new and different — the first time you try something": ["新产品与新收入——工具内部很难看见", "Nye tilbud og inntekter — sjelden synlig inne i et verktøy", "Un travail nouveau et différent — la première fois que vous essayez quelque chose", "Trabajo nuevo y diferente: la primera vez que intentas algo", "新しくて異なる仕事—何かを初めて試すとき", "عمل جديد ومختلف — أول مرة تجرب فيها شيئًا", "Arbeit, die neu und anders ist – beim ersten Mal, wenn du etwas ausprobierst", "Trabalho novo e diferente — a primeira vez que você tenta algo"],
  "What you learned, and what you made permanent": ["你学到的东西,以及你把它固定下来的部分", "Det du lærte, og det du gjorde varig", "Ce que vous avez appris, et ce que vous avez rendu permanent", "Lo que aprendiste y lo que hiciste permanente", "学んだこと、そして永続的にしたこと", "ما تعلمته، وما جعلته دائمًا", "Was du gelernt hast und was du dauerhaft gemacht hast", "O que você aprendeu e o que tornou permanente"],
  "Growth is empty so far — it fills when you reach for something you have not used before, so it grows by trying a new kind of work rather than by doing more of the same.": ["Growth 目前是空的——当你去用以前没用过的东西时它才会涨。所以它靠尝试新的工作方式增长,而不是靠把同一件事做更多遍。", "Vekst er tom foreløpig — den fylles når du tar i bruk noe du ikke har brukt før, så den vokser ved å prøve en ny type arbeid, ikke ved å gjøre mer av det samme.", "La Croissance est encore vide — elle se remplit lorsque vous utilisez quelque chose que vous n'aviez jamais utilisé, elle croît donc en essayant un nouveau type de travail, pas en refaisant la même chose.", "El crecimiento está vacío por ahora: se llena cuando alcanzas algo que no has usado antes, así que crece al probar un nuevo tipo de trabajo en lugar de hacer más de lo mismo.", "成長はまだ空です—まだ使ったことのないものに手を伸ばすと埋まります。同じことをもっと行うのではなく、新しい種類の仕事を試すことで成長します。", "النمو فارغ حتى الآن — يمتلئ عندما تصل إلى شيء لم تستخدمه من قبل، لذا ينمو بتجربة نوع جديد من العمل بدلاً من القيام بالمزيد من نفس الشيء.", "Wachstum ist bisher leer – es füllt sich, wenn du nach etwas greifst, das du noch nicht verwendet hast. Es wächst also durch das Ausprobieren einer neuen Art von Arbeit, nicht durch mehr vom Gleichen.", "O crescimento está vazio até agora — ele se preenche quando você alcança algo que não usou antes, então cresce ao tentar um novo tipo de trabalho, em vez de fazer mais do mesmo."],
  "How you work with Mimi": ["你与 Mimi 的协作方式", "Slik jobber du med Mimi", "Votre façon de travailler avec Mimi", "Cómo trabajas con Mimi", "Mimiとの働き方", "كيف تعمل مع Mimi", "Wie du mit Mimi arbeitest", "Como você trabalha com a Mimi"],
  "Your turns placed on the Five A's continuum — by what they did, not what they were called.": ["把你的每一轮放在 Five A's 连续谱上——按它实际做了什么,而不是叫什么。", "Rundene dine plassert på Five A's-kontinuumet — etter hva de gjorde, ikke hva de het.", "Vos tours placés sur le continuum des Five A's — selon ce qu'ils ont fait, non leur nom.", "Tus turnos colocados en el continuo de las Cinco A: por lo que hicieron, no por cómo se llamaron.", "あなたのターンは、5つのAの連続体上に配置されます—呼び名ではなく、行ったことによって。", "دوراتك موضوعة على سلسلة الخمسة A — بناءً على ما فعلته، وليس ما سميت به.", "Deine Züge auf dem Kontinuum der fünf A – nach dem, was sie taten, nicht wie sie genannt wurden.", "Suas jogadas colocadas no continuum dos Cinco A — pelo que fizeram, não pelo que foram chamadas."],
  "The model on its own, answering you directly": ["只有模型本身,直接回答你", "Modellen alene, som svarer deg direkte", "Le modèle seul, qui vous répond directement", "El modelo por sí solo, respondiéndote directamente", "モデル単独で、直接回答", "النموذج بمفرده، يرد عليك مباشرة", "Das Modell allein, das dir direkt antwortet", "O modelo sozinho, respondendo diretamente a você"],
  "Grounded in your own documents, notes and knowledge base": ["基于你自己的文档、笔记和知识库", "Forankret i dine egne dokumenter, notater og kunnskapsbase", "Ancré dans vos propres documents, notes et base de connaissances", "Basado en tus propios documentos, notas y base de conocimiento", "自分のドキュメント、ノート、ナレッジベースに基づく", "مستند إلى مستنداتك وملاحظاتك وقاعدة معرفتك الخاصة", "Basiert auf deinen eigenen Dokumenten, Notizen und Wissensdatenbank", "Baseado nos seus próprios documentos, notas e base de conhecimento"],
  "One fixed recipe, one defined job — a skill or a command": ["一份固定配方、一个明确任务——一个技能或一条命令", "Én fast oppskrift, én definert jobb — en ferdighet eller en kommando", "Une recette fixe, une tâche définie — une compétence ou une commande", "Una receta fija, un trabajo definido: una habilidad o un comando", "固定されたレシピ、定義された仕事—スキルまたはコマンド", "وصفة ثابتة، وظيفة محددة — مهارة أو أمر", "Ein festes Rezept, eine definierte Aufgabe – eine Fähigkeit oder ein Befehl", "Uma receita fixa, um trabalho definido — uma habilidade ou um comando"],
  "A schedule started it and it followed the path it was given": ["由计划触发,并按既定路径执行", "En plan startet den, og den fulgte veien den fikk", "Un calendrier l'a lancé et il a suivi le chemin donné", "Un horario lo inició y siguió el camino que se le dio", "スケジュールが開始し、与えられた経路をたどった", "جدول زمني بدأه واتبع المسار المعطى له", "Ein Zeitplan hat es gestartet und es folgte dem vorgegebenen Weg", "Uma agenda o iniciou e ele seguiu o caminho que lhe foi dado"],
  "It chose its own next step, or reached across your systems": ["它自己决定下一步,或跨系统动了手", "Den valgte sitt eget neste steg, eller grep inn på tvers av systemene dine", "Il a choisi son étape suivante, ou est intervenu à travers vos systèmes", "Eligió su propio siguiente paso o se conectó con tus sistemas", "自分で次のステップを選んだか、システムを横断した", "اختار خطوته التالية بنفسه، أو تواصل مع أنظمتك", "Es wählte seinen eigenen nächsten Schritt oder griff auf deine Systeme zu", "Ele escolheu seu próprio próximo passo ou alcançou seus sistemas"],
  "more human involvement": ["人的参与更多", "mer menneskelig involvering", "plus d'intervention humaine", "más participación humana", "より人間の関与", "مشاركة بشرية أكبر", "mehr menschliche Beteiligung", "mais envolvimento humano"],
  "more autonomy": ["自主性更高", "mer autonomi", "plus d'autonomie", "más autonomía", "より自律性", "استقلالية أكبر", "mehr Autonomie", "mais autonomia"],
  "Mostly": ["主要是", "Mest", "Surtout", "Mayormente", "ほとんど", "في الغالب", "Meistens", "Principalmente"],
  "More": ["更多", "Mer", "Plus", "Más", "もっと", "أكثر", "Mehr", "Mais"],
  // ── "is this still alive?" card ──
  "Maintained and current": ["持续维护,保持最新", "Vedlikeholdt og oppdatert", "Maintenu et à jour", "Mantenido y actualizado", "維持され、最新", "مُحافظ عليه ومُحدَّث", "Gepflegt und aktuell", "Mantido e atualizado"],
  "Latest release": ["最新版本", "Siste versjon", "Dernière version", "Última versión", "最新リリース", "أحدث إصدار", "Neueste Version", "Última versão"],
  "Before that": ["此前", "Før det", "Avant cela", "Antes de eso", "それ以前", "قبل ذلك", "Davor", "Antes disso"],
  "models from": ["个模型,来自", "modeller fra", "modèles de", "modelos de", "モデル（提供元）", "نماذج من", "Modelle von", "modelos de"],
  "providers": ["家服务商", "leverandører", "fournisseurs", "proveedores", "プロバイダー", "مزودون", "Anbieter", "fornecedores"],
  "the lineup is refreshed with every release": ["每次发版都会更新阵容", "utvalget oppdateres med hver utgivelse", "la sélection est actualisée à chaque version", "la alineación se actualiza con cada versión", "ラインナップはリリースごとに更新されます", "يتم تحديث التشكيلة مع كل إصدار", "Die Aufstellung wird mit jeder Version aktualisiert", "a linha é atualizada a cada versão"],
  "Signed in with QualiTaTi? The model behind each Mimi tier is upgraded for you — nothing to install, nothing to choose.": ["用 QualiTaTi 登录了?每个 Mimi 档位背后的模型会自动升级——无需安装,无需选择。", "Logget inn med QualiTaTi? Modellen bak hvert Mimi-nivå oppgraderes for deg — ingenting å installere, ingenting å velge.", "Connecté avec QualiTaTi ? Le modèle derrière chaque niveau Mimi est mis à niveau pour vous — rien à installer, rien à choisir.", "¿Has iniciado sesión con QualiTaTi? El modelo detrás de cada nivel de Mimi se actualiza para ti: nada que instalar, nada que elegir.", "QualiTaTiでサインインしていますか？各Mimiティアの背後にあるモデルは自動的にアップグレードされます—インストールも選択も不要です。", "هل سجلت الدخول باستخدام QualiTaTi؟ النموذج وراء كل مستوى من مستويات Mimi يتم ترقيته لك — لا شيء لتثبيته، لا شيء لاختياره.", "Mit QualiTaTi angemeldet? Das Modell hinter jeder Mimi-Stufe wird für dich aktualisiert – nichts zu installieren, nichts zu wählen.", "Conectado com QualiTaTi? O modelo por trás de cada nível da Mimi é atualizado para você — nada para instalar, nada para escolher."],
  "Built and maintained by": ["开发与维护者", "Laget og vedlikeholdt av", "Conçu et maintenu par", "Construido y mantenido por", "構築・保守", "تم بناؤه وصيانته بواسطة", "Erstellt und gepflegt von", "Construído e mantido por"],
  "Source and releases": ["源码与版本", "Kildekode og utgivelser", "Code source et versions", "Fuente y versiones", "ソースとリリース", "المصدر والإصدارات", "Quelle und Versionen", "Fonte e versões"],
  "Tutorial": ["教程", "Veiledning", "Tutoriel", "Tutorial", "チュートリアル", "برنامج تعليمي", "Tutorial", "Tutorial"],
  "Everything above is checkable — the release dates come from the public repository.": ["以上内容都可核查——发版日期来自公开代码仓库。", "Alt over kan etterprøves — utgivelsesdatoene kommer fra det offentlige kodelageret.", "Tout ceci est vérifiable — les dates de version proviennent du dépôt public.", "Todo lo anterior es verificable: las fechas de lanzamiento provienen del repositorio público.", "上記はすべて確認可能です—リリース日は公開リポジトリから取得されます。", "كل ما سبق قابل للتحقق — تواريخ الإصدار تأتي من المستودع العام.", "Alles oben Genannte ist überprüfbar – die Veröffentlichungsdaten stammen aus dem öffentlichen Repository.", "Tudo acima é verificável — as datas de lançamento vêm do repositório público."],
  "today": ["今天", "i dag", "aujourd'hui", "hoy", "今日", "اليوم", "heute", "hoje"],
  "yesterday": ["昨天", "i går", "hier", "ayer", "昨日", "أمس", "gestern", "ontem"],
  "days ago": ["天前", "dager siden", "jours", "hace días", "日前", "أيام مضت", "vor Tagen", "dias atrás"],
  "last month": ["上个月", "forrige måned", "le mois dernier", "el mes pasado", "先月", "الشهر الماضي", "letzten Monat", "mês passado"],
  "months ago": ["个月前", "måneder siden", "mois", "hace meses", "か月前", "أشهر مضت", "vor Monaten", "meses atrás"],
  // ── EDGE profile (Efficiency · Decisions · Growth · Empowerment) ──
  "How Mimi helps you": ["Mimi 如何帮到你", "Slik hjelper Mimi deg", "Comment Mimi vous aide", "Cómo te ayuda Mimi", "Mimiがどのように役立つか", "كيف يساعدك Mimi", "Wie Mimi dir hilft", "Como a Mimi ajuda você"],
  "The same hours, grouped by the kind of help — the EDGE framework.": ["同样的时长,按帮助类型分组——EDGE 框架。", "De samme timene, gruppert etter typen hjelp — EDGE-rammeverket.", "Les mêmes heures, regroupées par type d'aide — le cadre EDGE.", "Las mismas horas, agrupadas por el tipo de ayuda: el marco EDGE.", "同じ時間を、支援の種類ごとにグループ化したもの — EDGEフレームワーク。", "نفس الساعات، مجمعة حسب نوع المساعدة — إطار EDGE.", "Dieselben Stunden, gruppiert nach Art der Hilfe – das EDGE-Framework.", "As mesmas horas, agrupadas pelo tipo de ajuda — a estrutura EDGE."],
  "Efficiency": ["效率", "Effektivitet", "Efficacité", "Eficiencia", "効率性", "الكفاءة", "Effizienz", "Eficiência"],
  "Decisions": ["决策", "Beslutninger", "Décisions", "Decisiones", "意思決定", "القرارات", "Entscheidungen", "Decisões"],
  "Growth": ["增长", "Vekst", "Croissance", "Crecimiento", "成長", "النمو", "Wachstum", "Crescimento"],
  "Empowerment": ["赋能", "Myndiggjøring", "Autonomie", "Empoderamiento", "エンパワーメント", "التمكين", "Befähigung", "Empoderamento"],
  "Work that had to happen anyway, done faster": ["本来就要做的工作,做得更快", "Arbeid som måtte gjøres uansett, gjort raskere", "Le travail à faire de toute façon, fait plus vite", "Trabajo que tenía que hacerse de todos modos, hecho más rápido", "どうしても発生する作業を、より速く完了", "عمل كان يجب أن يحدث على أي حال، تم إنجازه بشكل أسرع", "Arbeit, die sowieso anfiel, schneller erledigt", "Trabalho que tinha que acontecer de qualquer forma, feito mais rápido"],
  "Evidence gathered and analysed so you can choose": ["收集并分析证据,帮你做选择", "Grunnlag samlet og analysert så du kan velge", "Des données réunies et analysées pour choisir", "Evidencia recopilada y analizada para que puedas elegir", "選択できるように収集・分析された証拠", "أدلة تم جمعها وتحليلها لتتمكن من الاختيار", "Belege gesammelt und analysiert, damit du wählen kannst", "Evidências coletadas e analisadas para você escolher"],
  "Work aimed outward — decks, messages, delivery": ["面向外部的工作——演示、消息、交付", "Arbeid rettet utover — presentasjoner, meldinger, leveranser", "Le travail tourné vers l'extérieur — présentations, messages, livraisons", "Trabajo orientado hacia afuera: presentaciones, mensajes, entrega", "外部に向けた作業 — デッキ、メッセージ、納品", "عمل موجه للخارج — عروض تقديمية، رسائل، تسليم", "Nach außen gerichtete Arbeit – Präsentationen, Nachrichten, Lieferung", "Trabalho voltado para fora — apresentações, mensagens, entrega"],
  "Capability that outlasts the session": ["比这次会话更持久的能力", "Kapasitet som varer lenger enn økten", "Des capacités qui survivent à la session", "Capacidad que perdura más allá de la sesión", "セッションを超えて持続する能力", "قدرة تدوم بعد الجلسة", "Fähigkeit, die über die Sitzung hinaus Bestand hat", "Capacidade que dura além da sessão"],
  // ── sidebar ──
  "Inbox": ["收件箱", "Innboks", "Boîte de réception", "Bandeja de entrada", "受信トレイ", "البريد الوارد", "Posteingang", "Caixa de entrada"],
  "Settings": ["设置", "Innstillinger", "Réglages", "Configuración", "設定", "الإعدادات", "Einstellungen", "Configurações"],
  "Connectors": ["连接器", "Koblinger", "Connecteurs", "Conectores", "コネクタ", "الموصلات", "Konnektoren", "Conectores"],
  "Automations": ["自动化", "Automatiseringer", "Automatisations", "Automatizaciones", "自動化", "الأتمتة", "Automatisierungen", "Automações"],
  "Activity": ["活动", "Aktivitet", "Activité", "Actividad", "アクティビティ", "النشاط", "Aktivität", "Atividade"],
  "Files": ["文件", "Filer", "Fichiers", "Archivos", "ファイル", "الملفات", "Dateien", "Arquivos"],
  "saved so far": ["累计节省", "spart så langt", "gagnées jusqu'ici", "guardados hasta ahora", "これまでの保存", "تم الحفظ حتى الآن", "bisher gespeichert", "salvos até agora"],
  "Projects": ["项目", "Prosjekter", "Projets", "Proyectos", "プロジェクト", "المشاريع", "Projekte", "Projetos"],
  "Sign out of QualiTaTi": ["退出 QualiTaTi", "Logg ut av QualiTaTi", "Se déconnecter de QualiTaTi", "Cerrar sesión de QualiTaTi", "QualiTaTiからサインアウト", "تسجيل الخروج من QualiTaTi", "Bei QualiTaTi abmelden", "Sair do QualiTaTi"],
  // ── permission modes ──
  "Plan": ["规划", "Plan", "Plan", "Plan", "プラン", "خطة", "Plan", "Plano"],
  "Accept edits": ["自动接受编辑", "Godta redigeringer", "Accepter les modifications", "Aceptar ediciones", "編集を承認", "قبول التعديلات", "Bearbeitungen übernehmen", "Aceitar edições"],
  "Bypass permissions": ["跳过审批", "Hopp over godkjenning", "Ignorer les autorisations", "Omitir permisos", "権限をバイパス", "تجاوز الأذونات", "Berechtigungen umgehen", "Ignorar permissões"],
  "Explore and propose a plan — nothing runs until you approve": ["先探索并提出方案——你批准之前什么都不执行", "Utforsk og foreslå en plan — ingenting kjører før du godkjenner", "Explorer et proposer un plan — rien ne s'exécute avant votre accord", "Explora y propone un plan: nada se ejecuta hasta que lo apruebes", "プランを探索して提案 — 承認するまで何も実行されません", "استكشف واقترح خطة — لا يتم تشغيل أي شيء حتى توافق", "Plan erkunden und vorschlagen – nichts wird ausgeführt, bis du zustimmst", "Explore e proponha um plano — nada é executado até você aprovar"],
  "Ask before edits and commands": ["改动和命令前先询问", "Spør før endringer og kommandoer", "Demander avant modifications et commandes", "Preguntar antes de ediciones y comandos", "編集とコマンドの前に確認", "اسأل قبل التعديلات والأوامر", "Vor Bearbeitungen und Befehlen fragen", "Perguntar antes de edições e comandos"],
  "Run everything without asking": ["全部直接执行,不再询问", "Kjør alt uten å spørre", "Tout exécuter sans demander", "Ejecutar todo sin preguntar", "確認なしですべて実行", "شغّل كل شيء دون سؤال", "Alles ohne Nachfrage ausführen", "Executar tudo sem perguntar"],
  // ── composer ──
  "Ask Mimi…  (drop or paste files)": ["向 Mimi 提问……(可拖入或粘贴文件)", "Spør Mimi …  (slipp eller lim inn filer)", "Demandez à Mimi…  (déposez ou collez des fichiers)", "Pregunta a Mimi… (suelta o pega archivos)", "Mimiに質問…（ファイルをドロップまたは貼り付け）", "اسأل Mimi… (أسقط أو الصق الملفات)", "Frag Mimi… (Dateien ablegen oder einfügen)", "Pergunte à Mimi… (solte ou cole arquivos)"],
  "Stop": ["停止", "Stopp", "Arrêter", "Detener", "停止", "إيقاف", "Stopp", "Parar"],
  "Today's free allowance for Mimi Puppy and Mimi Hound is used up": ["Mimi Puppy 和 Mimi Hound 今天的免费额度已用完", "Dagens gratiskvote for Mimi Puppy og Mimi Hound er brukt opp", "L’allocation gratuite du jour pour Mimi Puppy et Mimi Hound est épuisée", "La asignación gratuita de hoy para Mimi Puppy y Mimi Hound se ha agotado", "Mimi PuppyとMimi Houndの今日の無料枠は使い切りました", "تم استنفاد الحصة المجانية اليومية لـ Mimi Puppy وMimi Hound", "Das heutige kostenlose Kontingent für Mimi Puppy und Mimi Hound ist aufgebraucht", "A cota gratuita de hoje para Mimi Puppy e Mimi Hound foi usada"],
  "resets at": ["将于以下时间重置：", "tilbakestilles kl.", "réinitialisé à", "se restablece a las", "リセット時刻:", "تتم إعادة التعيين في", "wird zurückgesetzt um", "reinicia às"],
  "Switch to Mimi Wolf": ["切换到 Mimi Wolf", "Bytt til Mimi Wolf", "Passer à Mimi Wolf", "Cambiar a Mimi Wolf", "Mimi Wolfに切り替え", "التبديل إلى Mimi Wolf", "Zu Mimi Wolf wechseln", "Mudar para Mimi Wolf"],
  "Mimi Puppy": ["Mimi Puppy", "Mimi Puppy", "Mimi Puppy", "Mimi Puppy", "Mimi Puppy", "Mimi Puppy", "Mimi Puppy", "Mimi Puppy"],
  "free requests left today": ["次免费请求今天剩余", "gratis forespørsler igjen i dag", "requêtes gratuites restantes aujourd'hui", "solicitudes gratuitas restantes hoy", "今日の残り無料リクエスト", "طلبات مجانية متبقية اليوم", "kostenlose Anfragen heute übrig", "solicitações gratuitas restantes hoje"],
  // ── settings tabs ──
  "General": ["通用", "Generelt", "Général", "General", "一般", "عام", "Allgemein", "Geral"],
  "Models": ["模型", "Modeller", "Modèles", "Modelos", "モデル", "النماذج", "Modelle", "Modelos"],
  "Instructions": ["指令", "Instruksjoner", "Instructions", "Instrucciones", "指示", "التعليمات", "Anweisungen", "Instruções"],
  "Skills": ["技能", "Ferdigheter", "Compétences", "Habilidades", "スキル", "المهارات", "Fähigkeiten", "Habilidades"],
  "Search your skills…": ["搜索你的技能…", "Søk i ferdighetene dine…", "Rechercher vos compétences…", "Buscar tus habilidades…", "スキルを検索…", "ابحث في مهاراتك…", "Suche deine Fähigkeiten…", "Pesquisar suas habilidades…"],
  "Voice input": ["语音输入", "Taleinndata", "Saisie vocale", "Entrada de voz", "音声入力", "الإدخال الصوتي", "Spracheingabe", "Entrada de voz"],
  "Memory": ["记忆", "Minne", "Mémoire", "Memoria", "メモリ", "الذاكرة", "Speicher", "Memória"],
  "Personas": ["角色", "Personaer", "Personas", "Personas", "ペルソナ", "الشخصيات", "Personas", "Personas"],
  "Transfer guide": ["迁移指南", "Overføringsguide", "Guide de correspondance", "Guía de transferencia", "転送ガイド", "دليل النقل", "Übertragungsanleitung", "Guia de transferência"],
  // ── settings ▸ general ──
  "Setup & updates": ["安装与更新", "Oppsett og oppdateringer", "Configuration et mises à jour", "Configuración y actualizaciones", "セットアップと更新", "الإعداد والتحديثات", "Einrichtung & Updates", "Configuração e atualizações"],
  "Run setup again": ["重新运行初始设置", "Kjør oppsettet på nytt", "Relancer la configuration", "Ejecutar configuración de nuevo", "セットアップを再実行", "إعادة تشغيل الإعداد", "Einrichtung erneut ausführen", "Executar configuração novamente"],
  "Show the tour": ["查看引导", "Vis omvisningen", "Voir la visite guidée", "Mostrar el recorrido", "ツアーを表示", "عرض الجولة", "Tour anzeigen", "Mostrar o tour"],
  "Replay the first-run setup, or the five-step tour of the interface.": ["重放首次设置,或界面的五步引导。", "Spill av førstegangsoppsettet eller femtrinnsomvisningen på nytt.", "Rejouer la configuration initiale ou la visite en cinq étapes.", "Repetir la configuración inicial o el recorrido de cinco pasos por la interfaz.", "初回セットアップまたはインターフェースの5ステップツアーを再度実行します。", "إعادة تشغيل الإعداد الأول أو الجولة المكونة من خمس خطوات للواجهة.", "Ersteinrichtung oder die fünfteilige Tour durch die Oberfläche erneut abspielen.", "Repetir a configuração inicial ou o tour de cinco passos pela interface."],
  "Language": ["语言", "Språk", "Langue", "Idioma", "言語", "اللغة", "Sprache", "Idioma"],
  "The app's own labels and menus. Mimi replies in whatever language you write.": ["应用界面的标签与菜单语言。Mimi 会用你输入的语言回复。", "Appens egne etiketter og menyer. Mimi svarer på språket du skriver.", "Les libellés et menus de l'app. Mimi répond dans la langue où vous écrivez.", "Etiquetas y menús de la aplicación. Mimi responde en el idioma en que escribas.", "アプリのラベルとメニュー。Mimiはあなたが書く言語で返信します。", "تسميات التطبيق وقوائمه. ترد Mimi بأي لغة تكتب بها.", "Die eigenen Beschriftungen und Menüs der App. Mimi antwortet in der Sprache, in der du schreibst.", "Os rótulos e menus do aplicativo. Mimi responde no idioma em que você escreve."],
  // ── tour ──
  "Ask for the outcome, not the steps": ["说出你要的结果,而不是步骤", "Be om resultatet, ikke stegene", "Demandez le résultat, pas les étapes", "Pide el resultado, no los pasos", "手順ではなく結果を求める", "اطلب النتيجة، لا الخطوات", "Frage nach dem Ergebnis, nicht nach den Schritten", "Peça o resultado, não os passos"],
  "Three gears, one key": ["三个档位,一个按键", "Tre gir, én tast", "Trois vitesses, une touche", "Tres engranajes, una clave", "3つの歯車、1つの鍵", "ثلاثة تروس، مفتاح واحد", "Drei Zahnräder, ein Schlüssel", "Três engrenagens, uma chave"],
  "Your folder is the workspace": ["你的文件夹就是工作区", "Mappen din er arbeidsområdet", "Votre dossier est l'espace de travail", "Tu carpeta es el espacio de trabajo", "あなたのフォルダがワークスペースです", "مجلدك هو مساحة العمل", "Dein Ordner ist der Arbeitsbereich", "Sua pasta é o espaço de trabalho"],
  "Watch the work happen": ["看着工作进行", "Se arbeidet skje", "Regardez le travail se faire", "Observa cómo se hace el trabajo", "作業が行われるのを見る", "شاهد العمل يحدث", "Sieh zu, wie die Arbeit passiert", "Veja o trabalho acontecer"],
  "Everything else lives here": ["其余一切都在这里", "Alt annet bor her", "Tout le reste vit ici", "Todo lo demás vive aquí", "その他はすべてここにあります", "كل شيء آخر يعيش هنا", "Alles andere lebt hier", "Todo o resto vive aqui"],
  "Skip tour": ["跳过引导", "Hopp over", "Passer la visite", "Omitir recorrido", "ツアーをスキップ", "تخطي الجولة", "Tour überspringen", "Pular tour"],
  "Next": ["下一步", "Neste", "Suivant", "Siguiente", "次へ", "التالي", "Weiter", "Próximo"],
  "Back": ["上一步", "Tilbake", "Retour", "Atrás", "戻る", "رجوع", "Zurück", "Voltar"],
  "Done": ["完成", "Ferdig", "Terminé", "Hecho", "完了", "تم", "Fertig", "Concluído"],
  // ── onboarding ──
  "Welcome to MimiWork": ["欢迎使用 MimiWork", "Velkommen til MimiWork", "Bienvenue dans MimiWork", "Bienvenido a MimiWork", "MimiWorkへようこそ", "مرحبًا بك في MimiWork", "Willkommen bei MimiWork", "Bem-vindo ao MimiWork"],
  "Skip setup": ["跳过设置", "Hopp over oppsett", "Ignorer la configuration", "Omitir configuración", "セットアップをスキップ", "تخطي الإعداد", "Einrichtung überspringen", "Pular configuração"],
  "skip anyway": ["仍然跳过", "hopp over likevel", "ignorer quand même", "Omitir de todos modos", "それでもスキップ", "تخطي على أي حال", "Trotzdem überspringen", "Pular mesmo assim"],
  "Checking…": ["检查中……", "Sjekker …", "Vérification…", "Comprobando…", "確認中…", "جارٍ التحقق…", "Wird geprüft…", "Verificando…"],
  "Create your QualiTaTi account — or sign in — and the Mimi models are ready to work, free tier included. No API keys.": ["注册 QualiTaTi 账号(或直接登录),Mimi 模型即刻可用,含每日免费档。无需 API 密钥。", "Opprett QualiTaTi-kontoen din — eller logg inn — så er Mimi-modellene klare, gratisnivå inkludert. Ingen API-nøkler.", "Créez votre compte QualiTaTi — ou connectez-vous — et les modèles Mimi sont prêts, niveau gratuit inclus. Aucune clé API.", "Crea tu cuenta de QualiTaTi — o inicia sesión — y los modelos Mimi estarán listos para trabajar, con el plan gratuito incluido. Sin claves API.", "QualiTaTiアカウントを作成するか、サインインしてください。Mimiモデルはすぐに使える状態になり、無料枠も含まれます。APIキーは不要です。", "أنشئ حساب QualiTaTi الخاص بك — أو سجّل الدخول — وستكون نماذج Mimi جاهزة للعمل، مع تضمين الخطة المجانية. لا حاجة لمفاتيح API.", "Erstelle dein QualiTaTi-Konto – oder melde dich an – und die Mimi-Modelle sind einsatzbereit, inklusive kostenlosem Tarif. Keine API-Schlüssel nötig.", "Crie sua conta QualiTaTi — ou entre — e os modelos Mimi estarão prontos para trabalhar, com o plano gratuito incluído. Sem chaves de API."],
  "I'll use my own API key instead (OpenAI, Anthropic, Gemini…)": ["我想用自己的 API 密钥(OpenAI、Anthropic、Gemini……)", "Jeg bruker heller min egen API-nøkkel (OpenAI, Anthropic, Gemini …)", "J'utiliserai plutôt ma propre clé API (OpenAI, Anthropic, Gemini…)", "Usaré mi propia clave API en su lugar (OpenAI, Anthropic, Gemini…)", "代わりに自分のAPIキーを使用します（OpenAI、Anthropic、Gemini…）", "سأستخدم مفتاح API الخاص بي بدلاً من ذلك (OpenAI، Anthropic، Gemini…)", "Ich verwende stattdessen meinen eigenen API-Schlüssel (OpenAI, Anthropic, Gemini…)", "Vou usar minha própria chave de API (OpenAI, Anthropic, Gemini…)"],
  "← Back to QualiTaTi sign-in": ["← 返回 QualiTaTi 登录", "← Tilbake til QualiTaTi-innlogging", "← Retour à la connexion QualiTaTi", "← Volver al inicio de sesión de QualiTaTi", "← QualiTaTiサインインに戻る", "← العودة إلى تسجيل الدخول إلى QualiTaTi", "← Zurück zur QualiTaTi-Anmeldung", "← Voltar para o login do QualiTaTi"],
  // ── shared interface language ──
  "Add": ["添加", "Legg til", "Ajouter", "Añadir", "追加", "إضافة", "Hinzufügen", "Adicionar"],
  "Edit": ["编辑", "Rediger", "Modifier", "Editar", "編集", "تعديل", "Bearbeiten", "Editar"],
  "Delete": ["删除", "Slett", "Supprimer", "Eliminar", "削除", "حذف", "Löschen", "Excluir"],
  "Delete?": ["确认删除?", "Slette?", "Supprimer ?", "¿Eliminar?", "削除しますか？", "حذف؟", "Löschen?", "Excluir?"],
  "Remove": ["移除", "Fjern", "Retirer", "Quitar", "削除", "إزالة", "Entfernen", "Remover"],
  "Cancel": ["取消", "Avbryt", "Annuler", "Cancelar", "キャンセル", "إلغاء", "Abbrechen", "Cancelar"],
  "Close": ["关闭", "Lukk", "Fermer", "Cerrar", "閉じる", "إغلاق", "Schließen", "Fechar"],
  "Save": ["保存", "Lagre", "Enregistrer", "Guardar", "保存", "حفظ", "Speichern", "Salvar"],
  "Continue": ["继续", "Fortsett", "Continuer", "Continuar", "続行", "متابعة", "Fortfahren", "Continuar"],
  "Connect": ["连接", "Koble til", "Connecter", "Conectar", "接続", "اتصال", "Verbinden", "Conectar"],
  "Connected": ["已连接", "Tilkoblet", "Connecté", "Conectado", "接続済み", "متصل", "Verbunden", "Conectado"],
  "Disconnect": ["断开连接", "Koble fra", "Déconnecter", "Desconectar", "切断", "قطع الاتصال", "Trennen", "Desconectar"],
  "Enable": ["启用", "Aktiver", "Activer", "Habilitar", "有効にする", "تمكين", "Aktivieren", "Ativar"],
  "Disable": ["停用", "Deaktiver", "Désactiver", "Deshabilitar", "無効にする", "تعطيل", "Deaktivieren", "Desativar"],
  "Loading…": ["加载中……", "Laster …", "Chargement…", "Cargando…", "読み込み中…", "جارٍ التحميل…", "Wird geladen…", "Carregando…"],
  "Looking…": ["查找中……", "Leter …", "Recherche…", "Buscando…", "検索中…", "جارٍ البحث…", "Wird gesucht…", "Procurando…"],
  "Search": ["搜索", "Søk", "Rechercher", "Buscar", "検索", "بحث", "Suchen", "Pesquisar"],
  "Open": ["打开", "Åpne", "Ouvrir", "Abrir", "開く", "فتح", "Öffnen", "Abrir"],
  "Refresh": ["刷新", "Oppdater", "Actualiser", "Actualizar", "更新", "تحديث", "Aktualisieren", "Atualizar"],
  "Copy": ["复制", "Kopier", "Copier", "Copiar", "コピー", "نسخ", "Kopieren", "Copiar"],
  "Copied": ["已复制", "Kopiert", "Copié", "Copiado", "コピーしました", "تم النسخ", "Kopiert", "Copiado"],
  "Try again": ["重试", "Prøv igjen", "Réessayer", "Intentar de nuevo", "再試行", "إعادة المحاولة", "Erneut versuchen", "Tentar novamente"],
  "Learn more": ["了解更多", "Finn ut mer", "En savoir plus", "Más información", "詳細を見る", "اعرف المزيد", "Mehr erfahren", "Saber mais"],
  "Coming soon": ["即将推出", "Kommer snart", "Bientôt disponible", "Próximamente", "近日公開", "قريبًا", "Bald verfügbar", "Em breve"],
  "default": ["默认", "standard", "par défaut", "predeterminado", "デフォルト", "افتراضي", "Standard", "padrão"],
  "main": ["主目录", "hovedmappe", "principal", "principal", "メイン", "رئيسي", "Haupt", "principal"],
  "missing": ["缺失", "mangler", "manquant", "falta", "見つかりません", "مفقود", "fehlt", "em falta"],
  "Tasks": ["任务", "Oppgaver", "Tâches", "Tareas", "タスク", "المهام", "Aufgaben", "Tarefas"],
  "Progress": ["进度", "Fremdrift", "Progression", "Progreso", "進捗", "التقدم", "Fortschritt", "Progresso"],
  "Sources": ["来源", "Kilder", "Sources", "Fuentes", "ソース", "المصادر", "Quellen", "Fontes"],
  "Folders": ["文件夹", "Mapper", "Dossiers", "Carpetas", "フォルダ", "المجلدات", "Ordner", "Pastas"],
  "Add a folder": ["添加文件夹", "Legg til en mappe", "Ajouter un dossier", "Añadir una carpeta", "フォルダを追加", "إضافة مجلد", "Ordner hinzufügen", "Adicionar uma pasta"],
  "No folder yet": ["尚无文件夹", "Ingen mappe ennå", "Aucun dossier pour l'instant", "Aún no hay carpeta", "フォルダがまだありません", "لا يوجد مجلد بعد", "Noch kein Ordner", "Ainda sem pasta"],
  "folder": ["个文件夹", "mappe", "dossier", "carpeta", "フォルダ", "مجلد", "Ordner", "pasta"],
  "folders": ["个文件夹", "mapper", "dossiers", "carpetas", "フォルダ", "مجلدات", "Ordner", "pastas"],
  "Mimi works in a temporary space. Add a folder to work on your own files.": ["Mimi 目前在临时空间中工作。添加一个文件夹,即可处理你自己的文件。", "Mimi jobber i et midlertidig område. Legg til en mappe for å jobbe med dine egne filer.", "Mimi travaille dans un espace temporaire. Ajoutez un dossier pour travailler sur vos propres fichiers.", "Mimi trabaja en un espacio temporal. Añade una carpeta para trabajar con tus propios archivos.", "Mimiは一時的なスペースで動作します。自分のファイルで作業するにはフォルダを追加してください。", "يعمل Mimi في مساحة مؤقتة. أضف مجلدًا للعمل على ملفاتك الخاصة.", "Mimi arbeitet in einem temporären Bereich. Füge einen Ordner hinzu, um an deinen eigenen Dateien zu arbeiten.", "A Mimi trabalha num espaço temporário. Adiciona uma pasta para trabalhares nos teus próprios ficheiros."],
  "Recommended": ["推荐", "Anbefalt", "Recommandé", "Recomendado", "おすすめ", "موصى به", "Empfohlen", "Recomendado"],
  "Access": ["访问权限", "Tilgang", "Accès", "Acceso", "アクセス", "الوصول", "Zugriff", "Acesso"],
  "Tools": ["工具", "Verktøy", "Outils", "Herramientas", "ツール", "الأدوات", "Werkzeuge", "Ferramentas"],
  "asks first": ["会先询问", "spør først", "demande d'abord", "pregunta primero", "最初に確認", "يسأل أولاً", "fragt zuerst", "pergunta primeiro"],
  "Coworker": ["同事", "Medarbeider", "Coéquipier", "Compañero", "共同作業者", "زميل", "Mitarbeiter", "Colega"],
  "Search chats": ["搜索对话", "Søk i samtaler", "Rechercher des conversations", "Buscar chats", "チャットを検索", "البحث في المحادثات", "Chats durchsuchen", "Pesquisar conversas"],
  "No chats found.": ["未找到对话。", "Ingen samtaler funnet.", "Aucune conversation trouvée.", "No se encontraron chats.", "チャットが見つかりません。", "لا توجد محادثات.", "Keine Chats gefunden.", "Nenhuma conversa encontrada."],
  "New session": ["新建会话", "Ny økt", "Nouvelle session", "Nueva sesión", "新しいセッション", "جلسة جديدة", "Neue Sitzung", "Nova sessão"],
  "New project": ["新建项目", "Nytt prosjekt", "Nouveau projet", "Nuevo proyecto", "新しいプロジェクト", "مشروع جديد", "Neues Projekt", "Novo projeto"],
  "Artifacts": ["成果文件", "Resultatfiler", "Livrables", "Artefactos", "アーティファクト", "القطع الأثرية", "Artefakte", "Artefactos"],
  "Try a task": ["试试这项任务", "Prøv en oppgave", "Essayez une tâche", "Probar una tarea", "タスクを試す", "جرّب مهمة", "Aufgabe versuchen", "Experimentar uma tarefa"],
  "Show sidebar": ["显示侧边栏", "Vis sidefelt", "Afficher la barre latérale", "Mostrar barra lateral", "サイドバーを表示", "إظهار الشريط الجانبي", "Seitenleiste anzeigen", "Mostrar barra lateral"],
  "Session actions": ["会话操作", "Økthandlinger", "Actions de la session", "Acciones de sesión", "セッション操作", "إجراءات الجلسة", "Sitzungsaktionen", "Ações da sessão"],
  "Working now": ["正在工作", "Arbeider nå", "En cours", "Trabajando ahora", "作業中", "يعمل الآن", "Arbeitet jetzt", "A trabalhar agora"],
  "Sleeping (will wake itself)": ["休眠中(会自动唤醒)", "Sover (våkner av seg selv)", "En veille (se réveillera seul)", "Durmiendo (se despertará solo)", "スリープ中（自動で起きる）", "نائم (سيستيقظ تلقائيًا)", "Schläft (wacht von selbst auf)", "A dormir (acordará sozinho)"],
  "Group & filter conversations": ["分组并筛选对话", "Grupper og filtrer samtaler", "Grouper et filtrer les conversations", "Agrupar y filtrar conversaciones", "会話をグループ化・フィルタ", "تجميع وتصفية المحادثات", "Gespräche gruppieren und filtern", "Agrupar e filtrar conversas"],
  "Choose a persona": ["选择角色", "Velg en persona", "Choisir un persona", "Elegir un personaje", "ペルソナを選択", "اختر شخصية", "Persona wählen", "Escolher uma persona"],
  "Start with a specific persona": ["使用指定角色开始", "Start med en bestemt persona", "Démarrer avec un persona précis", "Comenzar con un personaje específico", "特定のペルソナで開始", "ابدأ بشخصية محددة", "Mit einer bestimmten Persona starten", "Começar com uma persona específica"],
  // ── onboarding ──
  "Pick a model provider — MimiWork runs on your own key, and your key and your data stay on this computer.": ["选择模型提供商——MimiWork 使用你自己的密钥运行,密钥和数据都保留在这台电脑上。", "Velg en modelltilbyder — MimiWork bruker din egen nøkkel, og både nøkkelen og dataene forblir på denne maskinen.", "Choisissez un fournisseur de modèles — MimiWork utilise votre propre clé, qui reste sur cet ordinateur avec vos données.", "Elige un proveedor de modelos: MimiWork funciona con tu propia clave, y tu clave y tus datos permanecen en este ordenador.", "モデルプロバイダーを選択 — MimiWorkは自分のキーで動作し、キーとデータはこのコンピュータに留まります。", "اختر مزود النموذج — يعمل MimiWork بمفتاحك الخاص، ويبقى مفتاحك وبياناتك على هذا الكمبيوتر.", "Wähle einen Modellanbieter — MimiWork läuft mit deinem eigenen Schlüssel, und dein Schlüssel und deine Daten bleiben auf diesem Computer.", "Escolhe um fornecedor de modelos — a MimiWork funciona com a tua própria chave, e a tua chave e os teus dados permanecem neste computador."],
  "Nothing works without a model —": ["没有模型就无法运行——", "Ingenting virker uten en modell —", "Rien ne fonctionne sans modèle —", "Nada funciona sin un modelo —", "モデルなしでは何も動作しません —", "لا شيء يعمل بدون نموذج —", "Ohne Modell funktioniert nichts —", "Nada funciona sem um modelo —"],
  "Models can be enabled or hidden anytime in Settings ▸ Models.": ["可随时在“设置 ▸ 模型”中启用或隐藏模型。", "Modeller kan aktiveres eller skjules når som helst under Innstillinger ▸ Modeller.", "Les modèles peuvent être activés ou masqués à tout moment dans Réglages ▸ Modèles.", "Los modelos se pueden habilitar u ocultar en cualquier momento en Ajustes ▸ Modelos.", "モデルはいつでも設定 ▸ モデルで有効化または非表示にできます。", "يمكن تمكين النماذج أو إخفاؤها في أي وقت من الإعدادات ▸ النماذج.", "Modelle können jederzeit in Einstellungen ▸ Modelle aktiviert oder ausgeblendet werden.", "Os modelos podem ser ativados ou ocultados a qualquer momento em Definições ▸ Modelos."],
  "Connect your everyday tools": ["连接常用工具", "Koble til verktøyene du bruker", "Connectez vos outils du quotidien", "Conecta tus herramientas cotidianas", "日常のツールを接続する", "اربط أدواتك اليومية", "Verbinde deine Alltagswerkzeuge", "Conecte as suas ferramentas do dia a dia"],
  "Chat can only advise. Connected, Mimi does the actual work:": ["聊天只能提供建议。连接后,Mimi 就能实际执行工作:", "Chat kan bare gi råd. Når verktøyene er koblet til, gjør Mimi selve arbeidet:", "Le chat ne peut que conseiller. Une fois connecté, Mimi effectue réellement le travail :", "El chat solo puede aconsejar. Conectada, Mimi hace el trabajo real:", "チャットはアドバイスしかできません。接続すると、Mimiが実際の作業を行います：", "الدردشة يمكنها فقط تقديم النصائح. عند الاتصال، تقوم ميمي بالعمل الفعلي:", "Chat kann nur beraten. Verbunden erledigt Mimi die eigentliche Arbeit:", "O chat só pode aconselhar. Conectada, a Mimi faz o trabalho real:"],
  "Stay on top of email": ["掌握邮件动态", "Hold oversikt over e-post", "Gardez le contrôle de vos e-mails", "Mantente al día con el correo", "メールを見逃さない", "ابقَ على اطلاع بالبريد الإلكتروني", "Bleib bei E-Mails auf dem Laufenden", "Fique por dentro do e-mail"],
  "Keep up with Slack": ["跟进 Slack 消息", "Følg med på Slack", "Suivez ce qui se passe sur Slack", "Mantente al día con Slack", "Slackを把握する", "تابع Slack", "Bleib bei Slack auf dem Laufenden", "Acompanhe o Slack"],
  "Ship code": ["交付代码", "Lever kode", "Livrez du code", "Envía código", "コードを出す", "أرسل الكود", "Code ausliefern", "Envie código"],
  "Keep your notes in reach": ["随时取用笔记", "Ha notatene for hånden", "Gardez vos notes à portée de main", "Ten tus notas a mano", "ノートを手元に", "أبقِ ملاحظاتك في متناول اليد", "Halte deine Notizen griffbereit", "Mantenha as suas notas à mão"],
  "Keep the CRM current": ["保持 CRM 最新", "Hold CRM-systemet oppdatert", "Gardez le CRM à jour", "Mantén el CRM actualizado", "CRMを最新に保つ", "حافظ على تحديث CRM", "Halte das CRM aktuell", "Mantenha o CRM atualizado"],
  "Track every relationship": ["跟进每一段关系", "Følg alle relasjoner", "Suivez chaque relation", "Sigue cada relación", "すべての関係を追跡する", "تتبع كل علاقة", "Verfolge jede Beziehung", "Acompanhe cada relação"],
  "Coming soon — pending Google’s app verification.": ["即将推出——正在等待 Google 应用验证。", "Kommer snart — avventer Googles appverifisering.", "Bientôt disponible — en attente de la validation de l'application par Google.", "Próximamente: pendiente de la verificación de la aplicación de Google.", "近日公開 — Googleのアプリ審査待ち。", "قريبًا — بانتظار التحقق من تطبيق Google.", "Demnächst verfügbar – ausstehend: Googles App-Verifizierung.", "Em breve — pendente da verificação do app do Google."],
  "Connect them when you need them": ["需要时再连接", "Koble dem til når du trenger dem", "Connectez-les quand vous en avez besoin", "Conéctalas cuando las necesites", "必要なときに接続する", "اربطها عندما تحتاجها", "Verbinde sie, wenn du sie brauchst", "Conecte-as quando precisar"],
  "Every tool connects from the Connectors page with your own tokens or a local one-click sign-in — nothing goes through a third-party cloud.": ["每个工具都可在“连接器”页面使用你自己的令牌或本地一键登录进行连接——数据不会经过第三方云端。", "Alle verktøy kobles til fra Koblinger-siden med dine egne tokener eller lokal ettklikksinnlogging — ingenting går via en tredjepartssky.", "Chaque outil se connecte depuis la page Connecteurs avec vos propres jetons ou une connexion locale en un clic — rien ne transite par un cloud tiers.", "Cada herramienta se conecta desde la página de Conectores con tus propios tokens o con un inicio de sesión local de un clic: nada pasa por una nube de terceros.", "各ツールはコネクターページから、自分のトークンまたはローカルのワンクリックサインインで接続します。サードパーティのクラウドを経由しません。", "كل أداة تتصل من صفحة الموصلات باستخدام رموزك الخاصة أو تسجيل دخول محلي بنقرة واحدة — لا شيء يمر عبر سحابة طرف ثالث.", "Jedes Werkzeug verbindet sich über die Connectors-Seite mit deinen eigenen Tokens oder einem lokalen Ein-Klick-Login – nichts läuft über eine Drittanbieter-Cloud.", "Cada ferramenta conecta-se a partir da página de Conectores com os seus próprios tokens ou com um login local de um clique — nada passa por uma nuvem de terceiros."],
  "30+ more tools on the Connectors page — add or remove anytime. Tokens stay on this computer.": ["“连接器”页面还有 30 多种工具——可随时添加或移除。令牌保留在这台电脑上。", "Du finner over 30 andre verktøy på Koblinger-siden — legg til eller fjern dem når som helst. Tokener forblir på denne maskinen.", "Plus de 30 autres outils sont disponibles sur la page Connecteurs — ajoutez-les ou retirez-les à tout moment. Les jetons restent sur cet ordinateur.", "Más de 30 herramientas en la página de Conectores: añade o elimina en cualquier momento. Los tokens permanecen en este ordenador.", "コネクターページには30以上のツールがあります。いつでも追加・削除可能。トークンはこのコンピューターに残ります。", "أكثر من 30 أداة في صفحة الموصلات — أضف أو أزل في أي وقت. تبقى الرموز على هذا الكمبيوتر.", "Mehr als 30 weitere Werkzeuge auf der Connectors-Seite – jederzeit hinzufügen oder entfernen. Tokens bleiben auf diesem Computer.", "Mais de 30 ferramentas na página de Conectores — adicione ou remova a qualquer momento. Os tokens permanecem neste computador."],
  "Give Mimi her first task": ["给 Mimi 第一个任务", "Gi Mimi hennes første oppgave", "Confiez sa première tâche à Mimi", "Dale a Mimi su primera tarea", "Mimiに最初のタスクを与える", "أعطِ ميمي مهمتها الأولى", "Gib Mimi ihre erste Aufgabe", "Dê à Mimi a primeira tarefa"],
  "Pick a folder Mimi may look at — everything stays on this computer, and she only ever sees folders you hand her.": ["选择一个允许 Mimi 查看的文件夹——所有内容都保留在这台电脑上,她只能看到你交给她的文件夹。", "Velg en mappe Mimi kan se i — alt forblir på denne maskinen, og hun ser bare mapper du gir henne tilgang til.", "Choisissez un dossier que Mimi peut consulter — tout reste sur cet ordinateur et elle ne voit que les dossiers que vous lui confiez.", "Elige una carpeta que Mimi pueda mirar: todo permanece en este ordenador, y solo ve las carpetas que le entregues.", "Mimiが見てもよいフォルダーを選んでください。すべてこのコンピューターに留まり、彼女はあなたが渡したフォルダーだけを見ます。", "اختر مجلدًا يمكن لميمي الاطلاع عليه — كل شيء يبقى على هذا الكمبيوتر، وهي ترى فقط المجلدات التي تسلمها إياها.", "Wähle einen Ordner, den Mimi ansehen darf – alles bleibt auf diesem Computer, und sie sieht nur Ordner, die du ihr gibst.", "Escolha uma pasta que a Mimi possa ver — tudo permanece neste computador, e ela só vê as pastas que você lhe der."],
  "Choose a folder": ["选择文件夹", "Velg en mappe", "Choisir un dossier", "Elige una carpeta", "フォルダーを選択", "اختر مجلدًا", "Ordner wählen", "Escolher uma pasta"],
  "Your course folder, a project, this week's mess — any folder works.": ["课程文件夹、项目或本周堆积的杂乱文件——任何文件夹都可以。", "Kursmappen, et prosjekt eller ukens rot — hvilken som helst mappe fungerer.", "Votre dossier de cours, un projet ou le désordre de la semaine — n'importe quel dossier convient.", "Tu carpeta de curso, un proyecto, el desorden de esta semana: cualquier carpeta sirve.", "コースのフォルダー、プロジェクト、今週の散らかり — どのフォルダーでも構いません。", "مجلد الدورة، مشروع، فوضى هذا الأسبوع — أي مجلد يصلح.", "Dein Kursordner, ein Projekt, das Chaos dieser Woche – jeder Ordner funktioniert.", "A pasta do seu curso, um projeto, a bagunça desta semana — qualquer pasta serve."],
  "Allow Mimi to edit and organize files in it": ["允许 Mimi 编辑和整理其中的文件", "La Mimi redigere og organisere filene i den", "Autoriser Mimi à modifier et organiser les fichiers", "Permitir que Mimi edite y organice archivos en ella", "Mimiがその中のファイルを編集・整理することを許可する", "اسمح لميمي بتحرير وتنظيم الملفات فيه", "Mimi erlauben, Dateien darin zu bearbeiten und zu organisieren", "Permitir que a Mimi edite e organize arquivos nela"],
  "Change": ["更改", "Endre", "Changer", "Cambiar", "変更", "تغيير", "Ändern", "Alterar"],
  "Now pick her first task:": ["现在选择她的第一个任务:", "Velg nå hennes første oppgave:", "Choisissez maintenant sa première tâche :", "Ahora elige su primera tarea:", "次に彼女の最初のタスクを選びます：", "الآن اختر مهمتها الأولى:", "Jetzt wähle ihre erste Aufgabe:", "Agora escolha a primeira tarefa dela:"],
  "Then pick her first task:": ["然后选择她的第一个任务:", "Velg deretter hennes første oppgave:", "Choisissez ensuite sa première tâche :", "Luego elige su primera tarea:", "それから彼女の最初のタスクを選びます：", "ثم اختر مهمتها الأولى:", "Dann wähle ihre erste Aufgabe:", "Depois escolha a primeira tarefa dela:"],
  "Summarize what's in this folder": ["总结此文件夹中的内容", "Oppsummer innholdet i denne mappen", "Résumer le contenu de ce dossier", "Resumir lo que hay en esta carpeta", "このフォルダーの中身を要約する", "لخص ما في هذا المجلد", "Zusammenfassen, was in diesem Ordner ist", "Resumir o que está nesta pasta"],
  "Tidy and organize these files": ["整理这些文件", "Rydd og organiser disse filene", "Ranger et organiser ces fichiers", "Ordenar y organizar estos archivos", "これらのファイルを整理する", "رتب ونظم هذه الملفات", "Diese Dateien aufräumen und organisieren", "Organizar e arrumar estes arquivos"],
  "Plan my week from what's here": ["根据这里的内容规划本周", "Planlegg uken min ut fra innholdet her", "Planifier ma semaine à partir de ce dossier", "Planificar mi semana a partir de lo que hay aquí", "ここから私の週を計画する", "خطط لأسبوعي مما هو هنا", "Meine Woche anhand dessen planen, was hier ist", "Planear a minha semana a partir do que está aqui"],
  "Choose a folder first": ["请先选择文件夹", "Velg en mappe først", "Choisissez d'abord un dossier", "Elige una carpeta primero", "最初にフォルダーを選択してください", "اختر مجلدًا أولاً", "Zuerst einen Ordner wählen", "Escolha uma pasta primeiro"],
  "Needs the edit permission above": ["需要启用上方的编辑权限", "Krever redigeringstillatelsen ovenfor", "Nécessite l'autorisation de modification ci-dessus", "Necesita el permiso de edición anterior", "上記の編集権限が必要です", "يتطلب إذن التحرير أعلاه", "Benötigt die obige Bearbeitungsberechtigung", "Precisa da permissão de edição acima"],
  "Uses the edit permission": ["使用编辑权限", "Bruker redigeringstillatelsen", "Utilise l'autorisation de modification", "Usa el permiso de edición", "編集権限を使用します", "يستخدم إذن التحرير", "Verwendet die Bearbeitungsberechtigung", "Usa a permissão de edição"],
  "Create an automation instead": ["改为创建自动化", "Opprett en automatisering i stedet", "Créer plutôt une automatisation", "Crear una automatización en su lugar", "代わりに自動化を作成する", "أنشئ أتمتة بدلاً من ذلك", "Stattdessen eine Automatisierung erstellen", "Criar uma automação em vez disso"],
  "Just open a blank session": ["仅打开空白会话", "Bare åpne en tom økt", "Ouvrir simplement une session vide", "Solo abrir una sesión en blanco", "空のセッションを開くだけ", "فقط افتح جلسة فارغة", "Einfach eine leere Sitzung öffnen", "Apenas abrir uma sessão em branco"],
  "Replay this setup anytime: Settings ▸ Appearance ▸ Run setup again.": ["可随时重新运行此设置:“设置 ▸ 外观 ▸ 重新运行初始设置”。", "Kjør dette oppsettet på nytt når som helst: Innstillinger ▸ Utseende ▸ Kjør oppsettet på nytt.", "Relancez cette configuration à tout moment : Réglages ▸ Apparence ▸ Relancer la configuration.", "Repite esta configuración en cualquier momento: Configuración ▸ Apariencia ▸ Ejecutar configuración de nuevo.", "この設定はいつでも再実行できます：設定 ▸ 外観 ▸ セットアップを再実行。", "أعد تشغيل هذا الإعداد في أي وقت: الإعدادات ▸ المظهر ▸ إعادة تشغيل الإعداد.", "Dieses Setup jederzeit wiederholen: Einstellungen ▸ Darstellung ▸ Setup erneut ausführen.", "Repita esta configuração a qualquer momento: Definições ▸ Aparência ▸ Executar configuração novamente."],
  // ── files, artifacts and session access ──
  "Nothing produced yet — files Mimi writes appear here.": ["尚未生成任何内容——Mimi 创建的文件会显示在这里。", "Ingenting er laget ennå — filer Mimi skriver vises her.", "Aucun livrable pour l'instant — les fichiers créés par Mimi apparaîtront ici.", "Aún no se ha producido nada: los archivos que Mimi escribe aparecen aquí.", "まだ生成されていません — Mimiが書いたファイルはここに表示されます。", "لا شيء تم إنتاجه بعد — الملفات التي تكتبها ميمي تظهر هنا.", "Noch nichts erstellt – Dateien, die Mimi schreibt, erscheinen hier.", "Nada produzido ainda — os arquivos que a Mimi escreve aparecem aqui."],
  "Show the folder where these files are saved": ["显示这些文件的保存文件夹", "Vis mappen der filene er lagret", "Afficher le dossier où ces fichiers sont enregistrés", "Mostrar la carpeta donde se guardan estos archivos", "これらのファイルが保存されているフォルダーを表示", "أظهر المجلد حيث تُحفظ هذه الملفات", "Ordner anzeigen, in dem diese Dateien gespeichert sind", "Mostrar a pasta onde estes arquivos estão guardados"],
  "Refresh artifacts": ["刷新成果文件", "Oppdater resultatfiler", "Actualiser les livrables", "Actualizar artefactos", "アーティファクトを更新", "تحديث القطع الأثرية", "Artefakte aktualisieren", "Atualizar artefactos"],
  "File recovery": ["文件恢复", "Filgjenoppretting", "Récupération de fichiers", "Recuperación de archivos", "ファイル復元", "استعادة الملفات", "Dateiwiederherstellung", "Recuperação de arquivos"],
  "file changed in Mimi's latest recoverable turn.": ["个文件在 Mimi 最近一次可恢复任务中发生了更改。", "fil ble endret i Mimis siste gjenopprettbare runde.", "fichier modifié lors de la dernière action récupérable de Mimi.", "archivo cambiado en el último turno recuperable de Mimi.", "Mimiの最新の復元可能なターンで変更されたファイル。", "ملف تغير في آخر دورة قابلة للاستعادة لميمي.", "Datei geändert in Mimis letztem wiederherstellbaren Zug.", "arquivo alterado no último turno recuperável da Mimi."],
  "files changed in Mimi's latest recoverable turn.": ["个文件在 Mimi 最近一次可恢复任务中发生了更改。", "filer ble endret i Mimis siste gjenopprettbare runde.", "fichiers modifiés lors de la dernière action récupérable de Mimi.", "archivos cambiados en el último turno recuperable de Mimi.", "Mimiの最新の復元可能なターンで変更されたファイル。", "ملفات تغيرت في آخر دورة قابلة للاستعادة لميمي.", "Dateien geändert in Mimis letztem wiederherstellbaren Zug.", "arquivos alterados no último turno recuperável da Mimi."],
  "Undo latest file changes": ["撤销最近的文件更改", "Angre siste filendringer", "Annuler les dernières modifications", "Deshacer los últimos cambios de archivos", "最新のファイル変更を元に戻す", "تراجع عن آخر تغييرات الملفات", "Letzte Dateiänderungen rückgängig machen", "Desfazer as últimas alterações de arquivos"],
  "Undo Mimi's latest file changes?": ["撤销 Mimi 最近的文件更改？", "Angre Mimis siste filendringer?", "Annuler les dernières modifications de Mimi ?", "¿Deshacer los últimos cambios de archivos de Mimi?", "Mimiの最新のファイル変更を元に戻しますか？", "هل تريد التراجع عن آخر تغييرات ملفات ميمي؟", "Mimis letzte Dateiänderungen rückgängig machen?", "Desfazer as últimas alterações de arquivos da Mimi?"],
  "Restoring…": ["正在恢复……", "Gjenoppretter …", "Restauration…", "Restaurando…", "復元中…", "جارٍ الاستعادة…", "Wiederherstellen…", "A restaurar…"],
  "Wait for Mimi to finish before restoring files": ["请等待 Mimi 完成任务后再恢复文件", "Vent til Mimi er ferdig før du gjenoppretter filer", "Attendez que Mimi ait terminé avant de restaurer les fichiers", "Espera a que Mimi termine antes de restaurar archivos", "ファイルを復元する前にMimiが終了するのを待ってください", "انتظر حتى تنتهي ميمي قبل استعادة الملفات", "Warte, bis Mimi fertig ist, bevor du Dateien wiederherstellst", "Aguarde a Mimi terminar antes de restaurar arquivos"],
  "Restore modified files and remove files created in that turn": ["恢复被修改的文件，并移除该任务中新建的文件", "Gjenopprett endrede filer og fjern filer som ble opprettet i denne runden", "Restaurer les fichiers modifiés et supprimer ceux créés pendant cette action", "Restaurar archivos modificados y eliminar archivos creados en ese turno", "変更されたファイルを復元し、そのターンで作成されたファイルを削除する", "استعادة الملفات المعدلة وحذف الملفات التي أُنشئت في تلك الدورة", "Geänderte Dateien wiederherstellen und in diesem Zug erstellte Dateien entfernen", "Restaurar arquivos modificados e remover arquivos criados nesse turno"],
  "The available file changes have already been restored.": ["可用的文件更改已经恢复。", "De tilgjengelige filendringene er allerede gjenopprettet.", "Les modifications disponibles ont déjà été restaurées.", "Los cambios de archivo disponibles ya se han restaurado.", "利用可能なファイルの変更はすでに復元されています。", "تمت استعادة تغييرات الملفات المتاحة بالفعل.", "Die verfügbaren Dateiänderungen wurden bereits wiederhergestellt.", "As alterações de arquivo disponíveis já foram restauradas."],
  "Files could not be restored.": ["无法恢复文件。", "Filene kunne ikke gjenopprettes.", "Les fichiers n'ont pas pu être restaurés.", "No se pudieron restaurar los archivos.", "ファイルを復元できませんでした。", "تعذرت استعادة الملفات.", "Dateien konnten nicht wiederhergestellt werden.", "Não foi possível restaurar os arquivos."],
  "Back to artifacts": ["返回成果文件", "Tilbake til resultatfiler", "Retour aux livrables", "Volver a artefactos", "アーティファクトに戻る", "العودة إلى القطع الأثرية", "Zurück zu Artefakten", "Voltar para artefatos"],
  "Reload preview": ["重新加载预览", "Last inn forhåndsvisningen på nytt", "Recharger l'aperçu", "Recargar vista previa", "プレビューを再読み込み", "إعادة تحميل المعاينة", "Vorschau neu laden", "Recarregar pré-visualização"],
  "Open in default app": ["在默认应用中打开", "Åpne i standardappen", "Ouvrir dans l'application par défaut", "Abrir en la aplicación predeterminada", "デフォルトのアプリで開く", "فتح في التطبيق الافتراضي", "In Standard-App öffnen", "Abrir no aplicativo padrão"],
  "Copy path": ["复制路径", "Kopier sti", "Copier le chemin", "Copiar ruta", "パスをコピー", "نسخ المسار", "Pfad kopieren", "Copiar caminho"],
  "Copy full path": ["复制完整路径", "Kopier hele stien", "Copier le chemin complet", "Copiar ruta completa", "完全なパスをコピー", "نسخ المسار الكامل", "Vollständigen Pfad kopieren", "Copiar caminho completo"],
  "Show in folder": ["在文件夹中显示", "Vis i mappe", "Afficher dans le dossier", "Mostrar en carpeta", "フォルダに表示", "إظهار في المجلد", "Im Ordner anzeigen", "Mostrar na pasta"],
  "This folder is empty.": ["此文件夹为空。", "Denne mappen er tom.", "Ce dossier est vide.", "Esta carpeta está vacía.", "このフォルダは空です。", "هذا المجلد فارغ.", "Dieser Ordner ist leer.", "Esta pasta está vazia."],
  "Empty file.": ["空文件。", "Tom fil.", "Fichier vide.", "Archivo vacío.", "空のファイルです。", "ملف فارغ.", "Leere Datei.", "Arquivo vazio."],
  "Rendering PDF…": ["正在渲染 PDF……", "Gjengir PDF …", "Rendu du PDF…", "Renderizando PDF…", "PDFをレンダリング中…", "جارٍ عرض PDF…", "PDF wird gerendert…", "Renderizando PDF…"],
  "Parsing spreadsheet…": ["正在解析电子表格……", "Leser regnearket …", "Analyse de la feuille de calcul…", "Analizando hoja de cálculo…", "スプレッドシートを解析中…", "جارٍ تحليل جدول البيانات…", "Tabellenkalkulation wird analysiert…", "Analisando planilha…"],
  "The agent is requesting access to a folder": ["AI 同事正在请求访问文件夹", "Medarbeideren ber om tilgang til en mappe", "Le coéquipier demande l'accès à un dossier", "El agente está solicitando acceso a una carpeta", "エージェントがフォルダへのアクセスを要求しています", "الوكيل يطلب الوصول إلى مجلد", "Der Agent fordert Zugriff auf einen Ordner an", "O agente está solicitando acesso a uma pasta"],
  "Choose or paste a folder path…": ["选择或粘贴文件夹路径……", "Velg eller lim inn en mappesti …", "Choisissez ou collez le chemin d'un dossier…", "Elige o pega una ruta de carpeta…", "フォルダパスを選択または貼り付け…", "اختر أو الصق مسار المجلد…", "Ordnerpfad auswählen oder einfügen…", "Escolha ou cole um caminho de pasta…"],
  "Choose location": ["选择位置", "Velg plassering", "Choisir l'emplacement", "Elegir ubicación", "場所を選択", "اختر الموقع", "Speicherort auswählen", "Escolher local"],
  "Session access": ["会话访问权限", "Økttilgang", "Accès de la session", "Acceso de sesión", "セッションアクセス", "وصول الجلسة", "Sitzungszugriff", "Acesso à sessão"],
  "Search connectors…": ["搜索连接器……", "Søk i koblinger …", "Rechercher des connecteurs…", "Buscar conectores…", "コネクタを検索…", "البحث في الموصلات…", "Konnektoren suchen…", "Pesquisar conectores…"],
  "Add a channel": ["添加频道", "Legg til en kanal", "Ajouter un canal", "Añadir un canal", "チャンネルを追加", "إضافة قناة", "Kanal hinzufügen", "Adicionar um canal"],
  "Stop listening": ["停止监听", "Slutt å lytte", "Arrêter l'écoute", "Dejar de escuchar", "リスニングを停止", "إيقاف الاستماع", "Zuhören beenden", "Parar de ouvir"],
  "Back to sources": ["返回来源", "Tilbake til kilder", "Retour aux sources", "Volver a fuentes", "ソースに戻る", "العودة إلى المصادر", "Zurück zu Quellen", "Voltar para fontes"],
  // ── settings ──
  "How MimiWork looks and behaves on this machine.": ["MimiWork 在这台电脑上的外观与行为。", "Hvordan MimiWork ser ut og oppfører seg på denne maskinen.", "L'apparence et le comportement de MimiWork sur cet ordinateur.", "Cómo se ve y se comporta MimiWork en esta máquina.", "このマシンでのMimiWorkの外観と動作。", "كيف يبدو ويتصرف MimiWork على هذا الجهاز.", "Wie MimiWork auf diesem Computer aussieht und sich verhält.", "Como o MimiWork se parece e se comporta nesta máquina."],
  "Theme": ["主题", "Tema", "Thème", "Tema", "テーマ", "السمة", "Design", "Tema"],
  "Appearance": ["外观", "Utseende", "Apparence", "Apariencia", "外観", "المظهر", "Darstellung", "Aparência"],
  "System": ["跟随系统", "System", "Système", "Sistema", "システム", "النظام", "System", "Sistema"],
  "Light": ["浅色", "Lys", "Clair", "Claro", "ライト", "فاتح", "Hell", "Claro"],
  "Dark": ["深色", "Mørk", "Sombre", "Oscuro", "ダーク", "داكن", "Dunkel", "Escuro"],
  "Auto follows your Mac’s appearance.": ["自动模式会跟随 Mac 的外观设置。", "Auto følger utseendet på Mac-en.", "Le mode Auto suit l'apparence de votre Mac.", "Automático sigue la apariencia de tu Mac.", "自動はMacの外観に従います。", "تلقائي يتبع مظهر جهاز Mac الخاص بك.", "Automatisch folgt der Darstellung deines Macs.", "Automático segue a aparência do seu Mac."],
  "Always-on": ["常驻设置", "Alltid på", "Toujours actif", "Siempre activo", "常時オン", "دائم التشغيل", "Immer an", "Sempre ativo"],
  "Open at login": ["登录时打开", "Åpne ved innlogging", "Ouvrir à la connexion", "Abrir al iniciar sesión", "ログイン時に開く", "فتح عند تسجيل الدخول", "Beim Anmelden öffnen", "Abrir ao iniciar sessão"],
  "Launch MimiWork automatically when you sign in.": ["登录时自动启动 MimiWork。", "Start MimiWork automatisk når du logger inn.", "Lancer MimiWork automatiquement à votre connexion.", "Inicia MimiWork automáticamente cuando inicies sesión.", "サインイン時にMimiWorkを自動的に起動します。", "تشغيل MimiWork تلقائيًا عند تسجيل الدخول.", "MimiWork automatisch starten, wenn du dich anmeldest.", "Iniciar o MimiWork automaticamente quando você iniciar sessão."],
  "Keep this system awake": ["保持系统唤醒", "Hold systemet våkent", "Maintenir le système actif", "Mantener este sistema despierto", "このシステムを起動したままにする", "إبقاء هذا النظام مستيقظًا", "Dieses System wach halten", "Manter este sistema acordado"],
  "Prevent idle sleep so scheduled tasks fire on time.": ["防止系统闲置休眠,确保计划任务准时运行。", "Hindre hvilemodus slik at planlagte oppgaver kjører i tide.", "Empêcher la mise en veille afin que les tâches planifiées s'exécutent à l'heure.", "Evita el sueño inactivo para que las tareas programadas se ejecuten a tiempo.", "アイドルスリープを防ぎ、スケジュールされたタスクが時間通りに実行されるようにします。", "منع السكون الخامل حتى يتم تنفيذ المهام المجدولة في الوقت المحدد.", "Verhindert den Ruhezustand, damit geplante Aufgaben pünktlich ausgeführt werden.", "Evita o sono ocioso para que as tarefas agendadas sejam executadas no horário."],
  "Floating Mimi": ["悬浮 Mimi", "Flytende Mimi", "Mimi flottante", "Mimi flotante", "フローティングMimi", "Mimi عائم", "Schwebendes Mimi", "Mimi flutuante"],
  "Trusted workspaces": ["受信任的工作区", "Klarerte arbeidsområder", "Espaces de travail approuvés", "Espacios de trabajo de confianza", "信頼済みワークスペース", "مساحات العمل الموثوقة", "Vertrauenswürdige Arbeitsbereiche", "Espaços de trabalho confiáveis"],
  "No workspaces are trusted.": ["没有受信任的工作区。", "Ingen arbeidsområder er klarert.", "Aucun espace de travail n'est approuvé.", "No hay espacios de trabajo de confianza.", "信頼済みワークスペースはありません。", "لا توجد مساحات عمل موثوقة.", "Keine Arbeitsbereiche sind vertrauenswürdig.", "Nenhum espaço de trabalho é confiável."],
  "Token savings": ["令牌节省", "Tokenbesparelser", "Économie de jetons", "Ahorro de tokens", "トークン節約", "توفير الرموز", "Token-Ersparnis", "Economia de tokens"],
  "PDFs on models without native PDF support": ["不原生支持 PDF 的模型如何处理 PDF", "PDF-er på modeller uten innebygd PDF-støtte", "PDF avec les modèles sans prise en charge native", "PDFs en modelos sin soporte nativo de PDF", "ネイティブPDFサポートのないモデルでのPDF", "ملفات PDF على النماذج دون دعم PDF أصلي", "PDFs bei Modellen ohne native PDF-Unterstützung", "PDFs em modelos sem suporte nativo a PDF"],
  "PDF fallback": ["PDF 后备处理", "PDF-reserveløsning", "Solution de repli PDF", "Respaldo de PDF", "PDFフォールバック", "الاحتياطي لـ PDF", "PDF-Fallback", "Fallback de PDF"],
  "Extract text": ["提取文本", "Trekk ut tekst", "Extraire le texte", "Extraer texto", "テキストを抽出", "استخراج النص", "Text extrahieren", "Extrair texto"],
  "Render pages": ["渲染页面", "Gjengi sider", "Rendre les pages", "Renderizar páginas", "ページをレンダリング", "عرض الصفحات", "Seiten rendern", "Renderizar páginas"],
  "Max pages": ["最大页数", "Maks sider", "Nombre maximal de pages", "Páginas máx.", "最大ページ数", "الحد الأقصى للصفحات", "Max. Seiten", "Máx. de páginas"],
  "Max size": ["最大大小", "Maks størrelse", "Taille maximale", "Tamaño máx.", "最大サイズ", "الحد الأقصى للحجم", "Max. Größe", "Tamanho máx."],
  "Context compaction": ["上下文压缩", "Kontekstkomprimering", "Compactage du contexte", "Compactación de contexto", "コンテキスト圧縮", "ضغط السياق", "Kontextkomprimierung", "Compactação de contexto"],
  "Compact at": ["压缩阈值", "Komprimer ved", "Compacter à", "Compactar en", "圧縮するタイミング", "الضغط عند", "Komprimieren bei", "Compactar em"],
  "or at": ["或达到", "eller ved", "ou à", "o en", "または", "أو عند", "oder bei", "ou em"],
  "tokens, whichever is smaller": ["个令牌,以较小者为准", "tokener, avhengig av hva som er minst", "jetons, selon la valeur la plus basse", "tokens, lo que sea menor", "トークンのうち小さい方", "رمزًا، أيهما أصغر", "Tokens, je nachdem, was kleiner ist", "tokens, o que for menor"],
  "Summarizer model": ["摘要模型", "Oppsummeringsmodell", "Modèle de résumé", "Modelo de resumen", "要約モデル", "نموذج الملخص", "Zusammenfassungsmodell", "Modelo de resumo"],
  "Session’s own model (default)": ["会话使用的模型(默认)", "Øktens egen modell (standard)", "Modèle de la session (par défaut)", "Modelo propio de la sesión (predeterminado)", "セッション独自のモデル（デフォルト）", "نموذج الجلسة الخاص (الافتراضي)", "Eigenes Modell der Sitzung (Standard)", "Modelo próprio da sessão (padrão)"],
  "Composer": ["输入框", "Meldingsfelt", "Zone de message", "Compositor", "コンポーザー", "المنشئ", "Composer", "Compositor"],
  "Show the context window bar": ["显示上下文窗口栏", "Vis kontekstvindu-linjen", "Afficher la barre de fenêtre de contexte", "Mostrar la barra de ventana de contexto", "コンテキストウィンドウバーを表示", "إظهار شريط نافذة السياق", "Kontextfensterleiste anzeigen", "Mostrar a barra da janela de contexto"],
  "Sidebar": ["侧边栏", "Sidefelt", "Barre latérale", "Barra lateral", "サイドバー", "الشريط الجانبي", "Seitenleiste", "Barra lateral"],
  "Conversations shown per assistant": ["每位助手显示的对话数", "Samtaler som vises per assistent", "Conversations affichées par assistant", "Conversaciones mostradas por asistente", "アシスタントごとに表示する会話数", "المحادثات المعروضة لكل مساعد", "Konversationen pro Assistent", "Conversas mostradas por assistente"],
  "Pick a folder": ["选择文件夹", "Velg en mappe", "Choisir un dossier", "Elegir una carpeta", "フォルダを選択", "اختيار مجلد", "Ordner auswählen", "Escolher uma pasta"],
  "Providers and the models offered in the composer's picker. Keys are stored only on this computer.": ["提供商及输入框模型选择器中显示的模型。密钥仅存储在这台电脑上。", "Tilbydere og modellene som vises i meldingsfeltets modellvelger. Nøkler lagres bare på denne maskinen.", "Fournisseurs et modèles proposés dans le sélecteur de la zone de message. Les clés sont stockées uniquement sur cet ordinateur.", "Proveedores y modelos ofrecidos en el selector del compositor. Las claves se almacenan solo en este equipo.", "コンポーザーのピッカーで提供されるプロバイダーとモデル。キーはこのコンピュータにのみ保存されます。", "المزودون والنماذج المتاحة في منتقي المنشئ. تُخزَّن المفاتيح على هذا الكمبيوتر فقط.", "Anbieter und Modelle im Composer-Auswahlfeld. Schlüssel werden nur auf diesem Computer gespeichert.", "Provedores e modelos oferecidos no seletor do compositor. As chaves são armazenadas apenas neste computador."],
  "Voice Input setup is available in the MimiWork desktop app.": ["语音输入设置仅在 MimiWork 桌面应用中提供。", "Oppsett av taleinndata er tilgjengelig i MimiWork-skrivebordsappen.", "La configuration de la saisie vocale est disponible dans l'application de bureau MimiWork.", "La configuración de entrada por voz está disponible en la aplicación de escritorio MimiWork.", "音声入力の設定はMimiWorkデスクトップアプリで利用できます。", "إعداد الإدخال الصوتي متاح في تطبيق سطح المكتب MimiWork.", "Die Einrichtung der Spracheingabe ist in der MimiWork-Desktop-App verfügbar.", "A configuração de entrada por voz está disponível no aplicativo de desktop MimiWork."],
  "Private by design.": ["隐私优先设计。", "Privat som standard.", "Confidentiel par conception.", "Privado por diseño.", "設計上プライベート。", "خاص بالتصميم.", "Von Natur aus privat.", "Privado por design."],
  "Audio is held in memory only while you record and is transcribed locally.": ["音频仅在录音期间保存在内存中,并在本地转录。", "Lyd lagres bare i minnet mens du tar opp og transkriberes lokalt.", "L'audio n'est conservé en mémoire que pendant l'enregistrement et est transcrit localement.", "El audio se mantiene solo en memoria mientras grabas y se transcribe localmente.", "音声は録音中のみメモリに保持され、ローカルで文字起こしされます。", "يُحتفظ بالصوت في الذاكرة فقط أثناء التسجيل ويتم تفريغه محليًا.", "Audio wird nur während der Aufnahme im Speicher gehalten und lokal transkribiert.", "O áudio é mantido apenas em memória enquanto grava e é transcrito localmente."],
  "This device": ["此设备", "Denne enheten", "Cet appareil", "Este dispositivo", "このデバイス", "هذا الجهاز", "Dieses Gerät", "Este dispositivo"],
  "Processor": ["处理器", "Prosessor", "Processeur", "Procesador", "プロセッサ", "المعالج", "Prozessor", "Processador"],
  "Verified": ["已验证", "Verifisert", "Vérifié", "Verificado", "検証済み", "تم التحقق", "Verifiziert", "Verificado"],
  "Repair": ["修复", "Reparer", "Réparer", "Reparar", "修復", "إصلاح", "Reparieren", "Reparar"],
  "Verifying…": ["验证中……", "Verifiserer …", "Vérification…", "Verificando…", "検証中…", "جارٍ التحقق…", "Wird verifiziert…", "Verificando…"],
  "Download model": ["下载模型", "Last ned modell", "Télécharger le modèle", "Descargar modelo", "モデルをダウンロード", "تنزيل النموذج", "Modell herunterladen", "Baixar modelo"],
  "Microphone test": ["麦克风测试", "Mikrofontest", "Test du microphone", "Prueba de micrófono", "マイクテスト", "اختبار الميكروفون", "Mikrofontest", "Teste de microfone"],
  // ── automations, files and activity ──
  "Recurring tasks MimiWork runs on a schedule.": ["MimiWork 按计划运行的重复任务。", "Gjentakende oppgaver MimiWork kjører etter en tidsplan.", "Tâches récurrentes exécutées par MimiWork selon un calendrier.", "Tareas recurrentes que MimiWork ejecuta según un horario.", "MimiWorkがスケジュールに従って実行する定期タスク。", "مهام متكررة ينفذها MimiWork وفقًا لجدول زمني.", "Wiederkehrende Aufgaben, die MimiWork nach einem Zeitplan ausführt.", "Tarefas recorrentes que o MimiWork executa em um agendamento."],
  "Model": ["模型", "Modell", "Modèle", "Modelo", "モデル", "النموذج", "Modell", "Modelo"],
  "Permission": ["权限", "Tillatelse", "Autorisation", "Permiso", "権限", "الإذن", "Berechtigung", "Permissão"],
  "At": ["时间", "Kl.", "À", "En", "時刻", "عند", "Um", "Em"],
  "Repeat": ["重复", "Gjenta", "Répéter", "Repetir", "繰り返し", "تكرار", "Wiederholen", "Repetir"],
  "Every day": ["每天", "Hver dag", "Tous les jours", "Cada día", "毎日", "كل يوم", "Jeden Tag", "Todos os dias"],
  "Weekdays": ["工作日", "Ukedager", "Jours de semaine", "Días laborables", "平日", "أيام الأسبوع", "Wochentage", "Dias úteis"],
  "Weekends": ["周末", "Helger", "Week-ends", "Fines de semana", "週末", "عطلات نهاية الأسبوع", "Wochenenden", "Fins de semana"],
  "Works in:": ["工作位置:", "Arbeider i:", "Travaille dans :", "Funciona en:", "対応環境:", "يعمل في:", "Funktioniert in:", "Funciona em:"],
  "Title": ["标题", "Tittel", "Titre", "Título", "タイトル", "العنوان", "Titel", "Título"],
  "Allowed without asking": ["无需询问即可执行", "Tillatt uten å spørre", "Autorisé sans demander", "Permitido sin preguntar", "確認なしで許可", "مسموح دون سؤال", "Ohne Nachfragen erlaubt", "Permitido sem perguntar"],
  "Runs": ["运行记录", "Kjøringer", "Exécutions", "Ejecuciones", "実行", "عمليات التشغيل", "Ausführungen", "Execuções"],
  "No runs yet.": ["尚无运行记录。", "Ingen kjøringer ennå.", "Aucune exécution pour l'instant.", "Aún no hay ejecuciones.", "まだ実行はありません。", "لا توجد عمليات تشغيل بعد.", "Noch keine Ausführungen.", "Ainda não há execuções."],
  "new": ["新", "ny", "nouveau", "nuevo", "新規", "جديد", "Neu", "novo"],
  "Delete automation": ["删除自动化", "Slett automatisering", "Supprimer l'automatisation", "Eliminar automatización", "自動化を削除", "حذف الأتمتة", "Automatisierung löschen", "Excluir automação"],
  "No audit events yet.": ["尚无活动记录。", "Ingen aktivitetshendelser ennå.", "Aucun événement d'activité pour l'instant.", "Aún no hay eventos de auditoría.", "監査イベントはまだありません。", "لا توجد أحداث تدقيق بعد.", "Noch keine Audit-Ereignisse.", "Ainda não há eventos de auditoria."],
  "Credits": ["积分", "Kreditter", "Crédits", "Créditos", "クレジット", "الاعتمادات", "Guthaben", "Créditos"],
  "filter…": ["筛选……", "filtrer …", "filtrer…", "filtrar…", "フィルタ…", "تصفية…", "filtern…", "filtrar…"],
  "No entries.": ["没有条目。", "Ingen oppføringer.", "Aucune entrée.", "Sin entradas.", "エントリがありません。", "لا توجد إدخالات.", "Keine Einträge.", "Sem entradas."],
  "file truncated for review": ["文件已截断以供审阅", "filen er forkortet for gjennomgang", "fichier tronqué pour la révision", "archivo truncado para revisión", "レビュー用に切り詰められたファイル", "تم اقتطاع الملف للمراجعة", "Datei für Überprüfung gekürzt", "arquivo truncado para revisão"],
  "No versions yet — save an edit to start history.": ["尚无版本——保存一次编辑即可开始记录历史。", "Ingen versjoner ennå — lagre en endring for å starte historikken.", "Aucune version pour l'instant — enregistrez une modification pour commencer l'historique.", "Aún no hay versiones: guarda una edición para iniciar el historial.", "まだバージョンがありません。編集を保存して履歴を開始してください。", "لا توجد إصدارات بعد — احفظ تعديلاً لبدء السجل.", "Noch keine Versionen – speichern Sie eine Bearbeitung, um den Verlauf zu starten.", "Ainda não há versões — guarde uma edição para iniciar o histórico."],
  // ── home and first session ──
  "Dismiss": ["关闭", "Avvis", "Fermer", "Descartar", "閉じる", "إغلاق", "Verwerfen", "Dispensar"],
  "Show sidebar (⌘B)": ["显示侧边栏 (⌘B)", "Vis sidefelt (⌘B)", "Afficher la barre latérale (⌘B)", "Mostrar barra lateral (⌘B)", "サイドバーを表示 (⌘B)", "إظهار الشريط الجانبي (⌘B)", "Seitenleiste anzeigen (⌘B)", "Mostrar barra lateral (⌘B)"],
  "Show files this conversation produced": ["显示此对话生成的文件", "Vis filer denne samtalen har laget", "Afficher les fichiers produits par cette conversation", "Mostrar archivos producidos por esta conversación", "この会話で生成されたファイルを表示", "إظهار الملفات التي أنتجها هذا المحادثة", "Von dieser Konversation erstellte Dateien anzeigen", "Mostrar arquivos produzidos por esta conversa"],
  "Work in a folder": ["在文件夹中工作", "Arbeid i en mappe", "Travailler dans un dossier", "Trabajar en una carpeta", "フォルダで作業", "العمل في مجلد", "In einem Ordner arbeiten", "Trabalhar numa pasta"],
  "I'll read what's there and produce what you need": ["我会读取其中的内容并生成你需要的成果", "Jeg leser innholdet og lager det du trenger", "Je lirai son contenu et produirai ce dont vous avez besoin", "Leeré lo que hay y produciré lo que necesites", "そこにあるものを読んで、必要なものを生成します", "سأقرأ ما هناك وأنتج ما تحتاجه", "Ich lese, was dort ist, und erstelle, was Sie brauchen", "Vou ler o que está lá e produzir o que precisas"],
  "Pick a folder →": ["选择文件夹 →", "Velg en mappe →", "Choisir un dossier →", "Elegir una carpeta →", "フォルダを選択 →", "اختيار مجلد ←", "Ordner auswählen →", "Escolher uma pasta →"],
  "Build a deck from my Canva designs": ["根据我的 Canva 设计制作演示文稿", "Lag en presentasjon fra Canva-designene mine", "Créer une présentation à partir de mes designs Canva", "Crear una presentación a partir de mis diseños de Canva", "Canvaのデザインからデッキを作成", "إنشاء عرض تقديمي من تصاميم Canva الخاصة بي", "Deck aus meinen Canva-Designs erstellen", "Criar uma apresentação a partir dos meus designs do Canva"],
  "Package your style guidelines into a skill": ["将风格指南打包为技能", "Pakk stilretningslinjene dine som en ferdighet", "Transformer vos règles de style en compétence", "Empaquetar tus guías de estilo en una habilidad", "スタイルガイドをスキルにパッケージ化", "تغليف إرشادات الأسلوب الخاصة بك في مهارة", "Verpacken Sie Ihre Styleguides in eine Fähigkeit", "Empacotar as tuas diretrizes de estilo numa habilidade"],
  "Start →": ["开始 →", "Start →", "Commencer →", "Iniciar →", "開始 →", "بدء ←", "Start →", "Iniciar →"],
  // ── accounts, models and skills ──
  "QualiTaTi account": ["QualiTaTi 账户", "QualiTaTi-konto", "Compte QualiTaTi", "Cuenta de QualiTaTi", "QualiTaTiアカウント", "حساب QualiTaTi", "QualiTaTi-Konto", "Conta QualiTaTi"],
  "Your QualiTaTi work is available here.": ["你在 QualiTaTi 中的工作可在此访问。", "QualiTaTi-arbeidet ditt er tilgjengelig her.", "Votre travail QualiTaTi est disponible ici.", "Tu trabajo de QualiTaTi está disponible aquí.", "QualiTaTiの作業はこちらで利用できます。", "عملك في QualiTaTi متاح هنا.", "Ihre QualiTaTi-Arbeit ist hier verfügbar.", "O teu trabalho QualiTaTi está disponível aqui."],
  "Model region": ["模型区域", "Modellregion", "Région du modèle", "Región del modelo", "モデルリージョン", "منطقة النموذج", "Modellregion", "Região do modelo"],
  "MFA code": ["多重验证代码", "MFA-kode", "Code MFA", "Código MFA", "MFAコード", "رمز MFA", "MFA-Code", "Código MFA"],
  "Account": ["账户", "Konto", "Compte", "Cuenta", "アカウント", "الحساب", "Konto", "Conta"],
  "Username": ["用户名", "Brukernavn", "Nom d'utilisateur", "Nombre de usuario", "ユーザー名", "اسم المستخدم", "Benutzername", "Nome de utilizador"],
  "Password": ["密码", "Passord", "Mot de passe", "Contraseña", "パスワード", "كلمة المرور", "Passwort", "Palavra-passe"],
  "Email": ["电子邮箱", "E-post", "E-mail", "Correo electrónico", "メール", "البريد الإلكتروني", "E-Mail", "Email"],
  "Confirm password": ["确认密码", "Bekreft passord", "Confirmer le mot de passe", "Confirmar contraseña", "パスワードを確認", "تأكيد كلمة المرور", "Passwort bestätigen", "Confirmar palavra-passe"],
  "Invite code (optional)": ["邀请码(可选)", "Invitasjonskode (valgfritt)", "Code d'invitation (facultatif)", "Código de invitación (opcional)", "招待コード（任意）", "رمز الدعوة (اختياري)", "Einladungscode (optional)", "Código de convite (opcional)"],
  "Not set up": ["未设置", "Ikke konfigurert", "Non configuré", "No configurado", "未設定", "غير مُعد", "Nicht eingerichtet", "Não configurado"],
  "Copy command": ["复制命令", "Kopier kommando", "Copier la commande", "Copiar comando", "コマンドをコピー", "نسخ الأمر", "Befehl kopieren", "Copiar comando"],
  "Runs one read-only check, then saves.": ["运行一次只读检查,然后保存。", "Kjører én skrivebeskyttet kontroll og lagrer deretter.", "Effectue une vérification en lecture seule, puis enregistre.", "Ejecuta una verificación de solo lectura y luego guarda.", "読み取り専用チェックを1回実行してから保存します。", "ينفذ فحصًا للقراءة فقط ثم يحفظ.", "Führt eine schreibgeschützte Prüfung aus und speichert dann.", "Executa uma verificação só de leitura e depois guarda."],
  "Test & save": ["测试并保存", "Test og lagre", "Tester et enregistrer", "Probar y guardar", "テストして保存", "اختبار وحفظ", "Testen und speichern", "Testar e guardar"],
  "Included models": ["包含的模型", "Inkluderte modeller", "Modèles inclus", "Modelos incluidos", "含まれるモデル", "النماذج المضمنة", "Enthaltene Modelle", "Modelos incluídos"],
  "In the composer's picker": ["在输入框的模型选择器中", "I modellvelgeren i meldingsfeltet", "Dans le sélecteur de la zone de message", "En el selector del compositor", "コンポーザーのピッカー内", "في منتقي الملحن", "Im Auswahlfeld des Komponisten", "No seletor do compositor"],
  "Enable this server": ["启用此服务器", "Aktiver denne serveren", "Activer ce serveur", "Habilitar este servidor", "このサーバーを有効にする", "تمكين هذا الخادم", "Diesen Server aktivieren", "Ativar este servidor"],
  "waiting for browser…": ["等待浏览器……", "venter på nettleseren …", "en attente du navigateur…", "esperando al navegador…", "ブラウザを待っています…", "في انتظار المتصفح…", "Warten auf Browser…", "a aguardar pelo navegador…"],
  "No tools.": ["没有工具。", "Ingen verktøy.", "Aucun outil.", "Sin herramientas.", "ツールがありません。", "لا توجد أدوات.", "Keine Werkzeuge.", "Sem ferramentas."],
  "Paste server JSON (name → config):": ["粘贴服务器 JSON(名称 → 配置):", "Lim inn server-JSON (navn → konfigurasjon):", "Collez le JSON du serveur (nom → configuration) :", "Pegar JSON del servidor (nombre → configuración):", "サーバーJSONを貼り付け（名前 → 設定）：", "الصق JSON الخادم (الاسم ← الإعداد):", "Server-JSON einfügen (Name → Konfiguration):", "Colar JSON do servidor (nome → configuração):"],
  "Tools exposed to MimiWork": ["向 MimiWork 提供的工具", "Verktøy som er tilgjengelige for MimiWork", "Outils mis à disposition de MimiWork", "Herramientas expuestas a MimiWork", "MimiWorkに公開されたツール", "الأدوات المكشوفة لـ MimiWork", "Für MimiWork freigegebene Werkzeuge", "Ferramentas expostas ao MimiWork"],
  "or connect manually:": ["或手动连接:", "eller koble til manuelt:", "ou connecter manuellement :", "o conectar manualmente:", "または手動で接続：", "أو الاتصال يدويًا:", "Oder manuell verbinden:", "ou ligar manualmente:"],
  "Write it myself": ["自己编写", "Skriv den selv", "L'écrire moi-même", "Escríbelo yo mismo", "自分で書く", "اكتبه بنفسي", "Selbst schreiben", "Escrever eu mesmo"],
  "Import a file": ["导入文件", "Importer en fil", "Importer un fichier", "Importar un archivo", "ファイルをインポート", "استيراد ملف", "Datei importieren", "Importar um ficheiro"],
  "Create with MimiWork": ["使用 MimiWork 创建", "Lag med MimiWork", "Créer avec MimiWork", "Crear con MimiWork", "MimiWorkで作成", "إنشاء باستخدام MimiWork", "Mit MimiWork erstellen", "Criar com MimiWork"],
  "Import from Claude Code": ["从 Claude Code 导入", "Importer fra Claude Code", "Importer depuis Claude Code", "Importar desde Claude Code", "Claude Codeからインポート", "استيراد من Claude Code", "Von Claude Code importieren", "Importar do Claude Code"],
  "Browse the skill store": ["浏览技能商店", "Bla i ferdighetsbutikken", "Parcourir la boutique de compétences", "Explorar la tienda de habilidades", "スキルストアを閲覧", "تصفح متجر المهارات", "Skill-Store durchsuchen", "Explorar a loja de habilidades"],
  "Upload a skill archive": ["上传技能压缩包", "Last opp et ferdighetsarkiv", "Téléverser une archive de compétence", "Subir un archivo de habilidades", "スキルアーカイブをアップロード", "رفع أرشيف المهارات", "Skill-Archiv hochladen", "Carregar um arquivo de habilidades"],
  "Skill store": ["技能商店", "Ferdighetsbutikk", "Boutique de compétences", "Tienda de habilidades", "スキルストア", "متجر المهارات", "Skill-Store", "Loja de habilidades"],
  "Search skills… (e.g. seo audit, meeting notes, resume)": ["搜索技能……(例如 SEO 审计、会议记录、简历)", "Søk etter ferdigheter … (f.eks. SEO-revisjon, møtereferat, CV)", "Rechercher des compétences… (p. ex. audit SEO, notes de réunion, CV)", "Buscar habilidades… (p. ej. auditoría SEO, notas de reuniones, currículum)", "スキルを検索…（例: SEO監査、会議メモ、履歴書）", "ابحث عن المهارات… (مثل: تدقيق SEO، ملاحظات الاجتماع، السيرة الذاتية)", "Skills suchen… (z. B. SEO-Audit, Besprechungsnotizen, Lebenslauf)", "Pesquisar habilidades… (ex.: auditoria de SEO, notas de reunião, currículo)"],
  "Close preview": ["关闭预览", "Lukk forhåndsvisning", "Fermer l'aperçu", "Cerrar vista previa", "プレビューを閉じる", "إغلاق المعاينة", "Vorschau schließen", "Fechar pré-visualização"],
  "Wants to use:": ["需要使用:", "Ønsker å bruke:", "Souhaite utiliser :", "Quiere usar:", "使用しようとしています:", "يريد استخدام:", "Möchte verwenden:", "Quer usar:"],
  "Review before installing": ["安装前审阅", "Se gjennom før installasjon", "Vérifier avant l'installation", "Revisar antes de instalar", "インストール前に確認", "مراجعة قبل التثبيت", "Vor der Installation überprüfen", "Rever antes de instalar"],
  "One line the worker uses to decide when this applies": ["用一句话说明何时使用此技能", "Én linje medarbeideren bruker for å avgjøre når dette gjelder", "Une phrase permettant au coéquipier de décider quand l'utiliser", "Una línea que el trabajador usa para decidir cuándo aplica esto", "ワーカーがこれが適用されるタイミングを判断するための一文", "سطر واحد يستخدمه العامل لتحديد متى ينطبق هذا", "Ein Satz, den der Worker verwendet, um zu entscheiden, wann dies zutrifft", "Uma linha que o trabalhador usa para decidir quando isto se aplica"],
  "Show folder": ["显示文件夹", "Vis mappe", "Afficher le dossier", "Mostrar carpeta", "フォルダを表示", "إظهار المجلد", "Ordner anzeigen", "Mostrar pasta"],
  // ── memory, personas and projects ──
  "Remember new things about you": ["记住关于你的新信息", "Husk nye ting om deg", "Mémoriser de nouvelles informations à votre sujet", "Recordar cosas nuevas sobre ti", "あなたについての新しいことを覚える", "تذكر أشياء جديدة عنك", "Neue Dinge über dich merken", "Lembrar coisas novas sobre ti"],
  "Remember new things about me": ["记住关于我的新信息", "Husk nye ting om meg", "Mémoriser de nouvelles informations à mon sujet", "Recordar cosas nuevas sobre mí", "私についての新しいことを覚える", "تذكر أشياء جديدة عني", "Neue Dinge über mich merken", "Lembrar coisas novas sobre mim"],
  "What I've learned about you": ["我对你的了解", "Det jeg har lært om deg", "Ce que j'ai appris à votre sujet", "Lo que he aprendido sobre ti", "あなたについて学んだこと", "ما تعلمته عنك", "Was ich über dich gelernt habe", "O que aprendi sobre ti"],
  "Your instructions": ["你的指令", "Instruksjonene dine", "Vos instructions", "Tus instrucciones", "あなたの指示", "تعليماتك", "Deine Anweisungen", "As tuas instruções"],
  "Fix this": ["修正此项", "Rett dette", "Corriger ceci", "Arreglar esto", "これを修正", "إصلاح هذا", "Dies beheben", "Corrigir isto"],
  "Delete this memory": ["删除此记忆", "Slett dette minnet", "Supprimer ce souvenir", "Eliminar este recuerdo", "この記憶を削除", "حذف هذه الذاكرة", "Diese Erinnerung löschen", "Apagar esta memória"],
  "Default for new sessions": ["新会话的默认角色", "Standard for nye økter", "Par défaut pour les nouvelles sessions", "Predeterminado para nuevas sesiones", "新しいセッションのデフォルト", "الافتراضي للجلسات الجديدة", "Standard für neue Sitzungen", "Padrão para novas sessões"],
  "Delete this persona": ["删除此角色", "Slett denne personaen", "Supprimer ce persona", "Eliminar esta persona", "このペルソナを削除", "حذف هذا الشخص", "Diese Persona löschen", "Apagar esta persona"],
  "Add personas": ["添加角色", "Legg til personaer", "Ajouter des personas", "Añadir personas", "ペルソナを追加", "إضافة شخصيات", "Personas hinzufügen", "Adicionar personas"],
  "GitHub URL": ["GitHub 网址", "GitHub-URL", "URL GitHub", "URL de GitHub", "GitHub URL", "رابط GitHub", "GitHub-URL", "URL do GitHub"],
  "Local directory": ["本地目录", "Lokal mappe", "Répertoire local", "Directorio local", "ローカルディレクトリ", "المجلد المحلي", "Lokales Verzeichnis", "Diretório local"],
  "Change emoji": ["更改表情符号", "Endre emoji", "Changer l'emoji", "Cambiar emoji", "絵文字を変更", "تغيير الرمز التعبيري", "Emoji ändern", "Alterar emoji"],
  "Project name": ["项目名称", "Prosjektnavn", "Nom du projet", "Nombre del proyecto", "プロジェクト名", "اسم المشروع", "Projektname", "Nome do projeto"],
  "Open in your file manager": ["在文件管理器中打开", "Åpne i filbehandleren", "Ouvrir dans le gestionnaire de fichiers", "Abrir en tu administrador de archivos", "ファイルマネージャーで開く", "فتح في مدير الملفات", "Im Dateimanager öffnen", "Abrir no gestor de ficheiros"],
  "What Mimi remembers about this project": ["Mimi 对此项目的记忆", "Det Mimi husker om dette prosjektet", "Ce que Mimi retient de ce projet", "Lo que Mimi recuerda sobre este proyecto", "Mimiがこのプロジェクトについて覚えていること", "ما تتذكره Mimi عن هذا المشروع", "Was Mimi über dieses Projekt merkt", "O que a Mimi lembra sobre este projeto"],
  "Edit memory": ["编辑记忆", "Rediger minne", "Modifier le souvenir", "Editar recuerdo", "記憶を編集", "تعديل الذاكرة", "Erinnerung bearbeiten", "Editar memória"],
  "Forget": ["忘记", "Glem", "Oublier", "Olvidar", "忘れる", "نسيان", "Vergessen", "Esquecer"],
  "Forget memory": ["删除记忆", "Glem minnet", "Oublier le souvenir", "Olvidar recuerdo", "記憶を忘れる", "نسيان الذاكرة", "Erinnerung vergessen", "Esquecer memória"],
  "Add a fact about this project…": ["添加关于此项目的信息……", "Legg til et faktum om dette prosjektet …", "Ajouter une information sur ce projet…", "Añadir un dato sobre este proyecto…", "このプロジェクトについての事実を追加…", "إضافة حقيقة عن هذا المشروع…", "Eine Tatsache über dieses Projekt hinzufügen…", "Adicionar um facto sobre este projeto…"],
  "Conversations": ["对话", "Samtaler", "Conversations", "Conversaciones", "会話", "المحادثات", "Unterhaltungen", "Conversas"],
  // ── connectors ──
  "MCP servers": ["MCP 服务器", "MCP-servere", "Serveurs MCP", "Servidores MCP", "MCPサーバー", "خوادم MCP", "MCP-Server", "Servidores MCP"],
  "Available": ["可用", "Tilgjengelig", "Disponibles", "Disponible", "利用可能", "متاح", "Verfügbar", "Disponível"],
  "Nothing matches.": ["没有匹配项。", "Ingen treff.", "Aucun résultat.", "Nada coincide.", "一致するものはありません。", "لا شيء يطابق.", "Nichts passt.", "Nada corresponde."],
  "Not connected": ["未连接", "Ikke tilkoblet", "Non connecté", "No conectado", "未接続", "غير متصل", "Nicht verbunden", "Não ligado"],
  "Accounts": ["账户", "Kontoer", "Comptes", "Cuentas", "アカウント", "الحسابات", "Konten", "Contas"],
  "Portals": ["门户", "Portaler", "Portails", "Portales", "ポータル", "البوابات", "Portale", "Portais"],
  "Default": ["默认", "Standard", "Par défaut", "Predeterminado", "デフォルト", "الافتراضي", "Standard", "Padrão"],
  "Sandbox": ["沙盒", "Sandkasse", "Bac à sable", "Sandbox", "サンドボックス", "صندوق الحماية", "Sandbox", "Sandbox"],
  "private app": ["私有应用", "privat app", "application privée", "aplicación privada", "プライベートアプリ", "تطبيق خاص", "private App", "aplicação privada"],
  "Add an account": ["添加账户", "Legg til en konto", "Ajouter un compte", "Añadir una cuenta", "アカウントを追加", "إضافة حساب", "Konto hinzufügen", "Adicionar uma conta"],
  "Add a portal": ["添加门户", "Legg til en portal", "Ajouter un portail", "Añadir un portal", "ポータルを追加", "إضافة بوابة", "Portal hinzufügen", "Adicionar um portal"],
  "Add an installation": ["添加安装", "Legg til en installasjon", "Ajouter une installation", "Añadir una instalación", "インストールを追加", "إضافة تثبيت", "Installation hinzufügen", "Adicionar uma instalação"],
  "Add a workspace": ["添加工作区", "Legg til et arbeidsområde", "Ajouter un espace de travail", "Añadir un espacio de trabajo", "ワークスペースを追加", "إضافة مساحة عمل", "Arbeitsbereich hinzufügen", "Adicionar um espaço de trabalho"],
  "Disconnect this account": ["断开此账户", "Koble fra denne kontoen", "Déconnecter ce compte", "Desconectar esta cuenta", "このアカウントを切断", "قطع الاتصال بهذا الحساب", "Dieses Konto trennen", "Desligar esta conta"],
  "Disconnect this mailbox": ["断开此邮箱", "Koble fra denne postboksen", "Déconnecter cette boîte mail", "Desconectar este buzón", "このメールボックスを切断", "قطع الاتصال بهذا الصندوق البريدي", "Dieses Postfach trennen", "Desligar esta caixa de correio"],
  "Disconnect this portal": ["断开此门户", "Koble fra denne portalen", "Déconnecter ce portail", "Desconectar este portal", "このポータルを切断", "قطع الاتصال بهذه البوابة", "Dieses Portal trennen", "Desligar este portal"],
  "Never show agents": ["绝不向 AI 同事显示", "Vis aldri til medarbeidere", "Ne jamais montrer aux coéquipiers", "No mostrar nunca agentes", "エージェントを表示しない", "عدم إظهار الوكلاء أبدًا", "Agenten nie anzeigen", "Nunca mostrar agentes"],
  "Access & privacy": ["访问与隐私", "Tilgang og personvern", "Accès et confidentialité", "Acceso y privacidad", "アクセスとプライバシー", "الوصول والخصوصية", "Zugriff & Datenschutz", "Acesso e privacidade"],
  "Hidden fields": ["隐藏字段", "Skjulte felt", "Champs masqués", "Campos ocultos", "非表示フィールド", "الحقول المخفية", "Ausgeblendete Felder", "Campos ocultos"],
  "Property name, e.g. salary": ["属性名称,例如 salary", "Egenskapsnavn, f.eks. lønn", "Nom de propriété, p. ex. salaire", "Nombre de la propiedad, p. ej. salario", "プロパティ名（例：給与）", "اسم الخاصية، مثل: الراتب", "Eigenschaftsname, z. B. Gehalt", "Nome da propriedade, ex.: salário"],
  "People": ["人员", "Personer", "Personnes", "Personas", "人", "الأشخاص", "Personen", "Pessoas"],
  "Waiting": ["等待中", "Venter", "En attente", "Esperando", "待機中", "في الانتظار", "Warten", "A aguardar"],
  "Listening": ["监听中", "Lytter", "À l'écoute", "Escuchando", "聞き取り中", "الاستماع", "Zuhören", "A ouvir"],
  "Approvals": ["审批", "Godkjenninger", "Approbations", "Aprobaciones", "承認", "الموافقات", "Genehmigungen", "Aprovações"],
  "Type a name…": ["输入姓名……", "Skriv inn et navn …", "Saisissez un nom…", "Escribe un nombre…", "名前を入力…", "اكتب اسمًا…", "Namen eingeben…", "Escreva um nome…"],
  "no matches": ["无匹配项", "ingen treff", "aucun résultat", "sin coincidencias", "一致なし", "لا توجد نتائج", "keine Treffer", "sem correspondências"],
  "Pick from the workspace directory": ["从工作区目录中选择", "Velg fra arbeidsområdekatalogen", "Choisir dans l'annuaire de l'espace de travail", "Elegir del directorio del espacio de trabajo", "ワークスペースのディレクトリから選択", "اختيار من دليل مساحة العمل", "Aus dem Arbeitsbereichsverzeichnis wählen", "Escolher do diretório do espaço de trabalho"],
  "Set by the workspace installer.": ["由工作区安装者设置。", "Angitt av den som installerte arbeidsområdet.", "Défini par la personne ayant installé l'espace de travail.", "Establecido por el instalador del espacio de trabajo.", "ワークスペースのインストーラーによって設定されます。", "تم تعيينه بواسطة مثبت مساحة العمل.", "Vom Installationsprogramm des Arbeitsbereichs festgelegt.", "Definido pelo instalador do espaço de trabalho."],
  "Recent senders": ["最近的发送者", "Nylige avsendere", "Expéditeurs récents", "Remitentes recientes", "最近の送信者", "المرسلون الأخيرون", "Letzte Absender", "Remetentes recentes"],
  "Allowed to message": ["获准发送消息", "Har lov til å sende meldinger", "Autorisés à envoyer des messages", "Permitido para mensajear", "メッセージを許可", "مسموح بالمراسلة", "Darf Nachrichten senden", "Permitido enviar mensagens"],
  // ── remaining controls and secondary views ──
  "In the message box": ["在消息输入框中", "I meldingsfeltet", "Dans la zone de message", "En el cuadro de mensaje", "メッセージボックス内", "في مربع الرسالة", "Im Nachrichtenfeld", "Na caixa de mensagem"],
  "In MimiWork": ["在 MimiWork 中", "I MimiWork", "Dans MimiWork", "En MimiWork", "MimiWork内", "في MimiWork", "In MimiWork", "No MimiWork"],
  "Persona": ["角色", "Persona", "Persona", "Persona", "ペルソナ", "الشخصية", "Persona", "Persona"],
  "Enable this persona": ["启用此角色", "Aktiver denne personaen", "Activer ce persona", "Habilitar esta persona", "このペルソナを有効にする", "تفعيل هذه الشخصية", "Diese Persona aktivieren", "Ativar esta persona"],
  "About": ["关于", "Om", "À propos", "Acerca de", "概要", "حول", "Über", "Sobre"],
  "Built-in capabilities": ["内置能力", "Innebygde funksjoner", "Fonctionnalités intégrées", "Capacidades integradas", "組み込み機能", "القدرات المدمجة", "Integrierte Funktionen", "Capacidades incorporadas"],
  "Connections for full benefit": ["充分发挥作用所需的连接", "Tilkoblinger for full nytte", "Connexions pour en profiter pleinement", "Conexiones para máximo beneficio", "フル活用のための接続", "اتصالات للاستفادة الكاملة", "Verbindungen für vollen Nutzen", "Ligações para benefício total"],
  "core": ["核心", "kjerne", "essentiel", "núcleo", "コア", "الأساسية", "Kern", "núcleo"],
  "New sessions get by default": ["新会话的默认设置", "Nye økter får som standard", "Paramètres par défaut des nouvelles sessions", "Las nuevas sesiones obtienen por defecto", "新しいセッションはデフォルトで取得", "الجلسات الجديدة تحصل افتراضيًا على", "Neue Sitzungen erhalten standardmäßig", "Novas sessões obtêm por padrão"],
  "Default mode": ["默认模式", "Standardmodus", "Mode par défaut", "Modo predeterminado", "デフォルトモード", "الوضع الافتراضي", "Standardmodus", "Modo padrão"],
  "Workspace": ["工作区", "Arbeidsområde", "Espace de travail", "Espacio de trabajo", "ワークスペース", "مساحة العمل", "Arbeitsbereich", "Espaço de trabalho"],
  "Model family": ["模型系列", "Modellfamilie", "Famille de modèles", "Familia de modelos", "モデルファミリー", "عائلة النماذج", "Modellfamilie", "Família de modelos"],
  "Add another model…": ["添加其他模型……", "Legg til en annen modell …", "Ajouter un autre modèle…", "Añadir otro modelo…", "別のモデルを追加…", "إضافة نموذج آخر…", "Weiteres Modell hinzufügen…", "Adicionar outro modelo…"],
  "Channels this session listens to": ["此会话监听的频道", "Kanaler denne økten lytter til", "Canaux écoutés par cette session", "Canales a los que esta sesión escucha", "このセッションがリッスンするチャンネル", "القنوات التي تستمع إليها هذه الجلسة", "Kanäle, auf die diese Sitzung hört", "Canais aos quais esta sessão ouve"],
  "Not subscribed to any channel.": ["未订阅任何频道。", "Abonnerer ikke på noen kanal.", "Aucun abonnement à un canal.", "No suscrito a ningún canal.", "どのチャンネルにも登録されていません。", "غير مشترك في أي قناة.", "Kein Kanal abonniert.", "Não subscrito em nenhum canal."],
  "Unsubscribe": ["取消订阅", "Avslutt abonnement", "Se désabonner", "Cancelar suscripción", "登録解除", "إلغاء الاشتراك", "Abonnement beenden", "Cancelar subscrição"],
  "Trust this workspace’s commands?": ["信任此工作区的命令?", "Stole på kommandoene i dette arbeidsområdet?", "Faire confiance aux commandes de cet espace de travail ?", "¿Confiar en los comandos de este espacio de trabajo?", "このワークスペースのコマンドを信頼しますか？", "هل تثق بأوامر مساحة العمل هذه؟", "Den Befehlen dieses Arbeitsbereichs vertrauen?", "Confiar nos comandos deste espaço de trabalho?"],
  "Repository": ["代码仓库", "Kodelager", "Dépôt", "Repositorio", "リポジトリ", "المستودع", "Repository", "Repositório"],
  "Topics to follow": ["关注主题", "Emner å følge", "Sujets à suivre", "Temas a seguir", "フォローするトピック", "المواضيع للمتابعة", "Themen zum Verfolgen", "Tópicos para seguir"],
  "e.g. AI in consumer research; qualitative methods": ["例如 消费者研究中的 AI;定性研究方法", "f.eks. KI i forbrukerforskning; kvalitative metoder", "p. ex. IA dans les études consommateurs ; méthodes qualitatives", "p. ej. IA en investigación de consumo; métodos cualitativos", "例：消費者調査におけるAI、定性手法", "مثال: الذكاء الاصطناعي في أبحاث المستهلك؛ الأساليب النوعية", "z. B. KI in der Verbraucherforschung; qualitative Methoden", "ex.: IA em pesquisa de consumo; métodos qualitativos"],
  "Post to channel": ["发布到频道", "Publiser i kanal", "Publier dans le canal", "Publicar en el canal", "チャンネルに投稿", "نشر إلى القناة", "Im Kanal veröffentlichen", "Publicar no canal"],
  "When": ["时间", "Når", "Quand", "Cuándo", "いつ", "متى", "Wann", "Quando"],
  "Time": ["时间", "Tid", "Heure", "Hora", "時刻", "الوقت", "Zeit", "Hora"],
  "Deliver to": ["发送到", "Lever til", "Livrer à", "Entregar a", "配信先", "التسليم إلى", "Liefern an", "Entregar a"],
  "Stop this session": ["停止此会话", "Stopp denne økten", "Arrêter cette session", "Detener esta sesión", "このセッションを停止", "إيقاف هذه الجلسة", "Diese Sitzung beenden", "Parar esta sessão"],
  "The agent proposed a plan": ["AI 同事提出了一个计划", "Medarbeideren foreslo en plan", "Le coéquipier a proposé un plan", "El agente propuso un plan", "エージェントが計画を提案しました", "اقترح الوكيل خطة", "Der Agent hat einen Plan vorgeschlagen", "O agente propôs um plano"],
  "What should change about the plan?": ["计划需要做哪些更改?", "Hva bør endres i planen?", "Que faut-il modifier dans le plan ?", "¿Qué debería cambiar del plan?", "計画の何を変更すべきですか？", "ما الذي يجب تغييره في الخطة؟", "Was soll am Plan geändert werden?", "O que deve mudar no plano?"],
  "Unrouted": ["未路由", "Ikke rutet", "Non acheminés", "Sin ruta", "ルーティングなし", "بدون توجيه", "Nicht weitergeleitet", "Sem rota"],
  "Unattended approvals": ["无人处理的审批", "Ubetjente godkjenninger", "Approbations sans surveillance", "Aprobaciones pendientes", "未処理の承認", "موافقات غير معالجة", "Unbearbeitete Genehmigungen", "Aprovações não atendidas"],
  "Direct messages": ["私信", "Direktemeldinger", "Messages directs", "Mensajes directos", "ダイレクトメッセージ", "الرسائل المباشرة", "Direktnachrichten", "Mensagens diretas"],
  "No session — park DMs": ["无会话——暂存私信", "Ingen økt — parker direktemeldinger", "Aucune session — mettre les messages directs en attente", "Sin sesión: estacionar MDs", "セッションなし — DMを保留", "لا توجد جلسة — إيقاف الرسائل المباشرة", "Keine Sitzung – DMs parken", "Sem sessão — estacionar DMs"],
  "Channel subscriptions": ["频道订阅", "Kanalabonnementer", "Abonnements aux canaux", "Suscripciones de canal", "チャンネル購読", "اشتراكات القنوات", "Kanal-Abonnements", "Subscrições de canal"],
  "Session": ["会话", "Økt", "Session", "Sesión", "セッション", "الجلسة", "Sitzung", "Sessão"],
  "Listens to": ["监听", "Lytter til", "Écoute", "Escucha", "リッスン先", "يستمع إلى", "Hört auf", "Ouve"],
  "Inbox routes to": ["收件箱路由到", "Innboks ruter til", "La boîte de réception achemine vers", "La bandeja de entrada enruta a", "受信トレイのルーティング先", "توجيه البريد الوارد إلى", "Posteingang leitet weiter an", "Caixa de entrada encaminha para"],
  "Choose a session…": ["选择会话……", "Velg en økt …", "Choisir une session…", "Elegir una sesión…", "セッションを選択…", "اختر جلسة…", "Sitzung wählen…", "Escolher uma sessão…"],
  "Source": ["来源", "Kilde", "Source", "Fuente", "ソース", "المصدر", "Quelle", "Origem"],
  "Reason": ["原因", "Årsak", "Raison", "Motivo", "理由", "السبب", "Grund", "Motivo"],
  "Message": ["消息", "Melding", "Message", "Mensaje", "メッセージ", "الرسالة", "Nachricht", "Mensagem"],
  "Update available": ["有可用更新", "Oppdatering tilgjengelig", "Mise à jour disponible", "Actualización disponible", "アップデートがあります", "تحديث متاح", "Update verfügbar", "Atualização disponível"],
  "Off = read-only. Tick to let the agent write here.": ["关闭 = 只读。勾选后允许 AI 同事在此写入。", "Av = skrivebeskyttet. Kryss av for å la medarbeideren skrive her.", "Désactivé = lecture seule. Cochez pour autoriser le coéquipier à écrire ici.", "Desactivado = solo lectura. Marca para permitir que el agente escriba aquí.", "オフ = 読み取り専用。チェックするとエージェントがここに書き込めます。", "إيقاف = للقراءة فقط. حدد للسماح للوكيل بالكتابة هنا.", "Aus = schreibgeschützt. Aktivieren, damit der Agent hier schreiben kann.", "Desligado = só leitura. Marque para permitir que o agente escreva aqui."],
  "Previous question": ["上一个问题", "Forrige spørsmål", "Question précédente", "Pregunta anterior", "前の質問", "السؤال السابق", "Vorherige Frage", "Pergunta anterior"],
  "Copy message": ["复制消息", "Kopier melding", "Copier le message", "Copiar mensaje", "メッセージをコピー", "نسخ الرسالة", "Nachricht kopieren", "Copiar mensagem"],
  "assistant": ["AI 同事", "medarbeider", "coéquipier", "asistente", "アシスタント", "مساعد", "Assistent", "assistente"],
  "proposed plan": ["建议的计划", "foreslått plan", "plan proposé", "plan propuesto", "提案された計画", "الخطة المقترحة", "vorgeschlagener Plan", "plano proposto"],
  "Retry": ["重试", "Prøv igjen", "Réessayer", "Reintentar", "再試行", "إعادة المحاولة", "Erneut versuchen", "Tentar novamente"],
  "more…": ["更多……", "mer …", "plus…", "más…", "もっと…", "المزيد…", "mehr…", "mais…"],
  "less…": ["收起……", "mindre …", "moins…", "menos…", "もっと少なく…", "أقل…", "weniger…", "menos…"],
  "Thought process": ["思考过程", "Tankeprosess", "Raisonnement", "Proceso de pensamiento", "思考プロセス", "عملية التفكير", "Gedankenprozess", "Processo de pensamento"],
  "Thinking…": ["思考中……", "Tenker …", "Réflexion…", "Pensando…", "考え中…", "جارٍ التفكير…", "Denke nach…", "Pensando…"],
  "Granted folder access": ["已授予文件夹访问权限", "Mappetilgang innvilget", "Accès au dossier accordé", "Acceso a carpeta concedido", "フォルダアクセスを許可", "تم منح الوصول إلى المجلد", "Ordnerzugriff gewährt", "Acesso à pasta concedido"],
  "Declined folder access": ["已拒绝文件夹访问权限", "Mappetilgang avslått", "Accès au dossier refusé", "Acceso a carpeta denegado", "フォルダアクセスを拒否", "تم رفض الوصول إلى المجلد", "Ordnerzugriff abgelehnt", "Acesso à pasta negado"],
  "Plan approved": ["计划已批准", "Plan godkjent", "Plan approuvé", "Plan aprobado", "計画が承認されました", "تمت الموافقة على الخطة", "Plan genehmigt", "Plano aprovado"],
  "Sent back with feedback": ["已退回并附上反馈", "Sendt tilbake med tilbakemelding", "Renvoyé avec des commentaires", "Enviado de vuelta con comentarios", "フィードバック付きで差し戻されました", "أُعيد مع ملاحظات", "Mit Feedback zurückgesendet", "Enviado de volta com feedback"],
  "Click to dismiss": ["点击关闭", "Klikk for å avvise", "Cliquer pour fermer", "Clic para descartar", "クリックで閉じる", "انقر للإغلاق", "Zum Schließen klicken", "Clique para dispensar"],
  "Open MimiWork (drag to move)": ["打开 MimiWork(拖动可移动)", "Åpne MimiWork (dra for å flytte)", "Ouvrir MimiWork (faire glisser pour déplacer)", "Abrir MimiWork (arrastrar para mover)", "MimiWorkを開く（ドラッグで移動）", "فتح MimiWork (اسحب للتحريك)", "MimiWork öffnen (ziehen zum Verschieben)", "Abrir MimiWork (arrastar para mover)"],
  "Hide floating Mimi": ["隐藏悬浮 Mimi", "Skjul flytende Mimi", "Masquer Mimi flottante", "Ocultar Mimi flotante", "フローティングMimiを隠す", "إخفاء Mimi العائم", "Schwebendes Mimi ausblenden", "Ocultar Mimi flutuante"],
  "Enabled for this session — tap to mute here": ["已为此会话启用——点击可在此会话中静音", "Aktivert for denne økten — trykk for å dempe her", "Activé pour cette session — cliquez pour désactiver ici", "Habilitado para esta sesión: toca para silenciar aquí", "このセッションで有効 — タップでミュート", "مفعّل لهذه الجلسة — اضغط لكتم الصوت هنا", "Für diese Sitzung aktiviert – tippen, um stummzuschalten", "Ativado para esta sessão — toque para silenciar aqui"],
  "Commands and skills": ["命令和技能", "Kommandoer og ferdigheter", "Commandes et compétences", "Comandos y habilidades", "コマンドとスキル", "الأوامر والمهارات", "Befehle und Fähigkeiten", "Comandos e habilidades"],
  "Looking for files…": ["正在查找文件……", "Leter etter filer …", "Recherche de fichiers…", "Buscando archivos…", "ファイルを検索中…", "جارٍ البحث عن الملفات…", "Suche nach Dateien…", "Procurando arquivos…"],
  "Attach": ["附加文件", "Legg ved", "Joindre", "Adjuntar", "添付", "إرفاق", "Anhängen", "Anexar"],
  "Transcribing…": ["转录中……", "Transkriberer …", "Transcription…", "Transcribiendo…", "文字起こし中…", "جارٍ النسخ…", "Transkribiere…", "A transcrever…"],
  "Connect a model": ["连接模型", "Koble til en modell", "Connecter un modèle", "Conectar un modelo", "モデルを接続", "ربط نموذج", "Modell verbinden", "Ligar um modelo"],
  "No model connected — connect a model": ["未连接模型——连接模型", "Ingen modell er tilkoblet — koble til en modell", "Aucun modèle connecté — connecter un modèle", "No hay modelo conectado: conecta un modelo", "モデルが接続されていません — モデルを接続", "لا يوجد نموذج متصل — قم بربط نموذج", "Kein Modell verbunden — verbinde ein Modell", "Nenhum modelo ligado — ligue um modelo"],
  "No model": ["无模型", "Ingen modell", "Aucun modèle", "Sin modelo", "モデルなし", "لا يوجد نموذج", "Kein Modell", "Sem modelo"],
  "Fetching the model list from the server": ["正在从服务器获取模型列表", "Henter modellisten fra serveren", "Récupération de la liste des modèles depuis le serveur", "Obteniendo la lista de modelos del servidor", "サーバーからモデルリストを取得中", "جلب قائمة النماذج من الخادم", "Modellliste vom Server abrufen", "A obter a lista de modelos do servidor"],
  "Loading models…": ["加载模型中……", "Laster modeller …", "Chargement des modèles…", "Cargando modelos…", "モデルを読み込み中…", "جارٍ تحميل النماذج…", "Lade Modelle…", "A carregar modelos…"],
  "Send": ["发送", "Send", "Envoyer", "Enviar", "送信", "إرسال", "Senden", "Enviar"],
  "Token usage": ["令牌用量", "Tokenbruk", "Utilisation des jetons", "Uso de tokens", "トークン使用量", "استخدام الرموز", "Token-Verbrauch", "Uso de tokens"],
  "Total": ["总计", "Totalt", "Total", "Total", "合計", "الإجمالي", "Gesamt", "Total"],
  "Mode": ["模式", "Modus", "Mode", "Modo", "モード", "الوضع", "Modus", "Modo"],
  "Send approvals to Inbox": ["将审批发送到收件箱", "Send godkjenninger til Innboks", "Envoyer les approbations dans la boîte de réception", "Enviar aprobaciones a la bandeja de entrada", "承認をインボックスに送信", "إرسال الموافقات إلى البريد الوارد", "Genehmigungen an Posteingang senden", "Enviar aprovações para a Caixa de Entrada"],
  "Send approvals to the Inbox": ["将审批发送到收件箱", "Send godkjenninger til Innboks", "Envoyer les approbations dans la boîte de réception", "Enviar aprobaciones a la bandeja de entrada", "承認をインボックスに送信", "إرسال الموافقات إلى البريد الوارد", "Genehmigungen an den Posteingang senden", "Enviar aprovações para a Caixa de Entrada"],
  "Click again to permanently delete": ["再次点击将永久删除", "Klikk igjen for å slette permanent", "Cliquez à nouveau pour supprimer définitivement", "Haz clic de nuevo para eliminar permanentemente", "もう一度クリックすると完全に削除されます", "انقر مرة أخرى للحذف نهائيًا", "Erneut klicken, um endgültig zu löschen", "Clique novamente para eliminar permanentemente"],
  "New project (pick a folder)": ["新建项目(选择文件夹)", "Nytt prosjekt (velg en mappe)", "Nouveau projet (choisir un dossier)", "Nuevo proyecto (elige una carpeta)", "新規プロジェクト（フォルダを選択）", "مشروع جديد (اختر مجلدًا)", "Neues Projekt (Ordner auswählen)", "Novo projeto (escolha uma pasta)"],
  "Group and filter conversations": ["分组并筛选对话", "Grupper og filtrer samtaler", "Grouper et filtrer les conversations", "Agrupar y filtrar conversaciones", "会話をグループ化してフィルタ", "تجميع المحادثات وتصفيتها", "Konversationen gruppieren und filtern", "Agrupar e filtrar conversas"],
  "Signed in to QualiTaTi": ["已登录 QualiTaTi", "Logget inn på QualiTaTi", "Connecté à QualiTaTi", "Sesión iniciada en QualiTaTi", "QualiTaTiにサインイン済み", "تم تسجيل الدخول إلى QualiTaTi", "Bei QualiTaTi angemeldet", "Sessão iniciada no QualiTaTi"],
  "Open qualitati.com": ["打开 qualitati.com", "Åpne qualitati.com", "Ouvrir qualitati.com", "Abrir qualitati.com", "qualitati.comを開く", "فتح qualitati.com", "qualitati.com öffnen", "Abrir qualitati.com"],
  "Powered by": ["技术支持:", "Drevet av", "Propulsé par", "Desarrollado por", "Powered by", "مدعوم بواسطة", "Unterstützt von", "Desenvolvido por"],
  "Reload": ["重新加载", "Last inn på nytt", "Recharger", "Recargar", "再読み込み", "إعادة تحميل", "Neu laden", "Recarregar"],
  "Loading...": ["加载中……", "Laster …", "Chargement…", "Cargando...", "読み込み中...", "جارٍ التحميل...", "Laden...", "A carregar..."],
  "Empty sheet.": ["空工作表。", "Tomt ark.", "Feuille vide.", "Hoja vacía.", "空のシート。", "ورقة فارغة.", "Leeres Blatt.", "Folha vazia."],
  "Choose your language": ["选择你的语言", "Velg språket ditt", "Choisissez votre langue", "Elige tu idioma", "言語を選択", "اختر لغتك", "Sprache wählen", "Escolha o seu idioma"],
  "You can change this later in Settings.": ["你可以稍后在设置中更改。", "Du kan endre dette senere i Innstillinger.", "Vous pouvez modifier cela plus tard dans les paramètres.", "Puedes cambiarlo más tarde en Ajustes.", "これは後で設定で変更できます。", "يمكنك تغيير هذا لاحقًا في الإعدادات.", "Sie können dies später in den Einstellungen ändern.", "Pode alterar isto mais tarde nas Definições."],
};

const IDX: Record<Lang, number> = { en: -1, zh: 0, no: 1, fr: 2, es: 3, ja: 4, ar: 5, de: 6, pt: 7 };
const SOURCE_BY_TRANSLATION = new Map<string, string>();
for (const [source, translations] of Object.entries(D)) {
  SOURCE_BY_TRANSLATION.set(source, source);
  translations.forEach((translation) => SOURCE_BY_TRANSLATION.set(translation, source));
}

let current: Lang = "en";
const subs = new Set<() => void>();

// The tutorial in the reader's language: the README's ten-minute tutorial for English,
// the translated docs/TUTORIAL.<lang>.md on GitHub otherwise (the account menu's Tutorial
// item and the About card's link both go here).
export function tutorialUrl(englishUrl?: string): string {
  const lang = getLang();
  if (lang === "en") return englishUrl || "https://github.com/lanceyuu/mimiwork#the-ten-minute-tutorial";
  return `https://github.com/lanceyuu/mimiwork/blob/main/docs/TUTORIAL.${lang}.md`;
}

export function getLang(): Lang {
  return current;
}
export function setLang(lang: Lang): void {
  if (lang === current) return;
  current = lang;
  if (typeof document !== "undefined") {
    document.documentElement.lang = lang === "no" ? "nb" : lang === "zh" ? "zh-CN" : lang;
    // Arabic reads right to left; the layout follows the document direction.
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
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
