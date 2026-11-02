param([string]$GamePath = 'D:\SteamLibrary\steamapps\common\Trackmania')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$local = Join-Path $root 'local'
New-Item -ItemType Directory -Force -Path $local | Out-Null
$exe = Join-Path $GamePath 'Trackmania.exe'
if(-not (Test-Path $exe)){throw "Trackmania executable not found at $exe"}
$exeInfo=Get-Item $exe
$manifest=Join-Path (Split-Path (Split-Path $GamePath -Parent) -Parent) 'appmanifest_2225070.acf'
$packs = @(Get-ChildItem (Join-Path $GamePath 'Packs') -File -ErrorAction Stop | Sort-Object Name | ForEach-Object {
  [PSCustomObject]@{name=$_.Name;sizeBytes=$_.Length;modifiedUtc=$_.LastWriteTimeUtc.ToString('o');ext=$_.Extension}
})
$gameData = @(Get-ChildItem $GamePath -Recurse -File -ErrorAction Stop | Where-Object {$_.FullName -notmatch '\\Packs\\'} | ForEach-Object {
 [PSCustomObject]@{rel=$_.FullName.Substring($GamePath.Length+1);sizeBytes=$_.Length}
})
$data = [ordered]@{
 format='trackmania2020_inventory_v1';generatedUtc=[datetime]::UtcNow.ToString('o')
 gamePath=$GamePath;version=$exeInfo.VersionInfo.FileVersion
 executableSha256=(Get-FileHash $exe -Algorithm SHA256).Hash
 steamManifest= if(Test-Path $manifest){$manifest}else{$null}
 packsCount=$packs.Count;packsBytes=($packs | Measure-Object sizeBytes -Sum).Sum;packs=$packs
 otherFilesCount=$gameData.Count;otherFiles=$gameData
 }
$output = Join-Path $local 'game-inventory.json'
$data | ConvertTo-Json -Depth 8 | Set-Content $output -Encoding UTF8
"Saved inventory: $output"
"Version: $($data.version) | packs: $($packs.Count) | packs GiB: $([math]::Round($data.packsBytes/1GB,2))"
