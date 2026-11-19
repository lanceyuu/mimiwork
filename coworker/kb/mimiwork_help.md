# MimiWork help

What Mimi knows about MimiWork itself. One "## " section per topic; `mimiwork_help` searches
them offline. Mapped from the app's own code on 2026-11-19. When a label, page or message in
the app changes, change it here in the same commit: Mimi names only what this file says.

## Where things are: the main window and sidebar
The window has the sidebar on the left, the conversation in the middle and the side panel on the right. The sidebar, top to bottom: "New session", "Search" (searches conversation titles, shortcut Cmd+K), then four pages: "Mail", "Automations", "Apps", "Agents". Below them come "Pinned" conversations, "Scheduled" automations, an "Apps" band and an "Agents" band (when there are any), "Recent" conversations (4 shown, then "Show N more") and "Projects". At the very bottom is the account row: your QualiTaTi username or "Not signed in". Click it for the account menu. Cmd+B hides or shows the sidebar; pressing ? shows all keyboard shortcuts. There is no "Manage" menu anywhere in MimiWork.

## The account menu
Click the account row at the bottom left of the sidebar. It holds: "Inbox", "Connectors", "Settings" (also Cmd+,), "Automations", "Activity", "Tutorial" (opens the online tutorial), "Files", and for a signed-in QualiTaTi account "Top up credits" and "Sign out of QualiTaTi". Signed out, it offers "Sign in or create an account", which opens Settings > Models where the sign-in form is. "Report this problem" is not in this menu: it is a button that appears next to certain errors.

## Settings and its tabs
Open Settings from the account row at the bottom left > "Settings", or press Cmd+,. Tabs: "General", "Models", "Instructions", "Skills", a "Connectors ›" shortcut that opens the Connectors page, and under "More": "Voice input", "Memory", "Transfer guide". There is no Personas tab, no About tab and no Token savings tab: Credits is a card under General, and Token savings is a card under Models.

## Settings > General
Theme (System, Light, Dark); Text size, Font and Background tint; Notifications and sounds; Sidebar (conversations shown per assistant); Mimi style (look of the floating companion); Composer (context window bar); Files (where each conversation's own folder is created, default ~/MimiWork, and "Your folder", a folder every new conversation starts in); Trusted workspaces; Always-on ("Open at login", "Keep this system awake" so scheduled tasks fire, "Floating Mimi"); the latest release; Credits; Language (the app's labels in English, 中文, Norsk, Français, Español, 日本語, العربية, Deutsch, Português; Mimi replies in whatever language you write); and Setup & updates ("Run setup again", "Show the tour", "Check for updates", "Copy diagnostic log", "Show log file").

## Settings > Models: signing in to QualiTaTi
The "QualiTaTi account" card at the top of Settings > Models is the only place to sign in to QualiTaTi (the "质见中国账户" card is for the China site, qualitati.cn). Sign in with Google, Microsoft, or a QualiTaTi username and password, or "Create account". Signed in, the card shows your credits, "Top up", "Sign out", "Your Mimi models" with "Add" and "Test" for each tier, and "Model region": "Default · US" (cheaper credits) or "Strict GDPR · Paris" (data stays in Europe, costs more). QualiTaTi has no API key to paste: it is a sign-in. If the card says "The Mimi models aren't connected yet.", press "Connect the models".

## Where to put an API key (OpenAI, Anthropic, Gemini and others)
It depends on what the key is for, and a key saved in one place does not fill the other.
- For Mimi herself to run on that provider's models: Settings > Models > the provider's card in the list (for example "OpenAI", "Claude (Anthropic)", "Gemini (Google)", "OpenRouter", "DeepSeek") > paste the key > "Test". Its models then appear in the composer's model picker.
- For a script Mimi runs that reads a key from its environment (OPENAI_API_KEY, TAVILY_API_KEY and so on): Settings > Models > "Keys for your own scripts". Any name works; pasting the lines of a .env file saves every NAME=value line at once. You can also paste the key in a chat and ask Mimi to keep it: she saves it there with save_script_key after asking you. These keys never run Mimi's own models.
The message "No model API key configured" means a model was chosen whose provider has no key on this computer: add the key in Settings > Models, or pick a Mimi tier in the model picker.

