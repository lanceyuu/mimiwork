# Windows publisher signing

Status: QUALITATI's public identity validation is completed and the Public Trust
profile `mimiwork-windows` is Active. GitHub federation and the restricted
`windows-signing` environment are configured. The profile signer role has been
assigned, and a real Windows signing run is required before calling any
installer signed.

Provisioned account: `qualitati-signing`, resource group `mimiwork-signing`, North
Europe, endpoint `https://neu.codesigning.azure.net/`. Publisher CN: `QUALITATI`.
The verified identity expires on 17 December 2028. Certificate lifetimes are
separate from identity-validation validity.

## Company setup

1. Use an Azure subscription owned by the publishing company. Register the
   `Microsoft.CodeSigning` resource provider.
2. Create an Artifact Signing account on the Basic plan in an available region
   (this account uses North Europe). Review the current Azure price
   before accepting a paid plan.
3. In Identity validation, select **Public Trust**, **Organization**, and **France**.
   Enter the exact registered legal name, registered address, company registration
   details, website and authorized contact. Complete Microsoft's verification.
   Do not choose Individual or Private Trust for public MimiWork releases.
4. Once approved, create a **Public Trust** certificate profile. Record its account
   name, profile name, endpoint, and exact publisher common name (CN).
   Publisher information is public in downloaded executable signatures.

Microsoft may request additional business evidence. Identity validation is completed
in the portal, not by the release workflow. The verified publisher may be the legal
company name rather than the MimiWork brand.

## GitHub authentication

Create an Entra app registration for MimiWork release signing and a federated identity
credential with:

- Issuer: `https://token.actions.githubusercontent.com`
- Audience: `api://AzureADTokenExchange`
- Subject: `repo:lanceyuu@30419601/mimiwork@1339329582:environment:windows-signing`

This repository uses GitHub immutable subjects, verified with
`gh api repos/lanceyuu/mimiwork/actions/oidc/customization/sub`. Do not substitute
the older name-only subject. The registered app `mimiwork-github-signing` has
client ID `a8892232-ee64-4977-8c74-6f83467ebf46` and service principal object ID
`08fb7368-e6ca-4693-a365-cd6c2a29b21b`.

Grant its service principal **Artifact Signing Certificate Profile Signer** at the
specific certificate profile scope. Do not grant subscription Owner or Contributor
to the release identity. A client secret or exportable certificate key is unnecessary.

Create the GitHub environment `windows-signing`. Restrict deployment branches/tags
to the release tags (`v*`, `app-v*`) and the trusted branch used for manual release
builds. Configure these environment variables:

| Variable | Value |
| --- | --- |
| `AZURE_CLIENT_ID` | Entra app registration application ID |
| `AZURE_TENANT_ID` | Company directory ID |
| `AZURE_SUBSCRIPTION_ID` | Subscription containing the signing account |
| `AZURE_SIGNING_ENDPOINT` | `https://neu.codesigning.azure.net/` |
| `AZURE_SIGNING_ACCOUNT` | Signing account name |
| `AZURE_SIGNING_PROFILE` | Approved Public Trust profile name |
| `WINDOWS_PUBLISHER` | Exact publisher CN from that profile |

Keep the existing `TAURI_SIGNING_PRIVATE_KEY` and its password in repository secrets.
The Windows build requires both kinds of signature. Missing configuration stops CI
before the expensive build. The other matrix entries use the `desktop-build`
environment and existing repository secrets.

## Signing order and checks

`build_windows.ps1 -RequireSigning` freezes the Python sidecar, signs its executable
and unsigned native EXE/DLL/PYD resources, and retains valid vendor signatures.
Invalid vendor signatures fail the build. Tauri's custom signing hook signs the
desktop executable, NSIS uninstaller and installer. Each signing invocation checks
the signature, timestamp and expected company publisher. Tauri then generates the
updater signature from the final installer bytes; never Authenticode-sign an installer
after generating its `.sig`.

The hook uses Microsoft's `ArtifactSigning` PowerShell module, pinned to 0.1.20,
and the Azure CLI credential from `azure/login` (OIDC). SHA-256 and Microsoft's
RFC 3161 timestamp service are explicit. Timestamps matter because the service's
short-lived certificates must remain verifiable after their issuance period.

For a local Windows build, install PowerShell 7 and that module, use `az login`
with a profile signer identity, set the four signing/publisher variables, and call
the same packaging script. Without any signing variables, local development builds
can remain unsigned. Partial configuration always fails.

Before the first signed release, run the authorized Windows build, inspect the
installer and installed executables' Digital Signatures, and test both clean
installation and an update on Windows with Defender and SmartScreen enabled.
Verify the installer `.sig` against the updater public key. Signing establishes
publisher identity; new releases can still receive SmartScreen reputation warnings.

## Microsoft Store follow-up

The existing EXE can use the Store's unpackaged-app submission path. Before
submission, replace the current WebView2 `downloadBootstrapper` mode with an
offline runtime installation strategy, verify silent installation and uninstall,
and audit signatures on every bundled PE file. Submit an immutable, versioned
HTTPS installer URL through a company Partner Center account, with listing assets,
privacy policy, and certification instructions for account-dependent features.
The current signing setup alone does not constitute Store certification.

See [EXE/MSI package requirements](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msi/app-package-requirements).

## References

- [Microsoft setup and organization eligibility](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart)
- [Microsoft signing integrations](https://learn.microsoft.com/en-us/azure/artifact-signing/how-to-signing-integrations)
- [Microsoft signing module](https://www.powershellgallery.com/packages/ArtifactSigning/0.1.20)
- [Tauri Windows signing](https://v2.tauri.app/distribute/sign/windows/)
- [SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation)
