# MimiWork-veiledningen

[English](TUTORIAL.md) · [中文](TUTORIAL.zh.md) · **Norsk** · [Français](TUTORIAL.fr.md)

Ti minutter fra første oppstart til din egen automatisering. Alt her fungerer på en fersk installasjon — ingen utviklerkunnskap nødvendig.

Den ene vanen som betyr mest: **be om resultatet, ikke stegene.** MimiWorks jobb er å levere en ferdig fil. «Les disse intervjuutskriftene og skriv et tematisk sammendrag som Word-dokument» gir deg `summary.docx`. «Kan du hjelpe meg å analysere intervjuer?» gir deg en samtale.

---

## 0 · Installer (én gang)

Last ned fra [Releases-siden](https://github.com/lanceyuu/mimiwork/releases/latest): `.dmg` for Mac (Apple Silicon eller Intel), `-setup.exe` for Windows. MimiWork er ennå ikke signert hos Apple eller Microsoft, så første oppstart ber deg gå god for appen — én gang.

- **Mac:** dra MimiWork til Programmer og dobbeltklikk. Når macOS sier den ikke kan verifisere appen (eller kaller den «skadet»), klikk **Ferdig**, åpne **Systeminnstillinger ▸ Personvern og sikkerhet**, bla til *Sikkerhet* og klikk **Åpne likevel**, åpne MimiWork igjen og skriv inn passordet ditt. Ingen knapp der? Åpne Terminal og kjør `xattr -cr /Applications/MimiWork.app`, og åpne appen som vanlig.
- **Windows:** holder nettleseren nedlastingen tilbake, velg **Behold ▸ Vis mer ▸ Behold likevel** (Edge) eller **Behold** (Chrome). Kjør installasjonen; på den blå skjermen *Windows beskyttet PC-en din* klikker du **Mer info ▸ Kjør likevel**. På en låst jobb-PC: høyreklikk filen ▸ Egenskaper ▸ huk av **Fjern blokkering**.

Hvert steg, med den nøyaktige ordlyden i hver melding, står i [README-ens Install-del](../README.md#install). Oppdateringer installeres fra appen og spør aldri igjen.

---

## 1 · Koble til en modell (2 minutter)

Åpne **Settings ▸ Models** (Innstillinger ▸ Modeller). To veier inn:

- **Logg inn med QualiTaTi** — ingen nøkler; Mimi-modellene bruker kredittene du allerede har. Etter innlogging viser kortet de tre nivåene — **Mimi Puppy** (gratis hver dag), **Mimi Hound** (rask), **Mimi Wolf** (mest kapabel) — hvert med en **Test**-knapp som gjør et ekte kall, så du vet at det virker før du trenger det. To ting verdt å sette med det samme:
  - **Model region** (modellregion) — *Default · US* (billigere kreditter) eller *Strict GDPR · Paris* (data blir i Europa). Gjelder fra kontoens neste melding, på alle enheter.
  - **Activity**-siden (venstre sidefelt) viser nøyaktig hva hvert kall kostet og hvilken pott som betalte — tallene kommer fra serverens hovedbok, ikke et lokalt anslag.
- **Lim inn din egen nøkkel** — OpenAI, Anthropic, Gemini, Kimi, DeepSeek, Mistral og et dusin til, eller helt lokalt via Ollama. Bytt når som helst fra velgeren i skrivefeltet.

## 2 · Gi den en mappe

Klikk på mappe-startkortet (eller bare si «jobb i mappen Projects/interviews»). **Ingenting utenfor mappene du gir tilgang til, kan leses** — det er hele personvernmodellen, så gi tilgang til mappen der de virkelige filene ligger. Klikk på et mappenavn under Access når som helst for å åpne den i Finder/Utforsker.

**Du gir den fra deg én gang.** Mappen du velger under oppsettet blir husket, og hver ny samtale starter med den allerede tildelt — du slipper å gi tilgang på nytt fra Access-panelet hver gang. Endre eller fjern den under Innstillinger ▸ Filer ▸ *Mappen din*, der en avkrysningsboks avgjør om Mimi får **lagre** i den (lese/skrive) eller bare lese. La den stå som lese/skrive hvis du vil at ferdige filer skal havne der.

Mapper du gir tilgang til inne i en samtale, blir værende i den samtalen — et engangsunntak forblir et engangsunntak.

## 3 · Den første ordentlige oppgaven

Med en mappe på plass, prøv en av disse (bytt ut filnavnene med dine egne):

> Les de tre PDF-ene i denne mappen og skriv et énsides sammendrag som `brief.docx` — tallene i en tabell.

> Profiler `wave2.sav` og fortell meg hva som er i den før du gjør noe annet.

> Gjør `results.xlsx` om til en 10-siders presentasjon som argumenterer for at vi bør fikse mobil først. Talenotater til medpresentøren min.

Dette skjer mens den jobber:

- **Alt med konsekvenser spør først.** Sending, skriving utenfor mappen, kommandoer, datahenting fra en server — du får et godkjenningskort, hver gang.
- **Du kan styre uten å stoppe.** Ser du at den er på feil spor? Bare skriv — «bruk desember-runden, ikke november» — så lander det ved neste trygge steg. Arbeidet fortsetter; instruksjonen din går ikke tapt og starter ingenting på nytt.
- **Slipp filer rett i samtalen.** En fil fra en tildelt mappe blir en `@-referanse` (behandles der den ligger). En fil fra hvor som helst ellers kopieres synlig inn i øktens mappe — ved siden av de andre filene dine — og åpnes med riktig verktøy.
- Ferdige filer lander **i mappen din** — aldri i samtalens midlertidige område, så snart du har gitt tilgang til en mappe Mimi får skrive i. **Artifacts**-panelet viser det du ba om — rapporten, regnearket, diagrammet — og holder skriptet som laget det unna. **Files**-siden samler alle leveranser fra alle økter på ett sted.

## 4 · Tre taster å lære

| Tast | Hva den gjør |
|---|---|
| **`/`** | Kommandopaletten: appkommandoer (`/plan`, `/compact`, `/init`, `/model` …), dine lagrede kommandoer, dine ferdigheter |
| **`@`** | Pek på en bestemt fil i en tildelt mappe — ingen filbaner å skrive |
| **`⇧⇥`** | Bytt tillatelsesmodus: **Plan** (foreslå først, rør ingenting) → **Ask for approval** (standard) → **Full access** |

Kjenner du Claude Code, Cowork eller Codex, er dette de samme bevegelsene — **Settings ▸ Transfer guide** har hele oversikten.

**Plan-modus fortjener en egen setning.** For alt som har innsats — en leveranse til en klient, en stor omstrukturering av datafilene — trykk `⇧⇥` til Plan først. Mimi legger fram hele opplegget, du godkjenner eller justerer, *så* kjører den. Ett minutt med å lese en plan slår tjue minutter med omarbeid.

## 5 · Lær den din måte — én gang

Forskjellen på et godt verktøy og en kollega er at en kollega husker.

- **Instructions** (Settings ▸ Instructions, eller en `AGENTS.md` i mappen din — `CLAUDE.md` virker også): faste regler. «Rapporter på britisk engelsk. Statistikk alltid med effektstørrelser. Aldri rør filene i /raw.»
- **Skills** (Settings ▸ Skills): pakket kunnskap. Startkortet «Package your style guidelines in a skill» tar deg gjennom din første — merkevarefarger, fonter, husregler — og deretter kommer hver presentasjon og hvert dokument ut i dem uten at du ber om det. Bla i **8 400 fellesskapsferdigheter**, og les en ferdighets faktiske instruksjoner før du installerer. Har du allerede ferdigheter i `~/.claude/skills`? Skills-fanen finner og importerer dem.
- **Memory** (Settings ▸ Memory): det Mimi la merke til og tok vare på. Se gjennom, rediger, slett.

## 6 · Koble til der du jobber

**Settings ▸ Connectors.** Slack (tagg Mimi i en kanal, det ferdige arbeidet kommer tilbake i tråden), Gmail/Outlook, Google Kalender og Disk, GitHub, Jira, Notion, Canva, **Qualtrics** (les spørreskjemaet så `Q4_1` blir et ekte spørsmål, hent svar som CSV eller etikettert SPSS `.sav` — med din godkjenning per nedlasting), og QualiTaTi-forskningsdataene dine (prosjekter, intervjuer, undersøkelser — hver henting spør først). Alt annet snakker [MCP](https://modelcontextprotocol.io/).

## 7 · La den jobbe når du ikke gjør det

Si det med vanlige ord:

> Hver mandag klokken 8: les de nye filene i `field-notes/` og legg et énsides ukesammendrag i `reports/`.

Det blir en **Automation** (sidefeltet) — kjører lokalt, full logg, og alt som krever en beslutning venter i **Inbox** i stedet for å gjette. Overvåk en Slack-kanal, oppdater en ukentlig presentasjon, jag et datasett — samme mønster.

## 8 · Den flytende Mimi

Den lille hunden på skrivebordet er en statuslampe: den viser når Mimi jobber, eller når noe venter på deg. Dra den dit du vil — den blir der. Klikk på ikonet for å åpne appen — det teller som «sett», så en ferdig oppgave du allerede har sett på blir ikke meldt om igjen og igjen. Klikk på en boble for å lukke bare den meldingen.

---

## En god uke med MimiWork, i fem forespørsler

1. «Jobb i denne mappen. Profiler hver `.sav` i den og gi meg en dataordbok som Word-dokument.»
2. «Pakk merkevareretningslinjene våre inn i en ferdighet» → hver framtidige presentasjon følger profilen.
3. «Gjør funnene fra runde to om til en 12-siders presentasjon for styringsgruppen — argumenter for mobilfiksen, med talenotater.» (i **Plan-modus**)
4. «Hent desemberundersøkelsen fra Qualtrics som SPSS og test om tilfredshet varierer med kanal — effektstørrelser, ikke bare p-verdier.»
5. «Hver fredag klokken 16: oppsummer denne Slack-kanalens uke i et notat i `reports/`.»

Innen fredag har du en dataordbok, en profilriktig presentasjon, en ekte analyse og en stående automatisering — og hver fil ligger på din disk, laget med dine nøkler, under din godkjenning.
