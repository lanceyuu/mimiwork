# MimiWork desktop privacy notice — draft for publication

Prepared 15 September 2026. This document is not yet the public privacy notice.

MimiWork is provided by QUALITATI, 47 rue Vivienne, 75002 Paris, France.
For privacy questions or requests about data held by QUALITATI, contact
contact@qualitati.com.

## What stays on your computer

The desktop app stores conversation records, preferences, memory and activity
records locally. Outputs are saved in a conversation workspace or a folder you
choose. You can grant additional folders read-only or read-write access. The
interface connects to a backend running on your computer.

Provider keys and connection tokens are held in a local credential file protected
using operating-system file permissions. This file is not an encrypted vault.
Your device's security and any backup or folder-sync services you use also affect
these local copies.

## When information leaves your computer

Cloud model requests send relevant conversation context to the model service you
select. Depending on the task, this can include messages, file contents,
attachments, extracted text or images, tool results and folder paths. A local
workspace does not mean that a cloud model processes information locally.

If you configure a local model endpoint, model processing occurs at that endpoint.
Other enabled features, such as web searches and connected cloud services, can
still send information outside your computer. Requests to websites, model
providers and connected services expose connection information to those services.

Using QualiTaTi account features sends authentication and account requests to the
selected QualiTaTi service. The desktop retains tokens and a personal API
credential for subsequent requests; it does not retain the account password.
The global QualiTaTi and China services use separate accounts and model routes.

Connecting a service or MCP server allows the corresponding operations to send
necessary information to that service. Review the selected service's privacy
terms, permissions and processing location. The desktop's configurable providers
are not all covered by the website's hosting or EU-processing arrangements.

Update checks contact the app's GitHub release endpoint. App distribution and
installation through Microsoft Store are also subject to Microsoft's applicable
privacy notice.

## Local deletion and service-held copies

Deleting a conversation removes its local conversation record and, where
applicable, its managed scratch folder. It does not remove files in a
user-selected project folder or establish deletion of memory, audit records,
backups or copies held by external services. Signing out clears local QualiTaTi
credential profiles and attempts to revoke the remote personal API key. If that
request cannot reach the service, remote revocation may not complete.

Contact QUALITATI about service-held data. For providers or services you configure
independently, their applicable privacy notices and deletion controls govern
copies they hold. Local deletion is not a request to every external service.

## Relationship to the QualiTaTi service notice

The [QualiTaTi privacy policy](https://qualitati.com/privacy-policy) describes
account and hosted-platform processing. Statements there about hosted storage,
encryption and processing regions must not be read as promises about your local
device or every independently configured provider in MimiWork.

---

Publication gate: verify the live service's retention periods, legal bases,
processors (including managed connection relays), international transfers and
rights-request procedures, and incorporate the resulting service disclosures or
a verified explicit reference. Remove this draft status only after that review.
Do not set the Partner Center privacy URL to this draft.
