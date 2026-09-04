# The MimiWork tutorial

**English** · [中文](TUTORIAL.zh.md) · [Norsk](TUTORIAL.no.md) · [Français](TUTORIAL.fr.md)

Ten minutes, from first launch to your own automation. Every step here works on a fresh
install — nothing needs a developer.

The one habit that matters most: **ask for the outcome, not the steps.** MimiWork's job is
to hand you a finished file. "Read these transcripts and write me a themed summary as a
Word doc" gets you `summary.docx`. "Can you help me analyse interviews?" gets you a
conversation.

---

## 0 · Install (once)

Download from the [Releases page](https://github.com/lanceyuu/mimiwork/releases/latest): the
`.dmg` for Mac (Apple Silicon or Intel), the `-setup.exe` for Windows. MimiWork is not yet
signed with Apple or Microsoft, so the first launch asks you to vouch for it — once.

- **Mac:** drag MimiWork to Applications and double-click it. When macOS says it could not
  verify the app (or calls it “damaged”), click **Done**, open **System Settings ▸ Privacy &
  Security**, scroll to *Security* and click **Open Anyway**, then open MimiWork again and
  enter your password. No button there? Open Terminal and run
  `xattr -cr /Applications/MimiWork.app`, then open it normally.
- **Windows:** if the browser holds the download, choose **Keep ▸ Show more ▸ Keep anyway**
  (Edge) or **Keep** (Chrome). Run the installer; on the blue *Windows protected your PC*
  screen click **More info ▸ Run anyway**. On a locked-down work PC: right-click the file ▸
  Properties ▸ tick **Unblock**.

Every step, with the exact wording of each prompt, is in the
[README’s Install section](../README.md#install). Updates install from inside the app and
never ask again.

---

## 1 · Connect a model (2 minutes)

Open **Settings ▸ Models**. Two ways in:

- **Sign in with QualiTaTi** — no keys, the Mimi models spend your existing credits.
  After signing in you'll see the three tiers right on the card — **Mimi Puppy** (free
  every day), **Mimi Hound** (fast), **Mimi Wolf** (most capable) — each with a **Test**
  button that makes a real one-token call, so you know it works before you need it.
  Two things worth setting while you're here:
  - **Model region** — *Default · US* (cheaper credits) or *Strict GDPR · Paris 🇫🇷*
    (data stays in Europe). It applies to your account's next message, on every device.
  - The **Activity** page (left sidebar) will show exactly what each call cost and which
    pool paid — the numbers come from the server's ledger, not an estimate.
- **Paste your own key** — OpenAI, Anthropic, Gemini, Kimi, DeepSeek, Mistral and a dozen
  more, or fully local via Ollama. Switch anytime from the picker in the composer.

## 2 · Give it a folder

Click the folder starter card (or just ask "work in my Projects/interviews folder").
**Nothing outside the folders you grant is readable** — that's the whole privacy model,
so grant the folder where the real files live. Click a folder's name under Access any
time to open it in Finder/Explorer.

**You hand it over once.** The folder you pick during setup is remembered, and every new
conversation starts with it already granted — no re-granting from the Access panel each
time. Change or clear it under Settings ▸ Files ▸ *Your folder*, where a checkbox decides
whether Mimi may **save** into it (read-write) or only read. Leave it read-write if you
want finished files to land there.

Folders you grant inside a conversation stay with that conversation — a one-off is a
one-off.

## 3 · The first real task

With a folder granted, try one of these, changing the filenames to yours:

> Read the three PDFs in this folder and write a one-page brief as `brief.docx` —
> keep the numbers in a table.

> Profile `wave2.sav` and tell me what's in it before doing anything else.

> Turn `results.xlsx` into a 10-slide deck that argues we should fix mobile first.
> Speaker notes for my co-presenter.

What to expect while it runs:

- **Anything consequential asks first.** Sending, writing outside the folder, shell
  commands, pulling data from a server — you get an approval card, every time.
- **You can steer without stopping.** Notice it heading the wrong way? Just type —
  *"use the December wave, not November"* — and it lands at the next safe step. The work
  keeps going; your instruction isn't lost and doesn't restart anything.
- **Drop files straight into the chat.** A file from a granted folder becomes an
  `@mention` (worked on in place). A file from anywhere else is copied into the session's
  folder — visibly, next to your other files — and opened with the right tool.
- The finished file lands **in your folder** — never in the conversation's temporary
  space, once you've granted a folder Mimi may write to. The **Artifacts** panel lists
  what you asked for — the report, the workbook, the chart — and keeps the script that
  produced it out of the way. The **Files** page keeps every deliverable from every
  session in one place.

## 4 · Three keys to learn

| Key | What it does |
|---|---|
| **`/`** | The command palette: app commands (`/plan`, `/compact`, `/init`, `/model`…), your saved commands, and your skills |
| **`@`** | Point at a specific file in a granted folder — no path typing |
| **`⇧⇥`** | Cycle permission modes: **Plan** (propose first, touch nothing) → **Ask for approval** (the default) → **Full access** |

If you know Claude Code, Cowork or Codex, these are the same gestures — and
**Settings ▸ Transfer guide** maps every MimiWork concept to its name over there.

**Plan mode deserves a special mention.** For anything with stakes — a deliverable for a
client, a big refactor of your data files — hit `⇧⇥` into Plan first. Mimi proposes the
whole approach, you approve or redirect, *then* it runs. One minute of reading a plan
beats twenty minutes of redoing the work.

## 5 · Teach it your way — once

The difference between a good tool and a colleague is that a colleague remembers.

- **Instructions** (Settings ▸ Instructions, or an `AGENTS.md` in your folder — `CLAUDE.md`
  works too): standing rules. *"Reports in UK English. Stats always with effect sizes.
  Never touch files in /raw."*
- **Skills** (Settings ▸ Skills): packaged know-how. The starter card *"Package your
  style guidelines in a skill"* walks you through your first one — brand colors, fonts,
  house rules — and from then on every deck and doc comes out in them without being asked.
  Browse the store's **8,400 community skills** by shelf, and read a skill's actual
  instructions before installing. Already have skills in `~/.claude/skills`? The Skills
  tab finds and imports them.
- **Memory** (Settings ▸ Memory): what Mimi noticed and kept. Review it, edit it, delete it.

## 6 · Connect where you work

**Settings ▸ Connectors.** Slack (tag Mimi in a channel, the finished work comes back in
the thread), Gmail/Outlook, Google Calendar and Drive, GitHub, Jira, Notion, Canva,
**Qualtrics** (read a survey's questionnaire so `Q4_1` becomes a real question, pull
responses as CSV or labelled SPSS `.sav` — with your approval per download), and your
QualiTaTi research data (projects, interviews, surveys — each retrieval asks first).
Anything else speaks [MCP](https://modelcontextprotocol.io/).

## 7 · Make it run while you don't

Ask in plain words:

> Every Monday at 8, read the new files in `field-notes/`, and put a one-page weekly
> summary in `reports/`.

That becomes an **Automation** (sidebar) — running locally, full transcript kept, and
anything that needs a decision waits in your **Inbox** instead of guessing. Watch a Slack
channel, refresh a weekly deck, chase a dataset — same pattern.

## 8 · The floating Mimi

The little companion on your desktop is a status light: it shows when Mimi is working, or
when something is waiting on you. Drag it anywhere — it stays where you put it. Click the
icon to open the app — that counts as "seen", so a finished-task cheer you've already
looked at won't keep repeating. Click a bubble to dismiss just that message.

---

## A good week with MimiWork, in five asks

1. *"Work in this folder. Profile every `.sav` in it and give me a data dictionary as a Word doc."*
2. *"Package our brand guidelines into a skill"* → every future deck is on-brand.
3. *"Turn the wave-2 findings into a 12-slide deck for the steering committee — argue for the mobile fix, speaker notes included."* (in **Plan mode**)
4. *"Pull the December survey from Qualtrics as SPSS and check whether satisfaction differs by channel — effect sizes, not just p-values."*
5. *"Every Friday at 4, summarise this Slack channel's week into a memo in `reports/`."*

By Friday you have a data dictionary, an on-brand deck, a real analysis, and a standing
automation — and every file is on your disk, made with your keys, under your approval.
