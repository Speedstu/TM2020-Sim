$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'env.ps1')
$scriptFile = Join-Path $PSScriptRoot 'gbx.ps1'
$mapsDir = Join-Path $script:RepoRoot 'local\test-maps'
$maps = @(Get-ChildItem $mapsDir -Filter '*.Map.Gbx' -File -ErrorAction Stop)
if($maps.Count -lt 2){throw "Need at least two test maps"}
$passed=0
foreach($f in $maps) {
 $output=Join-Path $mapsDir ($f.BaseName + '.json')
 & $scriptFile -Command map -Path $f.FullName -Output $output
 if($LASTEXITCODE -ne 0){throw "Parser failure: $($f.Name)"}
 $map=Get-Content $output -Raw | ConvertFrom-Json
 if($map.blocksCount -lt 1){throw "No blocks: $($f.Name)"}
 if($map.blocks.Count -ne $map.blocksCount){throw "Count mismatch: $($f.Name)"}
 if($map.blocks[0].grid.Count -ne 3){throw "Missing numeric grid: $($f.Name)"}
 "PASS map=$($f.Name), blocks=$($map.blocksCount), items=$($map.itemsCount), baked=$($map.bakedBlocksCount)"
 $passed++
}
"PASS: $passed map files."
