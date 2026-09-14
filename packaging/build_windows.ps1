#requires -Version 5.1
<#
.SYNOPSIS
  Build the Coworker Windows desktop app + its NSIS (.exe) installer.

.DESCRIPTION
  The Windows counterpart to build_dmg.sh:
    1. PyInstaller-bundle the server into a standalone onedir folder (no venv at runtime).
    2. Stage it at binaries\sidecar\ for Tauri's `resources` slot.
    3. `tauri build --bundles nsis` -> Coworker NSIS setup .exe (resources copied in).

  NSIS only, deliberately (v0.4.19/0.4.20). WiX v3's light.exe is a 32-bit process that
  cabs the whole payload in one go, and the sidecar is ~380 MB across ~10k files. Past
  roughly this size it dies with no error code at all -- two releases burned 45 min of CI
  each producing `failed to run ...\light.exe` and nothing more, while NSIS bundled the
  identical payload in three minutes. NSIS is also what the auto-updater ships, so the
  MSI was a second artifact almost nobody took. Pass -Bundles "nsis,msi" to try it anyway.

  Prerequisites (see the toolchain notes in the PR/plan):
    - Rust (rustup) with the x86_64-pc-windows-msvc target + the MSVC C++ build tools (link.exe).
    - Node + npm (frontend build).
    - A Python venv at platform\.venv with this package installed editable, plus pyinstaller.
      `typer` is needed only at build time: PyInstaller walks the `mcp` package and `mcp.cli`
      calls sys.exit() at import if typer is absent, which aborts the freeze.
        py -m venv .venv ; .\.venv\Scripts\pip install -e ".[bedrock]" pyinstaller tzdata typer

  Release builds require Azure Artifact Signing. See WINDOWS_SIGNING.md.
  Local builds without signing configuration remain unsigned for development.

  Experimental (use-at-your-own-risk) connectors are EXCLUDED from this build by default —
  the spec strips coworker.connectors.experimental. Self-builders can opt in with:
    $env:COWORKER_EXPERIMENTAL = "1"; .\build_windows.ps1
#>
[CmdletBinding()]
param(
    # Which installer bundles to produce. See the MSI note above before adding "msi".
    [string]$Bundles = "nsis",
    [switch]$RequireSigning
)
$ErrorActionPreference = "Stop"

$Here     = Split-Path -Parent $MyInvocation.MyCommand.Path
$Platform = Split-Path -Parent $Here
$Gui      = Join-Path $Platform "surfaces\gui"
$Venv     = Join-Path $Platform ".venv"
$PyInst   = Join-Path $Venv "Scripts\pyinstaller.exe"
$SignScript = Join-Path $Here "sign_windows.ps1"
$SigningNames = @("AZURE_SIGNING_ENDPOINT", "AZURE_SIGNING_ACCOUNT", "AZURE_SIGNING_PROFILE", "WINDOWS_PUBLISHER")
$Configured = @($SigningNames | Where-Object { -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_)) })
$SignWindows = $Configured.Count -eq $SigningNames.Count
if (($RequireSigning -or $Configured.Count -gt 0) -and -not $SignWindows) {
    throw "Windows signing configuration is incomplete. See packaging/WINDOWS_SIGNING.md."
}
if ($RequireSigning -and -not $env:TAURI_SIGNING_PRIVATE_KEY) {
    throw "Release builds require the auto-update signing key as well as Authenticode signing."
}
if ($SignWindows) {
    if (-not (Get-Command pwsh -ErrorAction SilentlyContinue)) { throw "Signing requires PowerShell 7 (pwsh)." }
}

function Require-Cmd($name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "Required tool '$name' not found on PATH. See the prerequisites in this script's header."
    }
}

Require-Cmd rustc
Require-Cmd npm
if (-not (Test-Path $PyInst)) {
    throw "PyInstaller not found at $PyInst. Create the venv and install deps (see header)."
}

# Host target triple, e.g. x86_64-pc-windows-msvc — Tauri's externalBin suffix.
$Triple = (& rustc -vV | Select-String '^host:').ToString().Split()[-1]
$Arch   = $Triple.Split('-')[0]

# A running openworker-server.exe (e.g. a prior sidecar/smoke test) locks the output exe and
# makes PyInstaller's overwrite fail with Access-is-denied. Stop any before bundling.
$running = Get-Process -Name "openworker-server" -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "==> stopping $($running.Count) running openworker-server process(es) holding the output exe"
    $running | Stop-Process -Force
    Start-Sleep -Seconds 1
}

