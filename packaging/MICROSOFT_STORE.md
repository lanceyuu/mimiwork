# Microsoft Store distribution

MimiWork uses the EXE/MSI submission route under QUALITATI. The existing product
ID is `5ac3ffca-5cb9-4b0f-b6e7-30ca175f9cf9`; do not create another product.

## Build the Store candidate

Run the Release workflow manually with `store_installer=true`. It produces workflow
artifacts only, never a public release. The Windows job calls:

```powershell
./packaging/build_windows.ps1 -RequireSigning -StoreInstaller
```

This rebuilds the Python sidecar, signs native files and the NSIS installer, and
embeds the offline WebView2 installer. It requires the same Azure and updater
credentials as direct releases. The default direct-download build is unchanged.

The workflow currently also builds both Mac targets; those are not Store submissions.

## Before submission

Verify silent installation (`/S`) and silent uninstallation on a clean Windows
machine, including setup without network access and without a preinstalled WebView2
runtime. Confirm startup, loopback backend connection, document creation, and removal.
The embedded runtime does not make cloud AI work offline. Confirm all bundled PE
signatures and the installer timestamp. Do not call a build certification-ready
until these checks actually pass.

Publish the verified candidate at a new immutable HTTPS URL. Never replace a released
installer with this different binary under the same filename and URL. Submit that
specific URL and the tested silent arguments to Partner Center.

Finish the Store logo, actual app screenshots, descriptions, reviewer access,
accurate IARC questionnaire and desktop-specific privacy disclosures. A saved draft
is not a submission and a submission is not approval.

Requirements: https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msi/app-package-requirements