## Settings > Models: other cards
Below the providers: "In the composer's picker" (tick which models the picker offers; "Make default"), "Keys for your own scripts", "Paper search" (an optional OpenAlex key; without one a small free daily limit shared with your network applies to paper searches and reference checks), "Token savings" (how PDFs are handled on models that cannot read PDFs, with Max pages, default 20, and Max size, default 10 MB) and "Context compaction" (when long conversations are summarised: at 80% of the context or 250,000 tokens by default, and which model summarises).

## The Mimi models: Puppy, Hound, Wolf, Werewolf
All four need a QualiTaTi sign-in. Mimi Puppy (fastest) and Mimi Hound (robust) are free every day and share one daily free allowance; one task can use several requests. Mimi Wolf (powerful) and Mimi Werewolf (frontier, the strongest) spend QualiTaTi credits. The line under the message box shows how many free requests are left today. When the free allowance is used up, switch to Mimi Wolf (it uses credits) or wait for the reset time shown; Hound will not help, because it shares Puppy's allowance. When the credit balance is empty, top up at qualitati.com/recharge or switch to Puppy within its free allowance. You change the model with the model chip next to the mode chip under the message box, even in the middle of a conversation.

## Permission modes: Default, Accept edits, Plan, Bypass permissions
The chip to the left of the model picker sets how much Mimi may do without asking:
- "Default": asks before edits and commands.
- "Accept edits": edits files in the folder without asking; still asks before commands.
- "Plan": explores and proposes a plan; nothing runs until you approve it ("Approve — ask per step" or "Approve & run").
- "Bypass permissions": runs everything without asking.
Shift+Tab cycles Default, Accept edits and Plan; Bypass permissions is chosen from the menu only. In every mode, including Bypass, a write outside a writable folder is refused and a destructive command is confirmed every time. The menu also has "Send approvals to Inbox", which parks approvals and questions in the Inbox so the work continues elsewhere. Approval cards answer with "Yes", "Yes, always", "Yes, always for this command" or "No" (keys y, a, n). There are no modes called "Ask for approval", "Full access" or "Discuss" in the app.

## Folders: what Mimi can read and change
Each conversation gets its own folder under ~/MimiWork (shown as "Temporary space"), or starts in "Your folder" if one is set in Settings > General > Files. Mimi can read only the folders granted to the conversation; nothing else on the computer. The folders granted to a conversation are listed to Mimi in every turn, so she never needs to run a command to find out where she is. To add one: side panel on the right > "Folders" > "Add a folder" > choose the folder > tick "Allow writes" if Mimi should change files there (otherwise it is read-only) > "Add". Mimi can also ask for a folder mid-task with a card ("Grant access" or "Decline"); she does this with request_directory. A folder granted in one conversation is not granted in the next, unless it is "Your folder".

## Attaching files to a message
Use the "+" button ("Attach": Photo or image, PDF, Word, Excel, PowerPoint, Other files), or drop or paste files into the message box. Images, PDFs and text files are sent with the message; Office files are saved into the conversation's folder and Mimi opens them with her Office tools. Limits: 8 attachments per message, about 10 MB per file, 15 MB per message. A bigger file is saved into the folder and mentioned with @. Type @ in the message box to point Mimi at a file in a granted folder, and / for commands and skills (/help, /init, /clear, /compact, /plan, /model, /memory, /skills).

## Stopping, steering and retrying a task
While Mimi works, type in the message box and press "Steer" to change course without restarting, or "Stop task" (Esc) to stop; "Force stop" appears if stopping hangs. "Retry" appears on the last error in a conversation; switching the model first and then retrying is a normal way out of a model error. "Connection lost. Reconnecting…" means the app lost touch with its own local server for a moment; the task may still be running.

## Files Mimi makes: artifacts, opening, undo
Files Mimi produced appear as chips in the chat and under "Artifacts" in the side panel. Each has "Open", "Show in folder" and "Revise". Opening one shows a preview with "Comment on this file" (pin numbered notes and send them to Mimi), "Open in default app", "Copy path" and "Show in folder". Word and PDF previews have a "References" tab that checks each reference against Crossref and OpenAlex and labels it "Retracted", "Needs a fix", "Not found" or "Couldn't check"; for Word, the fixes can be written in as tracked changes. Mimi revises Word files with tracked changes you accept or reject in Word (Review > Track Changes). "File recovery" in the side panel has "Undo latest file changes", which restores the files changed in Mimi's latest turn.

