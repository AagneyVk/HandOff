$ErrorActionPreference = 'Stop'
$destination = Join-Path $env:RUNNER_TEMP 'HandOff-installed'
$state = Join-Path $env:LOCALAPPDATA 'HandOff'
New-Item -ItemType Directory -Force $state | Out-Null
$marker = Join-Path $state 'installer-test-marker'
Set-Content $marker 'preserve pairing directory'
$installer = (Resolve-Path 'dist/installer/HandOff-Setup.exe').Path
foreach ($attempt in 1..2) {
    $process = Start-Process -FilePath $installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=`"$destination`"") -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer exited $($process.ExitCode)" }
    if (!(Test-Path $marker)) { throw 'Upgrade removed app data' }
    python tools/smoke_windows.py (Join-Path $destination 'HandOff.exe')
    if ($LASTEXITCODE -ne 0) { throw 'Installed app failed to launch' }
}
$uninstaller = Join-Path $destination 'unins000.exe'
$process = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'Uninstall failed' }

if (!(Test-Path $marker)) { throw 'Uninstall removed app data' }
Remove-Item $marker
