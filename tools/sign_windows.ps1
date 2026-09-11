$ErrorActionPreference = 'Stop'
$path = Join-Path $env:RUNNER_TEMP 'handoff-release.pfx'
$password = ConvertTo-SecureString $env:WINDOWS_CERT_PASSWORD -AsPlainText -Force
$cert = Import-PfxCertificate -FilePath $path -CertStoreLocation Cert:\CurrentUser\My -Password $password
try {
    $tool = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe' | Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $tool) { throw 'Windows SDK signing tool not found' }
    & $tool.FullName sign /sha1 $cert.Thumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 'dist\HandOff\HandOff.exe'
    if ($LASTEXITCODE -ne 0) { throw 'Signing failed' }
    $signature = Get-AuthenticodeSignature 'dist\HandOff\HandOff.exe'
    if ($signature.Status -ne 'Valid') { throw 'Windows signature does not chain to a trusted publisher' }
} finally {
    Remove-Item "Cert:\CurrentUser\My\$($cert.Thumbprint)" -ErrorAction SilentlyContinue
    Remove-Item $path -ErrorAction SilentlyContinue
}