## Connectors: email, Notion, Slack and other services
Account row > "Connectors" (or Settings > "Connectors ›"). Tabs: "Connectors", "Coding agents", "MCP servers". The Connectors tab lists services under "Connected" and "Available", each with "Connect": Telegram, Slack, "Email (IMAP)", Gmail, Google Calendar, Browser, GitHub, Outlook, Jira, monday.com, Confluence, Zendesk, Linear, GitLab, Discord, Stripe, Asana, HubSpot, Dropbox, Box, WhatsApp, QuickBooks, Docusign, ClickUp, Google Drive, Canva, Figma, Close, Notion, Attio, PostHog, Mixpanel, Amplitude, Apollo.io, Hunter, Qualtrics. Notion, Jira, monday.com and Canva sign in with one click in the browser. One-click sign-in for Gmail, Google Calendar and Google Drive is paused ("Coming soon"). A connector can be muted for one conversation in the side panel under "Access". Connector reads run without asking; anything that sends or changes something asks first.

## Connecting email
Mail and Mimi's email tools use the "Email (IMAP)" connector: account row > "Connectors" > "Email (IMAP)" > your address and an app password. Gmail, iCloud and Fastmail servers are found automatically; other providers need their IMAP and SMTP server names. A personal Gmail works with an app password. Google Workspace and Microsoft 365 accounts often have IMAP or app passwords switched off by the organisation's admin. One-click Gmail and Outlook sign-in is not available yet.

## Coding agents: Claude Code, Codex, opencode, Cursor, Gemini CLI
These are separate programs on your computer that take on software and file work for Mimi, on your own accounts and not on QualiTaTi credits. There are exactly five: Claude Code, Codex, opencode, Cursor and Gemini CLI. Set them up at account row > "Connectors" > "Coding agents": each shows "Installed", "Signed in", "Model", "Effort" and "Test", and a status of "Not installed", "Not signed in", "Needs attention" or "Connected". Install commands: Claude Code `curl -fsSL https://claude.ai/install.sh | bash`; Codex `npm install -g @openai/codex`; opencode `curl -fsSL https://opencode.ai/install | bash`; Cursor `curl https://cursor.com/install -fsS | bash`; Gemini CLI `npm install -g @google/gemini-cli`. Sign in with the "Sign in" button (or `claude auth login`, `codex login`, `cursor-agent login`); opencode needs no sign-in for its free models; Gemini CLI has no button: run `gemini` once, choose Use Gemini API Key and paste a key from Google AI Studio. Mimi asks before every hand-off, and in a git project each agent works on its own branch. "Is installed but not signed in" means: sign in on that page, then try again.

## MCP servers
Account row > "Connectors" > "MCP servers": external tool servers shared by all conversations. "+ Add server" takes pasted JSON (name → config); "Refresh connections" reloads them. Enabled servers' tools load with your next message and follow your permission mode.

## Agents: what an agent system is
Sidebar > "Agents". An agent system is a reusable team of agents for a job you do again and again, drawn as a diagram. "Describe what you need" + "Design it with Mimi" opens a conversation that designs one with you; "Start from a pattern" offers nine working examples (Sequence, Routing, Parallel work, Reflection, ReAct, Planning, Tool use, Multi-agent, Human review). A system's page has "Run", "Duplicate", "Export" (saves system.json to Downloads) and "Delete"; click the title to rename it. Mimi links to a system with a link of the form agent:<id>, which opens it in Agents.

## Agents: the kinds of node
Add nodes from the bar above the canvas:
- "Mimi agent": does one job with its own model, thinking effort and tools.
- "Coding agent": hands the job to Claude Code, Codex, opencode, Cursor or Gemini CLI, in a project folder.
- "Router": sends the work down exactly one labelled connection.
- "Lead agent (assigns work)": plans the work and gives parts to helpers connected by dashed lines; helpers run only when the lead asks. Only a lead agent can assign work, and a lead agent is always a Mimi agent: a coding agent cannot lead.
- "Human review": the run stops and asks you to approve, send back with a comment, or stop.
When someone wants Claude Code, Codex or Gemini to take part, they are Coding agent nodes with that coding agent chosen. Never make a Mimi agent and put a coding agent's name in its model: the model field takes a model from your picker, or stays empty to use the chat's model. A Mimi agent can still run on a Claude, GPT or Gemini model if that model is in your picker. To have "Claude" coordinate coding agents, use a Lead agent on a model you have, assigning work to the coding agents.

