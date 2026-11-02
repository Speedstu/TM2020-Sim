[CmdletBinding()]
param([string]$GamePath = "")
$ErrorActionPreference = "SilentlyContinue"
$roots = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
if ($GamePath) { [void]$roots.Add($GamePath) }
$known = @(
  "C:\Program Files (x86)\Steam\steamapps\common\Trackmania",
  "C:\Program Files (x86)\Ubisoft\Ubisoft Game Launcher\games\Trackmania",
  "C:\Program Files\Ubisoft\Ubisoft Game Launcher\games\Trackmania"
)
foreach($p in $known){[void]$roots.Add($p)}
foreach($drv in (Get-PSDrive -PSProvider FileSystem)){
  foreach($sub in @('SteamLibrary\steamapps\common\Trackmania','Steam\steamapps\common\Trackmania','Ubisoft\Ubisoft Game Launcher\games\Trackmania','Games\Trackmania','Trackmania')){
     [void]$roots.Add((Join-Path $drv.Root $sub))
  }
}
$steamVdf = Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Steam\steamapps\libraryfolders.vdf'
if(Test-Path $steamVdf){
  $contents = Get-Content $steamVdf -Raw
  foreach($m in [regex]::Matches($contents, '"path"\s+"([^"]+)"')){
    $path = $m.Groups[1].Value -replace '\\\\','\'
    [void]$roots.Add((Join-Path $path 'steamapps\common\Trackmania'))
  }
}
$found = @()
foreach ($root in $roots){
 if(Test-Path -LiteralPath $root -PathType Container){
    $exe = Get-ChildItem -LiteralPath $root -Filter 'Trackmania.exe' -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if($exe){
      $found += [pscustomobject]@{Path=$root; Exe=$exe.FullName; Size=$exe.Length; Version=$exe.VersionInfo.FileVersion}
    }
 }
}
if($found.Count -eq 0) {
  'STATUS: NOT_INSTALLED_OR_NOT_FOUND'
  'If installed in a custom directory, call: .\scripts\detect-game.ps1 -GamePath "X:\your\Trackmania"'
} else {
  'STATUS: GAME_FOUND'
  $found | Format-List | Out-String
}
