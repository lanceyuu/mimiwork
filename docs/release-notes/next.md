Email sent by Mimi now shows up in your Sent folder, so a message that went out no longer looks as if it failed.

- **Sent email is filed**: some mail hosts, such as Namecheap Private Email, iCloud and most cPanel hosts, do not keep a copy of messages sent from other apps. Mimi now files a copy in your Sent folder itself after the message is delivered. Gmail and Microsoft already do this, so they are left alone and you get no duplicate.
- **No false failures**: before, Mimi could look in Sent, find nothing, and tell you the send had failed even though the recipient had the message. If filing the copy goes wrong, Mimi now says so, and the message still counts as sent, so it is never sent twice.
