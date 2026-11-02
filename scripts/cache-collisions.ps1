$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$env:TEMP=Join-Path $root 'cache\temp'
$env:TMP=$env:TEMP
$env:PYTHONDONTWRITEBYTECODE='1'
$exe=Join-Path $root 'bin\trackray.exe'
if(-not (Test-Path $exe)){throw 'Raycaster executable not compiled'}
foreach($id in 365553,364956) {
  $path=Join-Path $root "local\collision\$id"
  $obj=Join-Path $path 'embedded_physical_shapes.obj'
  $binary=Join-Path $path 'embedded_physical_shapes.tmcol'
  & $exe $obj --cache $binary
  if($LASTEXITCODE -ne 0){throw "Unable to cache geometry $id"}
}
& python (Join-Path $PSScriptRoot 'test-collision-cache.py')
if($LASTEXITCODE -ne 0){throw 'Cached raycaster not identical to OBJ'}
Write-Output 'PASS binary collision cache generated and 2400 ray queries identical'
