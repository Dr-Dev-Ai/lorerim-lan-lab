param(
    [Parameter(Mandatory=$true)][string]$Lab,
    [Parameter(Mandatory=$true)][string]$PeerManifest,
    [switch]$HostServer
)
$ErrorActionPreference = 'Stop'
if (Get-Process ModOrganizer -ErrorAction SilentlyContinue) {
    throw 'Close other idle Mod Organizer windows first; MO2 can retain a cross-instance launch lock.'
}
$root = (Resolve-Path -LiteralPath $Lab).Path
if (-not (Test-Path -LiteralPath (Join-Path $root 'LORERIM_LAB.json'))) { throw 'Not a marked isolated lab.' }
$server = Join-Path (Split-Path $root) 'server'
$manifest = Join-Path (Split-Path $root) 'fresh-local-manifest.json'
$report = Join-Path (Split-Path $root) 'peer-comparison.json'
& python (Join-Path $PSScriptRoot 'lancheck.py') snapshot $root 'LoreRim LAN Test' $manifest --full --server-config (Join-Path $server 'config\STServer.ini')
if ($LASTEXITCODE -ne 0) { throw 'Could not create a fresh manifest.' }
& python (Join-Path $PSScriptRoot 'lancheck.py') compare $manifest $PeerManifest $report
if ($LASTEXITCODE -ne 0) { throw "Parity failed; read $report. Nothing launched." }
Write-Output 'File parity passed. Save-resident settings and gameplay compatibility still require verification.'
if ($HostServer) {
    Start-Process -FilePath (Join-Path $server 'SkyrimTogetherServer.exe') -WorkingDirectory $server -WindowStyle Hidden
}
# The MO2 interface is visible for the user to select/run the isolated game.
Start-Process -FilePath (Join-Path $root 'ModOrganizer.exe') -WorkingDirectory $root
