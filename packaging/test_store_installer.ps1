param([Parameter(Mandatory=$true)][string]$ArtifactDirectory)
$ErrorActionPreference = 'Stop'
$files = @(Get-ChildItem $ArtifactDirectory -Recurse -Filter '*_x64-setup.exe')
if ($files.Count -ne 1) { throw 'Expected exactly one versioned installer' }
$installer = $files[0]
$signature = Get-AuthenticodeSignature $installer.FullName
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(^|,\s*)CN=QUALITATI(,|$)' -or -not $signature.TimeStamperCertificate) {
    throw 'Installer must have a valid timestamped QUALITATI signature'
}
# Use a disposable runner directory; never uninstall an existing user installation.
$installDir = Join-Path $env:RUNNER_TEMP 'MimiWorkStoreValidation'
if (Test-Path $installDir) { throw 'Validation directory already exists' }
$evidence = [ordered]@{
    installer = $installer.Name
    sha256 = (Get-FileHash $installer.FullName -Algorithm SHA256).Hash
    publisher = $signature.SignerCertificate.Subject
    timestampSubject = $signature.TimeStamperCertificate.Subject
    environment = 'GitHub-hosted windows-latest; networking and preinstalled WebView2 unchanged'
    cleanOfflineRuntimeTest = 'NOT TESTED'
    guiAndDocumentWorkflow = 'NOT TESTED'
}
try {
    $p = Start-Process $installer.FullName -ArgumentList "/S /D=$installDir" -PassThru
    if (-not $p.WaitForExit(300000)) { $p.Kill(); throw 'Silent installation timed out' }
    $evidence.installExitCode = $p.ExitCode
    if ($p.ExitCode -ne 0) { throw "Silent installation failed: $($p.ExitCode)" }
    $apps = @(Get-ChildItem $installDir -Filter '*.exe' | Where-Object Name -NotMatch 'uninstall')
    if ($apps.Count -eq 0) { throw 'Installed app executable not found' }
    $sidecar = @(Get-ChildItem $installDir -Recurse -Filter 'openworker-server.exe')
    if ($sidecar.Count -ne 1) { throw 'Installed Python sidecar not found' }
    $invalid = @(Get-ChildItem $installDir -Recurse -File | Where-Object Extension -In '.exe','.dll','.pyd' | ForEach-Object {
        $sig = Get-AuthenticodeSignature $_.FullName
        if ($sig.Status -ne 'Valid') { $_.FullName }
    })
    $evidence.invalidNativeSignatures = $invalid
    if ($invalid.Count) { throw 'Installed native file signature validation failed' }
    $license = Join-Path $installDir 'licenses\MimiWork-LICENSE.txt'
    if (-not (Test-Path $license) -or (Get-Content $license -Raw) -notmatch 'MimiWork Application License') {
        throw 'Application license missing from installed resources'
    }
    $uninstallers = @(Get-ChildItem $installDir -Filter '*uninstall*.exe')
    if ($uninstallers.Count -ne 1) { throw 'Expected one uninstaller' }
    # NSIS _?= avoids its temporary self-copy, so WaitForExit observes actual removal.
    $u = Start-Process $uninstallers[0].FullName -ArgumentList "/S _?=$installDir" -PassThru
    if (-not $u.WaitForExit(180000)) { $u.Kill(); throw 'Silent uninstall timed out' }
    $evidence.uninstallExitCode = $u.ExitCode
    if ($u.ExitCode -ne 0) { throw "Silent uninstall failed: $($u.ExitCode)" }
    foreach ($app in $apps) { if (Test-Path $app.FullName) { throw 'Application executable remained after uninstall' } }
    if (Test-Path $sidecar[0].FullName) { throw 'Sidecar remained after uninstall' }
    $evidence.result = 'PASS'
} catch {
    $evidence.result = 'FAIL'
    $evidence.error = $_.Exception.Message
    throw
} finally {
    $evidence | ConvertTo-Json -Depth 5 | Set-Content store-validation.json
    if ($env:GITHUB_STEP_SUMMARY) {
        "Installer validation: $($evidence.result). Clean offline runtime setup and GUI workflows are not covered by this run." | Out-File $env:GITHUB_STEP_SUMMARY -Append
    }
}
