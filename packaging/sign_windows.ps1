#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Path)
$ErrorActionPreference = "Stop"

foreach ($name in @("AZURE_SIGNING_ENDPOINT", "AZURE_SIGNING_ACCOUNT", "AZURE_SIGNING_PROFILE", "WINDOWS_PUBLISHER")) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Missing $name. See packaging/WINDOWS_SIGNING.md."
    }
}
$File = (Get-Item -LiteralPath $Path).FullName
Import-Module ArtifactSigning -RequiredVersion 0.1.20 -ErrorAction Stop
# Use the short-lived Azure CLI session established by azure/login through GitHub OIDC.
$Signing = @{
    Endpoint = $env:AZURE_SIGNING_ENDPOINT
    CodeSigningAccountName = $env:AZURE_SIGNING_ACCOUNT
    CertificateProfileName = $env:AZURE_SIGNING_PROFILE
    Files = $File
    FileDigest = "SHA256"
    TimestampRfc3161 = "http://timestamp.acs.microsoft.com"
    TimestampDigest = "SHA256"
    ExcludeEnvironmentCredential = $true
    ExcludeWorkloadIdentityCredential = $true
    ExcludeManagedIdentityCredential = $true
    ExcludeSharedTokenCacheCredential = $true
    ExcludeVisualStudioCredential = $true
    ExcludeVisualStudioCodeCredential = $true
    ExcludeAzureCliCredential = $false
    ExcludeAzurePowerShellCredential = $true
    ExcludeAzureDeveloperCliCredential = $true
    ExcludeInteractiveBrowserCredential = $true
}
Invoke-ArtifactSigning @Signing
$Signature = Get-AuthenticodeSignature -LiteralPath $File
if ($Signature.Status -ne "Valid" -or -not $Signature.TimeStamperCertificate) {
    throw "Signing did not produce a valid timestamped signature: $File ($($Signature.Status))"
}
$Publisher = $Signature.SignerCertificate.GetNameInfo(
    [System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
if ($Publisher -cne $env:WINDOWS_PUBLISHER) {
    throw "Signing publisher '$Publisher' does not match WINDOWS_PUBLISHER."
}
