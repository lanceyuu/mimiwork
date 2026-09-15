# Windows acceptance check

Use a disposable Windows PC or VM and the Store candidate from Release run
34992424765, not the normal public v0.6.15 download. Its SHA-256 is
`6808707ADB87700A7367BDDC13640C17A4A1DD8803BE87180F448826D9A2AEDF`.
The publisher must show QUALITATI. Do not disable antivirus or bypass warnings;
record an unexpected block for investigation.

1. Record Windows version and whether WebView2 is already installed. For the
   offline dependency test, start from a clean disposable image without WebView2;
   do not remove system components from your everyday PC.
2. Download the candidate first, then disconnect the test VM's network. Run setup
   with `/S`. Confirm installation succeeds and the app opens. Record any errors.
3. Reconnect the network and configure a supported model or a test QualiTaTi
   account through the app. Never send credentials with the test report.
4. Grant a folder containing these fictional samples. Ask: “Use meeting-notes.txt
   to create an editable Word document with decisions, an action table and open
   questions. Save it in this folder.” Open the resulting document and verify its
   contents and editability.
5. Ask: “Create an Excel workbook from expenses.csv with category totals.” Open
   the workbook. Expected totals: Printing €60, Materials €100, overall €160.
6. Close and reopen MimiWork; confirm the conversation and outputs remain usable.
   Uninstall from Windows Settings. Confirm the app is removed and the chosen
   output folder remains intact.

Report pass/fail per step, Windows/WebView2 versions and the installer hash.
Automated run 34997301027 already passed signature checks and silent
install/uninstall on a hosted runner; it did not cover these interactive/offline
checks. Cloud tasks require a configured service and may consume usage credits.
