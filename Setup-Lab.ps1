param([string]$Source, [string]$Destination)
$ErrorActionPreference = 'Stop'
$adapter = Join-Path $PSScriptRoot 'adapter\BSAMemoryMap.dll'
if (-not (Test-Path -LiteralPath $adapter)) {
    throw 'Use the complete guided installer release (includes the tested adapter), not the GitHub source ZIP.'
}
if (-not $Source) { $Source = Read-Host 'Folder containing your LoreRim ModOrganizer.exe (not just downloads)' }
if (-not $Destination) { $Destination = Read-Host 'NEW lab folder, preferably a short path such as D:\LoreRim-LAN\LoreRim' }
$Source = (Resolve-Path -LiteralPath $Source).Path
$Destination = [IO.Path]::GetFullPath($Destination)
if ($Destination.TrimEnd('\').Equals($Source.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase) -or
    $Destination.StartsWith($Source.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -or
    $Source.StartsWith($Destination.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Source and lab must be separate, non-overlapping trees.'
}
if ((Get-Item -LiteralPath (Join-Path $Source 'Stock Game\SkyrimSE.exe')).VersionInfo.FileVersion -ne '1.6.1170.0') {
    throw 'This experimental setup is pinned to Skyrim 1.6.1170.0. Do not upgrade/downgrade the modpack blindly.'
}
& python -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ is required.' }
if (Test-Path -LiteralPath $Destination) { throw 'Lab destination must not exist.' }
if ($Destination.Length -gt 60) { throw 'Choose a shorter destination to avoid native mod path-length failures.' }
$parent = Split-Path $Destination
if (-not (Test-Path -LiteralPath $parent)) { $null=New-Item -ItemType Directory -Path $parent }
$backup = Join-Path $parent ('original-profile-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$null = New-Item -ItemType Directory -Path $backup
Copy-Item -LiteralPath (Join-Path $Source 'ModOrganizer.ini') -Destination $backup
& robocopy (Join-Path $Source 'profiles') (Join-Path $backup 'profiles') /E /COPY:DAT /R:1 /W:1 /XJ /NFL /NDL /NP
if ($LASTEXITCODE -ge 8) { throw 'Profile/save backup failed.' }
& (Join-Path $PSScriptRoot 'clone_lab.ps1') -Source $Source -Destination $Destination
$zip = Join-Path $parent 'STR-1.8.3-for-1.6.1170.zip'
$url = 'https://github.com/tiltedphoques/TiltedEvolution/releases/download/v1.8.3/SkyrimTogether-1.8.3-windows-x64-for-1.6.1170.zip'
Invoke-WebRequest -Uri $url -OutFile $zip
$expected = '0b2f7edcaed6152541092a1fda759de2f407985523d69a87c9cddf0ebf9b5996'
if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower() -ne $expected) { throw 'Upstream archive hash mismatch; not extracting.' }
$package = Join-Path $parent 'STR-1.8.3-for-1.6.1170'
if (Test-Path -LiteralPath $package) { throw 'Upstream extraction folder exists; review before reusing it.' }
Expand-Archive -LiteralPath $zip -DestinationPath $package
& python (Join-Path $PSScriptRoot 'prepare_lab.py') $Source $Destination $package
if ($LASTEXITCODE -ne 0) { throw 'Configuration failed. Do not launch an incomplete lab.' }
foreach ($fix in @('camera_fix.py','blink_fix.py','alttab_fix.py','transport_fix.py','jcontainers_update.py')) {
    & python (Join-Path $PSScriptRoot $fix) $Destination
    if ($LASTEXITCODE -ne 0) { throw "Compatibility setup failed at $fix. Do not launch an incomplete lab." }
}
& python (Join-Path $PSScriptRoot 'bsa_guard_fix.py') $Destination --adapter $adapter
if ($LASTEXITCODE -ne 0) { throw 'BSA compatibility setup failed. Do not launch an incomplete lab.' }
Write-Output 'Lab and all compatibility fixes installed. Follow TESTING before playing together. Original saves remain separate.'
