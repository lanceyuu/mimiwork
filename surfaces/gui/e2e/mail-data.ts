// What the mocked backend answers for the Mail section: three inbox conversations (one of
// them hostile), their messages, one archived message that only search can reach, and two
// conversations that are only in Sent.

export const TRACKER = "https://tracker.invalid";
const NOW = Math.floor(Date.now() / 1000);

const envelope = (uid: number, from: string, subject: string, date: number, extra: object = {}) => ({
  folder: "INBOX", uid, message_id: `<${uid}@example.com>`, from, to: "me@example.com", cc: "",
  subject, date, unread: false, has_attachments: false, ...extra,
});

// Everything an email can try. Each address is unique, so a test can say exactly what
// was, and was not, requested.
export const HOSTILE_HTML = `<html><head>
<meta http-equiv="refresh" content="0;url=${TRACKER}/refresh">
<base href="${TRACKER}/base/">
<link rel="stylesheet" href="${TRACKER}/style.css">
<style>@import url(${TRACKER}/import.css); body { background: url(${TRACKER}/bg.png); font: 14px system-ui; }</style>
<script>window.__ran = "script"; fetch("${TRACKER}/script");</script>
</head><body>
<p id="hello">You have won. Claim your prize today.</p>
<img src="${TRACKER}/pixel.png" onerror="window.__ran = 'onerror'; fetch('${TRACKER}/onerror')">
<img name="head" src="${TRACKER}/named-head.png">
<img name="documentElement" src="${TRACKER}/named-root.png">
<form name="querySelectorAll" action="${TRACKER}/form"><input name="getAttribute" value="x"></form>
<noscript><style></noscript><a href="${TRACKER}/noscript">Noscript link</a></style></noscript>
<p><a id="plain" href="${TRACKER}/plain">Plain link</a></p>
<p><a id="self" target="_self" href="${TRACKER}/self">Same-frame link</a></p>
<div><template shadowrootmode="closed"><p><a href="${TRACKER}/shadow">Shadow link</a></p></template></div>
<svg width="220" height="28"><a xlink:href="${TRACKER}/svg"><text id="svg-text" x="0" y="20">SVG link</text></a></svg>
<svg width="220" height="28"><a><animate attributeName="href" to="${TRACKER}/smil" fill="freeze"/><text id="smil-text" x="0" y="20">Animated link</text></a></svg>
</body></html>`;

export const MAIL_THREADS = [
  { key: "a1a1a1a1a1a1a1a1", subject: "Plan for Friday", sender: "Ana Lopez <ana@example.com>", date: NOW - 3600, unread: true, count: 2, has_attachments: true },
  { key: "b2b2b2b2b2b2b2b2", subject: "Your invoice for October", sender: "Billing <billing@example.com>", date: NOW - 86400, unread: false, count: 1, has_attachments: false },
  { key: "c3c3c3c3c3c3c3c3", subject: "You have won", sender: "Prize Desk <win@tracker.invalid>", date: NOW - 2 * 86400, unread: false, count: 1, has_attachments: false },
];

const ME = "Me <me@example.com>";
const sent = (uid: number, to: string, subject: string, date: number, extra: object = {}) =>
  envelope(uid, ME, subject, date, { folder: "Sent", to, ...extra });

// Under Sent a row names who the message went to, not who wrote it.
export const MAIL_SENT = [
  { key: "e5e5e5e5e5e5e5e5", subject: "Lunch on Thursday", sender: ME, to: "Ben Carter", date: NOW - 1800, unread: false, count: 1, has_attachments: false },
  { key: "f6f6f6f6f6f6f6f6", subject: "Re: Agenda for the workshop", sender: ME, to: "Ana Lopez, Li Chen", date: NOW - 3 * 86400, unread: false, count: 2, has_attachments: true },
];

export const MAIL_THREAD_MESSAGES: Record<string, ReturnType<typeof envelope>[]> = {
  e5e5e5e5e5e5e5e5: [sent(50, "Ben Carter <ben@example.com>", "Lunch on Thursday", NOW - 1800)],
  f6f6f6f6f6f6f6f6: [
    sent(51, "Ana Lopez <ana@example.com>, Li Chen <li@example.com>", "Agenda for the workshop", NOW - 4 * 86400, { has_attachments: true }),
    sent(52, "Ana Lopez <ana@example.com>, Li Chen <li@example.com>", "Re: Agenda for the workshop", NOW - 3 * 86400),
  ],
  a1a1a1a1a1a1a1a1: [
    envelope(1, "Ana Lopez <ana@example.com>", "Plan for Friday", NOW - 7200),
    envelope(2, "Ana Lopez <ana@example.com>", "Re: Plan for Friday", NOW - 3600, { unread: true, has_attachments: true }),
  ],
  b2b2b2b2b2b2b2b2: [envelope(3, "Billing <billing@example.com>", "Your invoice for October", NOW - 86400)],
  c3c3c3c3c3c3c3c3: [envelope(4, "Prize Desk <win@tracker.invalid>", "You have won", NOW - 2 * 86400)],
};

const message = (key: string, index: number, html: string, text: string, attachments: object[] = []) => ({
  ...MAIL_THREAD_MESSAGES[key][index], thread_key: key, html, text, attachments,
});

export const MAIL_MESSAGES: Record<string, object> = {
  "INBOX/1": message("a1a1a1a1a1a1a1a1", 0, "<p>Can we plan Friday?</p>", "Can we plan Friday?"),
  "INBOX/2": message(
    "a1a1a1a1a1a1a1a1", 1,
    '<p>Hi,</p><p>Shall we meet on <a id="agenda" href="https://example.com/agenda">Friday at ten</a>? The plan is attached.</p>',
    "Hi,\nShall we meet on Friday at ten? The plan is attached.",
    [{ filename: "plan.pdf", content_type: "application/pdf", size: 48213 }],
  ),
  "INBOX/3": message("b2b2b2b2b2b2b2b2", 0, "<p>Your invoice for October is ready.</p>", "Your invoice for October is ready."),
  "INBOX/4": message("c3c3c3c3c3c3c3c3", 0, HOSTILE_HTML, "You have won. Claim your prize today."),
  "Sent/50": message("e5e5e5e5e5e5e5e5", 0, "<p>Hi Ben,</p><p>Are you free for lunch on Thursday at noon?</p>", "Hi Ben,\nAre you free for lunch on Thursday at noon?"),
  "Sent/51": message(
    "f6f6f6f6f6f6f6f6", 0, "<p>Here is the agenda for the workshop.</p>", "Here is the agenda for the workshop.",
    [{ filename: "agenda.docx", content_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", size: 18220 }],
  ),
  "Sent/52": message("f6f6f6f6f6f6f6f6", 1, "<p>One change: we start at nine, not ten.</p>", "One change: we start at nine, not ten."),
  "Archive/40": {
    ...envelope(40, "Billing <billing@example.com>", "Invoice January", NOW - 300 * 86400, { folder: "Archive" }),
    thread_key: "d4d4d4d4d4d4d4d4", html: "<p>Paid in full.</p>", text: "Paid in full.", attachments: [],
  },
};

export const MAIL_SEARCH = [
  envelope(40, "Billing <billing@example.com>", "Invoice January", NOW - 300 * 86400, { folder: "Archive" }),
];