## Agents: node settings and connections
Click a node to edit it. Every node has "Name" and "What should it do?". Mimi agents, routers and leads have "Model" (default: the model the chat uses), "Thinking effort" (Default, Low, Medium, High) and "Tools it may use" (Files, Search, Word documents, Excel workbooks, PowerPoint decks, PDF documents, Images, Dataset inspection, Python analysis, R analysis, Research-methods knowledge base, QualiTaTi projects, Task list, Code files, Git, Shell). A coding agent has "Coding agent", "Its model", "Thinking effort" and "Project folder". Connect nodes by dragging from a node's right edge to another node. A connection either goes forward or loops back up to 1 to 5 times; a looping checker starts its answer with PASS to move on. "Start the work here" sets the starting node. Limits: 30 agents, loops of 1 to 5 rounds, 40 agent runs in one run.

## Agents: running a system and giving it a question
Press "Run" on the system's page, type what the agents should work on (your question or task) in the box, then "Run in a chat". This always starts a new conversation that runs the system on that input; review steps ask you in that chat. Mimi can also run a saved system from any chat with run_agent_system, by its id or exact title, with your input. The system's page then shows "Last run: Running", "Finished", "Stopped with an error" or "Stopped", and each node lights up as it works. Each Mimi agent spends credits on its own model; coding agents run on your own accounts.

## Agents: "Before this can run" and other run errors
A red line "Before this can run:" above the canvas lists what blocks a run, and Run stays disabled until it is fixed: "Choose which agent starts the work.", "Tell this agent what to do.", "Choose which coding agent does this work.", "Choose the project folder the coding agent works in.", "Only a lead agent can assign work.", "An agent cannot connect to itself.", "The flow goes in a circle. Give the connection that loops back a round limit.", "Each of a router's connections needs a different label.", "<name> is a coding agent, not a model. Make it a Coding agent node…". At run time: "<agent> is installed but not signed in" means sign in at Connectors > Coding agents; "No model API key configured" means a node's model has no key on this computer (choose a Mimi tier or add the key in Settings > Models).

## Agents: which folder a coding agent works in
A coding agent works in its node's "Project folder", which must be inside a writable folder granted to the conversation that runs the system. Empty means the conversation's own folder. A system saved in one chat may remember that chat's temporary folder; when it runs from another chat it now uses the new chat's folder instead. A real project folder must be granted in the running chat: side panel > "Folders" > "Add a folder" > tick "Allow writes" (Mimi can ask for it with request_directory), then run again. In a git project the work happens in a copy on its own branch (mimi/…), so your folder is not changed; all coding agents in one run share that copy.

## Automations (scheduled tasks)
Sidebar > "Automations". "+ New automation": a title, "What should it do each run?", a time ("At") and "Repeat" (Every day, Weekdays, Weekends), "Model", "Permission", "Works in:" (a folder, or a fresh one each run) and up to 10 attached files. "Starter blueprints" offers ready ones (GitHub digest, Pipeline digest, Morning brief, Weekly research digest, Morning news briefing, Inbox digest, Folder cleanup); "Import blueprint" takes a .mimiflow.json file. An automation's page has "▶ Run now", "Share blueprint", "Edit", "Delete", an on/off switch, its instructions, "Allowed without asking" and its "Runs", each opening its own conversation. Automations run only while MimiWork is open; a missed run catches up once when it next starts. Settings > General > "Keep this system awake" keeps the computer from sleeping through a schedule. In an automation, "Default" mode parks questions in the Inbox and waits.

## Apps
Sidebar > "Apps": small tools Mimi builds for you, such as a form, a button and a result, that run inside MimiWork and can ask Mimi when they need to. Describe it under "What should the app do?" and press "Build with Mimi". An app's page has "Model", "Undo last change", "Improve" (ask Mimi to change it), "Export" (a .mimiapp.html file) and delete.

