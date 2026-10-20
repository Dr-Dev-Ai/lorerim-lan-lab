param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination
)
$ErrorActionPreference = 'Stop'
$src = (Resolve-Path -LiteralPath $Source).Path.TrimEnd('\')
$dst = [IO.Path]::GetFullPath($Destination).TrimEnd('\')
if ((Test-Path -LiteralPath $dst) -or $dst.StartsWith($src + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Destination must be a new independent folder.'
}
if (-not (Test-Path -LiteralPath (Join-Path $src 'ModOrganizer.ini'))) { throw 'Not an MO2 installation.' }
$null = New-Item -ItemType Directory -Path $dst
$excluded = @('downloads','cache','webcache','logs','crashDumps','__temp__') | ForEach-Object { Join-Path $src $_ }
$excluded += Get-ChildItem -LiteralPath (Join-Path $src 'profiles') -Directory | ForEach-Object { Join-Path $_.FullName 'saves' }
& robocopy $src $dst /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XJ /MT:4 /XD $excluded /NFL /NDL /NP "/LOG:$dst-copy.log"
if ($LASTEXITCODE -ge 8) { throw "Copy failed: $LASTEXITCODE. Do not launch this incomplete copy." }
@{source=$src; created=(Get-Date).ToUniversalTime().ToString('o'); method='physical copies; no hardlinks'} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dst 'LORERIM_LAB.json') -Encoding utf8
Write-Output "Clone complete: $dst. Run prepare_lab.py before launching MO2."
