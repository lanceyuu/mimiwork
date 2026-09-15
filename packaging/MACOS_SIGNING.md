# macOS signing and notarization

Preparation status, 15 September 2026: the Apple Developer app displayed a paid
membership under Fengming Liu, valid through 15 September 2027. The browser account
did not have certificate access. The enrolled team's ID, membership type, and
certificate identity remain unverified. `security find-identity -v -p codesigning`
found zero valid identities on this Mac. No Apple secrets were configured in GitHub
at the last check. No newly signed or notarized Mac build has been verified.

## Resume when the account is available

1. Sign in to the Apple Developer account that owns the membership. Confirm its
   team ID and whether the team is an individual or QUALITATI organization.
2. Check existing **Developer ID Application** certificates before creating one.
   A certificate must have its matching private key available to this build process.
   A membership receipt, team ID, or downloaded `.cer` alone is insufficient.
3. If needed, create a certificate signing request on the machine that will retain
   the private key, obtain the Developer ID Application certificate, and import it.
   Apple documents Account Holder access for creating these certificates.
4. Export that certificate and private key as a password-protected `.p12` for CI.
   Confirm the actual signing identity with `security find-identity -v -p codesigning`.
   Do not invent the team ID or assume the publisher will be QUALITATI.
5. Prepare notarization authentication. The current workflow expects an App Store
   Connect team API key with its `.p8`, key ID, and issuer ID. Confirm the enrolled
   account can create/use this key. Other authentication methods require adapting
   the workflow and the DMG finishing step before use.
6. Store the credentials directly in GitHub Actions secrets for `lanceyuu/mimiwork`.
   Never put private keys or passwords into source control, brain notes, or chat.

## Existing GitHub secret mapping

| Secret | Contents |
| --- | --- |
| `APPLE_CERTIFICATE` | Base64-encoded `.p12` containing certificate and private key |
| `APPLE_CERTIFICATE_PASSWORD` | Password for that `.p12` |
| `APPLE_SIGNING_IDENTITY` | Exact `Developer ID Application: … (TEAMID)` identity |
| `APPLE_API_KEY_CONTENT` | Base64-encoded notarization API `.p8` |
| `APPLE_API_KEY` | API key ID |
| `APPLE_API_ISSUER` | API issuer ID |

The macOS jobs use the `desktop-build` environment and can read repository secrets.
`TAURI_SIGNING_PRIVATE_KEY` and its password are separate updater secrets already
configured. Retain them; Apple signing does not replace updater signing.

## Existing build path

Always use `bash packaging/build_dmg.sh` for an authorized build. It rebuilds the
Python sidecar, stages standalone native files, signs nested Mach-O files with
hardened runtime and timestamps, then builds the Tauri application. The script
imports the CI certificate into a temporary keychain when supplied. The release
workflow decodes the API key into `APPLE_API_KEY_PATH` for Tauri and the DMG step.

The finishing step signs the DMG, submits it with `notarytool`, staples its ticket,
and checks Gatekeeper acceptance. With missing Apple credentials, the current
scripts still permit unsigned or incompletely notarized development output;
therefore a green build alone must not be treated as proof of Apple verification.
`OCW_SKIP_NOTARIZE=1` is only for local iteration, never a public distribution.

Before enabling a public signed release, require complete Apple credentials and
successful notarization in the release path. Review the existing unsigned-Mac
release instructions once both architectures have passed the checks below.

## First-build acceptance

- Confirm both Apple Silicon and Intel jobs used the intended Developer ID team.
- Confirm `notarytool` reports Accepted and the ticket is stapled successfully.
- Verify the downloaded app with `codesign --verify --deep --strict --verbose=2`
  and `spctl --assess --type execute --verbose=2`, supplying its actual app path.
- Validate the downloaded DMG using `xcrun stapler validate` and Gatekeeper's
  `spctl --assess --type open --context context:primary-signature` with its path.
- Test a clean downloaded installation, microphone access, sidecar launch, and an
  update. Verify updater signatures against the existing public key.
- Only then record the Mac release as signed and notarized. This is distribution
  outside the Mac App Store, not an App Store submission or approval.

No build, tag, push, or release is authorized merely by preparing these notes.

## Reference

[Apple: Developer ID certificates](https://developer.apple.com/help/account/certificates/create-developer-id-certificates/)
distinguishes Developer ID Application (apps) from Developer ID Installer (installer
packages). MimiWork currently distributes a DMG containing an app, not a PKG.
