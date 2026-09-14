# Run with pwsh -NoProfile -File packaging/test_windows_signing.ps1.
# These tests never contact Azure or modify a real executable.
$ErrorActionPreference = "Stop"
$SignScript = Join-Path $PSScriptRoot "sign_windows.ps1"
$Fixture = New-TemporaryFile
$Names = @("AZURE_SIGNING_ENDPOINT", "AZURE_SIGNING_ACCOUNT", "AZURE_SIGNING_PROFILE", "WINDOWS_PUBLISHER")
$Previous = @{}
foreach ($Name in $Names) {
    $Previous[$Name] = [Environment]::GetEnvironmentVariable($Name)
    [Environment]::SetEnvironmentVariable($Name, "fixture")
}
$env:WINDOWS_PUBLISHER = "Example Company"

function Import-Module { param($Name, $RequiredVersion, $ErrorAction) }
function Invoke-ArtifactSigning {
    if ($Signing.FileDigest -ne "SHA256" -or $Signing.TimestampDigest -ne "SHA256" -or
        $Signing.TimestampRfc3161 -ne "http://timestamp.acs.microsoft.com" -or
        $Signing.ExcludeAzureCliCredential -ne $false -or
        $Signing.ExcludeEnvironmentCredential -ne $true) {
        throw "Signing must use SHA-256, timestamping and the Azure CLI identity."
    }
    if ($global:MimiSigningTestServiceFails) { throw "Fixture service failure" }
    $global:MimiSigningTestCalls++
}
function Get-AuthenticodeSignature { param($LiteralPath) return $global:MimiSigningTestResult }
function Expect-Rejection([string]$Reason) {
    $Rejected = $false
    try { & $SignScript -Path $Fixture.FullName } catch { $Rejected = $true }
    if (-not $Rejected) { throw "Expected rejection: $Reason" }
    Write-Host "PASS: $Reason"
}

try {
    $Certificate = [pscustomobject]@{}
    $Certificate | Add-Member ScriptMethod GetNameInfo { param($Type, $Issuer) return $global:MimiSigningTestCompany }
    $global:MimiSigningTestCompany = "Example Company"
    $global:MimiSigningTestCalls = 0
    $global:MimiSigningTestServiceFails = $false
    $global:MimiSigningTestResult = [pscustomobject]@{
        Status = "Valid"; TimeStamperCertificate = $true; SignerCertificate = $Certificate
    }
    & $SignScript -Path $Fixture.FullName
    if ($global:MimiSigningTestCalls -ne 1) { throw "The valid artifact was not signed exactly once." }
    Write-Host "PASS: valid timestamped company signatures are accepted"

    $global:MimiSigningTestResult.Status = "HashMismatch"
    Expect-Rejection "tampered signatures fail"
    $global:MimiSigningTestResult.Status = "Valid"
    $global:MimiSigningTestResult.TimeStamperCertificate = $null
    Expect-Rejection "missing timestamps fail"
    $global:MimiSigningTestResult.TimeStamperCertificate = $true
    $global:MimiSigningTestCompany = "Wrong Company"
    Expect-Rejection "the wrong publisher fails"
    $global:MimiSigningTestCompany = "Example Company"
    $global:MimiSigningTestServiceFails = $true
    Expect-Rejection "service failures cannot silently produce unsigned releases"
    $global:MimiSigningTestServiceFails = $false
    $Before = $global:MimiSigningTestCalls
    $env:AZURE_SIGNING_PROFILE = ""
    Expect-Rejection "incomplete configuration fails before signing"
    if ($global:MimiSigningTestCalls -ne $Before) { throw "Signing ran without configuration." }
} finally {
    Remove-Item -LiteralPath $Fixture.FullName
    foreach ($Name in $Names) { [Environment]::SetEnvironmentVariable($Name, $Previous[$Name]) }
}
