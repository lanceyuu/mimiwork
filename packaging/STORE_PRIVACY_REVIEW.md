# MimiWork desktop privacy review

Technical findings for the public privacy notice, checked against source commit
4b4164c on 15 September 2026. This is a preparation document, not a published policy.
Do not mark the Store privacy requirement complete merely because this file exists.

## Desktop text supported by the current implementation

MimiWork keeps conversation records, preferences, memory and activity records on
your computer. Files it creates are saved in the conversation workspace or a folder
you choose. Additional folder grants can be read-only or read-write. Its desktop
interface communicates with a local backend on the loopback interface.

When you use a cloud AI model, the conversation context needed for that request is
sent to the selected provider or gateway. This may include prompts, previous
messages, attachments, extracted document content, tool results and folder paths.
A local desktop workspace does not mean that cloud AI processing stays on your
computer. Local model processing depends on the endpoint you configure; web tools,
cloud connectors and other network features can still contact external services.

Signing in to QualiTaTi sends your login information to the selected QualiTaTi
service. The desktop stores authentication tokens and a personal API credential
for subsequent account and model requests; it does not store the sign-in password.
The global QualiTaTi service and the China service have separate accounts and
model routes. Account/profile and credit requests go to the selected service.

Configured model and connector credentials are stored locally. The current store
is a file protected using operating-system permissions, not an encrypted vault or
an OS keychain. Connector and MCP services receive information needed for the
operations you invoke. The permissions and data processing of each connected
service also apply.

Deleting a conversation removes its local conversation record and, where
applicable, its managed scratch folder. User-selected project folders are not
removed by that operation. It does not establish deletion of all related local
memory/audit records, backup copies, or copies held by external services. Signing
out clears the local QualiTaTi credential profiles and attempts to revoke the
remote personal API key; revocation can fail while offline.

Update checks contact the configured GitHub release endpoint. Network services
also receive the connection information inherent in their requests. No claim
about server retention, training use or processing region is made here.

## Evidence in this repository

| Finding | Source |
| --- | --- |
| Platform state locations and file-backed credential protection | `coworker/secrets.py` |
| Local conversation, memory and activity stores | `coworker/server/manager.py`, `coworker/conversations.py` |
| Granted folder scope | `coworker/roots.py` |
| Per-model provider selection | `coworker/providers/router.py`, `coworker/providers/registry.py` |
| QualiTaTi authentication, routing and sign-out | `coworker/qualitati.py` |
| Local HTTP/WebSocket authentication | `surfaces/gui/src/api.ts`, `coworker/server/run.py` |
| Direct-download updater endpoint | `surfaces/gui/src-tauri/tauri.conf.json` |

## Still to verify before publishing the notice

Check the deployed QualiTaTi services and the existing public privacy policy for
actual controller details, purposes/legal bases, retention, deletion procedures,
processor/relay arrangements, international transfers and provider training terms.
Inventory managed connector relays and hosted skill services as well as direct
provider calls. Reconcile those facts with the desktop text above; do not inherit
an “EU-only” or “everything stays local” statement from another product.

Provide a live public notice that explicitly covers MimiWork and link that exact
URL in Partner Center. Existing URL in the draft is
https://qualitati.com/privacy-policy. Its desktop coverage remains unverified.
