$ErrorActionPreference='Stop'
$game='F:\LoreRim-LAN\LoreRim'
$profile=Join-Path $game 'profiles\LoreRim LAN Test'
$stage='F:\LoreRim-LAN\updates\v05'
$package=Join-Path $stage 'package'
$client=Join-Path $game 'mods\LoreRim LAN - Skyrim Together 1.8.3 (1170)\SkyrimTogetherReborn'
$modName='[NoDelete] LoreRim LAN Campaign Update v0.5'
$compatName='[NoDelete] LoreRim LAN Respawn Compatibility'
$mod=Join-Path "$game\mods" $modName
$compat=Join-Path "$game\mods" $compatName
if(Get-Process SkyrimTogether*,SkyrimSE,ModOrganizer -ErrorAction SilentlyContinue){throw 'Close the game and Mod Organizer before installing'}
if(Test-Path -LiteralPath $mod){throw 'Update mod already exists; inspect before repeating'}
$entries=Get-Content "$package\FILES.json" -Raw | ConvertFrom-Json
foreach($entry in $entries){
 $path=Join-Path $package $entry.path
 if(!(Test-Path -LiteralPath $path) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower() -ne $entry.sha256){throw ('Package integrity failure: '+$entry.path)}
}
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$backup=Join-Path 'F:\LoreRim-LAN\update-backups' "v05-$stamp"
New-Item "$backup\client" -ItemType Directory -Force | Out-Null
$originals=@()
foreach($name in @('SkyrimTogether.exe','EarlyLoad.dll')){
 $target=Join-Path $client $name
 $saved=Join-Path "$backup\client" $name
 Copy-Item -LiteralPath $target -Destination $saved
 $originals+=@{target=$target;saved=$saved}
}
$listing=Join-Path $profile 'modlist.txt'
Copy-Item -LiteralPath $listing -Destination "$backup\modlist.txt"
$originals+=@{target=$listing;saved="$backup\modlist.txt"}
$compatExisted=Test-Path -LiteralPath $compat
$compatFile=Join-Path $compat 'autoxec_load.txt'
$compatFileExisted=Test-Path -LiteralPath $compatFile
if($compatFileExisted){
 Copy-Item -LiteralPath $compatFile -Destination "$backup\autoxec_load.txt"
 $originals+=@{target=$compatFile;saved="$backup\autoxec_load.txt"}
}
Copy-Item -LiteralPath "$profile\saves" -Destination "$backup\saves" -Recurse
foreach($entry in $originals){
 if((Get-FileHash -LiteralPath $entry.target -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $entry.saved -Algorithm SHA256).Hash){throw 'Original-file backup verification failed'}
}
$saves=@(Get-ChildItem "$profile\saves" -File)
foreach($save in $saves){
 if((Get-FileHash -LiteralPath $save.FullName -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath (Join-Path "$backup\saves" $save.Name) -Algorithm SHA256).Hash){throw 'Save backup verification failed'}
}
Write-Output 'Verified backups of both client binaries, profile configuration and all saves'
try {
 foreach($name in @('SkyrimTogether.exe','EarlyLoad.dll')){Copy-Item -LiteralPath "$package\client\$name" -Destination (Join-Path $client $name) -Force}
 New-Item -Path (Join-Path $mod 'Scripts') -ItemType Directory -Force | Out-Null
 foreach($source in Get-ChildItem "$package\scripts" -Filter '*.pex'){
  Copy-Item -LiteralPath $source.FullName -Destination (Join-Path "$mod\Scripts" $source.Name)
 }
 New-Item -Path (Join-Path $mod 'SKSE\Plugins') -ItemType Directory -Force | Out-Null
 Copy-Item -LiteralPath "$package\companion\SKSE\Plugins\LoreRimCampaignCosave.dll" -Destination "$mod\SKSE\Plugins\LoreRimCampaignCosave.dll"
 Copy-Item -LiteralPath "$package\templates\LoreRimCampaign.ini" -Destination "$mod\SKSE\Plugins\LoreRimCampaign.ini"
 if(Test-Path "$package\compatibility\autoxec_load.txt"){
  if(!$compatExisted){New-Item -Path $compat -ItemType Directory | Out-Null}
  Copy-Item -LiteralPath "$package\compatibility\autoxec_load.txt" -Destination $compatFile -Force
 }
 $raw=[IO.File]::ReadAllBytes($listing)
 $bom=$raw.Length -ge 3 -and $raw[0] -eq 239 -and $raw[1] -eq 187 -and $raw[2] -eq 191
 $lines=[Collections.Generic.List[string]]::new()
 foreach($line in [IO.File]::ReadAllLines($listing)){if($line -ne ('+'+$modName) -and $line -ne ('-'+$modName) -and $line -ne ('+'+$compatName) -and $line -ne ('-'+$compatName)){$lines.Add($line)}}
 $position=0
 while($position -lt $lines.Count -and $lines[$position].StartsWith('#')){$position++}
 $lines.Insert($position,('+'+$modName));$lines.Insert($position+1,('+'+$compatName))
 [IO.File]::WriteAllLines($listing,$lines,[Text.UTF8Encoding]::new($bom))
 $verified=@()
 foreach($entry in $entries){
  if($entry.path.StartsWith('client/')){$target=Join-Path $client ([IO.Path]::GetFileName($entry.path))}
  elseif($entry.path.StartsWith('scripts/')){$target=Join-Path "$mod\Scripts" ([IO.Path]::GetFileName($entry.path))}
  elseif($entry.path.StartsWith('companion/')){$target=Join-Path $mod $entry.path.Substring(10)}
  elseif($entry.path.StartsWith('templates/')){$target=Join-Path "$mod\SKSE\Plugins" ([IO.Path]::GetFileName($entry.path))}
  elseif($entry.path.StartsWith('compatibility/')){$target=$compatFile}
  else{throw 'Unexpected package member'}
  $hash=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower()
  if($hash -ne $entry.sha256){throw ('Installed-file verification failure: '+$entry.path)}
  $verified+=@{file=$entry.path;sha256=$hash}
 }
 $report=[pscustomobject]@{applied=$true;build='lorerim-campaign-bridge-v0.5-staged';game=$game;backup=$backup;savesBackedUp=$saves.Count;campaignGuardEnabled=$false;enrollmentPending=$true;verifiedFiles=$verified}
 $report | ConvertTo-Json -Depth 5 | Set-Content "$backup\APPLIED.json" -Encoding utf8
 $report | ConvertTo-Json -Depth 5 | Set-Content "$stage\APPLIED.json" -Encoding utf8
 $report | ConvertTo-Json -Depth 5
} catch {
 foreach($entry in $originals){Copy-Item -LiteralPath $entry.saved -Destination $entry.target -Force}
 if(Test-Path -LiteralPath $mod){Remove-Item -LiteralPath $mod -Recurse -Force}
 if(!$compatExisted -and (Test-Path -LiteralPath $compat)){Remove-Item -LiteralPath $compat -Recurse -Force}
 elseif(!$compatFileExisted -and (Test-Path -LiteralPath $compatFile)){Remove-Item -LiteralPath $compatFile -Force}
 'Installed files restored after update failure' | Set-Content "$backup\ROLLED_BACK.txt"
 throw
}