## Mail
Sidebar > "Mail". It reads the mailbox connected as "Email (IMAP)" in Connectors; without one it shows "Open Connectors". Toolbar: "Search mail", "Ask Mimi" (a question about the open conversation or the whole mailbox, answered in a new chat), "New message", "Sorting", "Refresh". Tabs: "All", "Sent", "Drafts", and with sorting on "Needs reply", "FYI", "Newsletters". Sorting stays off until "Turn on sorting" and spends credits. Reading a message: "Archive", "Move to bin", "Mark unread", "Reply", "Reply all"; images stay blocked until "Show images". "Comments": select text, press "Comment", say what the reply should say, then "Write reply". A draft has "Rewrite" (shorter, warmer…) and "Discard". "Mail could not find a Sent folder in this mailbox." means the mailbox has no folder Mail recognises as Sent.

## Inbox: approvals and questions
Account row > "Inbox", or the Inbox chip on the account row. It collects approvals, questions and notifications, including from conversations running unattended and from automations. Tabs "Pending" and "Configure"; filters "All", "Approvals", "Questions". A question can be skipped ("use your own judgement"). Turn on "Send approvals to Inbox" in the mode menu to send a conversation's approvals here.

## Projects
The "Projects" band in the sidebar, below Recent. "+" ("New project") creates one. Drag a conversation onto a project to move it there. A project's page has a name and icon, "Pin to the top", "Instructions" added to every new conversation in it, "What Mimi knows" (facts you teach it), its conversations, and "Delete project" (optionally with its conversations).

## Skills
Settings > "Skills": reusable ways Mimi handles recurring work. "Add skill" offers "Write it myself", "Import a file" (.zip or SKILL.md), "Create with MimiWork", "Import from Claude Code" and "Browse the skill store". A skill turned off here stays off everywhere. In a chat, type / to use one directly.

## Instructions and Memory
Settings > "Instructions": standing context for every conversation (how you like things done, what to avoid); it is saved as an AGENTS.md file. A folder can add its own AGENTS.md or CLAUDE.md. Settings > More > "Memory": "Remember new things about me" on or off (each save shows a note in the chat with Undo), "What I've learned about you" as a list or graph with "Fix this" and "Delete this memory", "Forget everything…", and a separate "Your instructions" list.

## Conversations: rename, pin, archive, delete, find
Hover a conversation in the sidebar and click ⋮: "Rename", "Pin", "Archive", "Duplicate as new thread", "Delete". Deleting removes the messages and the record of what Mimi did; files written to your folders stay. Archived conversations are hidden from the Recent list and from Search; to see them: the sliders icon next to "Recent" > Group by > "Persona" > "Coworker" > "Archived (n)". Search (Cmd+K) looks at conversation titles.

## Activity, Files and time saved
Account row > "Activity": what ran and what it cost in credits, with filters. Account row > "Files": the current conversation's folders and the files Mimi made; text files open in a small editor with "Save" and "Proofread", and saved versions are kept. Time saved shows on the account row once it reaches 30 minutes, under the message box and in Activity; it is an estimate from what was produced, not a measurement.

## Voice input
Settings > More > "Voice input" (desktop app only): download the local "Whisper Base · English" model (about 141 MB) and pass the "Microphone test"; the microphone button in the message box works only after that. Recordings stay on the computer. Only English is offered. Requirements: macOS 12 or later on Apple Silicon, or Windows 10 22H2 or 11 on x64.

## Slides and presentations
Mimi writes editable PowerPoint decks. The default style is image first: photographs free of copyright found with search_slide_photos (CC0 or public domain, stock photography first, then Wikimedia Commons), one idea per slide, few words on the slide and the rest in the speaker notes, and a "Photo credits" slide at the end. A house template or a style you give replaces the default. Pictures of the finished slides are checked only on a computer with LibreOffice installed; LibreOffice draws fonts it does not have with substitutes, and on some Macs draws no Chinese at all, which does not affect the saved deck.

## Report this problem, diagnostic log, updates
"Report this problem" is a button next to certain errors, not a menu item. It sends the error, the app version and platform, your QualiTaTi username and the end of the app log to the QualiTaTi team; nothing from the conversation is sent. Without a network: Settings > General > "Copy diagnostic log" and paste it into a message to the team. Updates: an "Update available" banner with "Restart to update", or Settings > General > "Check for updates". "Run setup again" and "Show the tour" are also under Settings > General.