Write-Host "==> [1/3] PyInstaller: bundling openworker-server ($Triple)" -ForegroundColor Cyan
& $PyInst --noconfirm --clean `
    --distpath (Join-Path $Here "dist") --workpath (Join-Path $Here "build") `
    (Join-Path $Here "openworker-server.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }

Write-Host "==> [2/3] staging sidecar resources" -ForegroundColor Cyan
# Onedir bundle (exe + _internal\) ships via Tauri `resources`, landing at <install>\sidecar\
# next to the app exe — onefile's per-launch self-extraction cost seconds of boot splash.
$BinDir = Join-Path $Gui "src-tauri\binaries"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$Src = Join-Path $Here "dist\openworker-server"
$Dst = Join-Path $BinDir "sidecar"
if (Test-Path $Dst) { Remove-Item -Recurse -Force $Dst }
# Clear any stale onefile binary from pre-onedir builds.
Remove-Item -Force (Join-Path $BinDir "openworker-server-$Triple.exe") -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force $Src $Dst
Write-Host "    -> $Dst"

if ($SignWindows) {
    # PyInstaller resources are not covered by Tauri's executable signing hook.
    # Keep valid vendor signatures; sign unsigned native modules for Smart App Control.
    $NativeFiles = @(Get-ChildItem -LiteralPath $Dst -Recurse -File |
        Where-Object { $_.Extension -in @(".exe", ".dll", ".pyd") })
    if (-not (Test-Path -LiteralPath (Join-Path $Dst "openworker-server.exe"))) {
        throw "The staged Python sidecar executable is missing."
    }
    foreach ($NativeFile in $NativeFiles) {
        $Signature = Get-AuthenticodeSignature -LiteralPath $NativeFile.FullName
        if ($Signature.Status -eq "NotSigned" -or $NativeFile.Name -eq "openworker-server.exe") {
            & pwsh -NoProfile -File $SignScript -Path $NativeFile.FullName
            if ($LASTEXITCODE -ne 0) { throw "Sidecar signing failed: $($NativeFile.FullName)" }
        } elseif ($Signature.Status -ne "Valid") {
            throw "Invalid vendor signature: $($NativeFile.FullName) ($($Signature.Status))"
        }
    }
}

Write-Host "==> [3/3] tauri build (--bundles $Bundles)" -ForegroundColor Cyan
# Auto-update artifacts (NSIS setup .exe + minisign .sig): produced only when the updater
# signing key env is present (CI secret TAURI_SIGNING_PRIVATE_KEY). Keyless builds skip
# the overlay so dev builds keep working; keyless RELEASES strand installs without
# auto-update.
$UpdaterArgs = @()
$BundleOverlay = @{}
if ($env:TAURI_SIGNING_PRIVATE_KEY) {
    # Pass the overlay as a FILE: inline JSON loses its quotes through the
    # PowerShell -> npm.cmd -> cmd hop ("key must be a string", v0.1.3 run).
    $BundleOverlay.createUpdaterArtifacts = $true
} else {
    Write-Host "    WARNING: no updater signing key - building WITHOUT auto-update artifacts (not releasable)." -ForegroundColor Yellow
}
if ($SignWindows) {
    $BundleOverlay.publisher = $env:WINDOWS_PUBLISHER
    # Object arguments preserve spaces in checkout paths. Tauri signs its executable,
    # uninstaller and installer before producing the updater's content signature.
    $BundleOverlay.windows = @{
        signCommand = @{
            cmd = "pwsh"
            args = @("-NoProfile", "-File", $SignScript, "-Path", "%1")
        }
    }
}
$Overlay = $null
if ($BundleOverlay.Count -gt 0) {
    $Overlay = Join-Path ([IO.Path]::GetTempPath()) ("mimiwork-windows-" + [guid]::NewGuid() + ".json")
    @{ bundle = $BundleOverlay } | ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $Overlay -Encoding utf8
    $UpdaterArgs = @("--config", $Overlay)
}
Push-Location $Gui
try {
    # Retry the bundle step: tauri downloads the NSIS toolchain from GitHub at bundle
    # time, and a dropped connection there ("An existing connection was forcibly closed
    # by the remote host", v0.4.6 run 32735525435) fails a release that had already
    # compiled cleanly. Two extra attempts cost minutes; a lost release costs a re-tag.
    $Attempts = 3
    for ($i = 1; $i -le $Attempts; $i++) {
        & npm run tauri build -- --bundles $Bundles @UpdaterArgs
        if ($LASTEXITCODE -eq 0) { break }
        if ($i -eq $Attempts) { throw "tauri build failed (exit $LASTEXITCODE) after $Attempts attempts" }
        Write-Host "    tauri build failed (exit $LASTEXITCODE) - retrying ($i/$($Attempts - 1))..." -ForegroundColor Yellow
        Start-Sleep -Seconds (10 * $i)
    }
}
finally {
    Pop-Location
    if ($Overlay) { Remove-Item -LiteralPath $Overlay -Force }
}

$BundleDir = Join-Path $Gui "src-tauri\target\release\bundle"
if ($SignWindows) {
    $Installers = @(Get-ChildItem -Path $BundleDir -Recurse -File -Include *.exe, *.msi)
    if ($Installers.Count -eq 0) { throw "No signed installers were produced." }
    foreach ($Installer in $Installers) {
        $Signature = Get-AuthenticodeSignature -LiteralPath $Installer.FullName
        if ($Signature.Status -ne "Valid" -or -not $Signature.TimeStamperCertificate) {
            throw "Installer is not validly signed and timestamped: $($Installer.FullName)"
        }
        if ($RequireSigning -and -not (Test-Path -LiteralPath ($Installer.FullName + ".sig"))) {
            throw "Installer is missing its auto-update signature: $($Installer.FullName)"
        }
    }
}
Write-Host ""
Write-Host "Done. Installers under: $BundleDir" -ForegroundColor Green
Get-ChildItem -Path $BundleDir -Recurse -Include *.exe, *.msi -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host "  $($_.FullName)" }
