Mimi can now save an email as a draft instead of sending it, so you can review and send it from your own mail app.

- **Drafts in every mail connector**: ask Mimi to draft a message and it lands in your Drafts folder, unsent. This works for the Email (IMAP) connector, Gmail and Outlook. Saving a draft asks for your approval, the same as sending.
- **Gmail and Outlook need a new permission**: saving drafts needs a permission that earlier tokens did not include (gmail.compose for Gmail, Mail.ReadWrite for Outlook). If you connected either one before this version, reconnect it with a new access token before drafting; Mimi tells you so plainly instead of showing a raw error. Email (IMAP) accounts need nothing.
