param([switch]$SkipBuild)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$build=Join-Path $root 'native\build'
$exe='D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'
$fixtures=Join-Path $root 'local\recon\main-step-fixtures-v5'
$inputs=Join-Path $root 'local\recon\original-step-native-v5'
$results=Join-Path $root 'local\recon\original-step-native-results-v5'
function Assert-OriginalExit([string]$message){if($LASTEXITCODE -ne 0){throw $message}}
if(!$SkipBuild){
 & cmake -S (Join-Path $root 'native') -B $build -G 'MinGW Makefiles' -DCMAKE_BUILD_TYPE=Release
 Assert-OriginalExit 'Original main-step configure failed'
 & cmake --build $build --target tm2020_original_step_native --parallel 6
 Assert-OriginalExit 'Original main-step build failed'
}
& python (Join-Path $PSScriptRoot 'test_original_step_fixture.py')
Assert-OriginalExit 'Original main-step fixture corruption tests failed'
$paths=@(Get-ChildItem -LiteralPath $fixtures -Filter '*.tmstep' | Sort-Object Name | Select-Object -ExpandProperty FullName)
if($paths.Count -ne 2){throw 'Expected the retained inactive and active main-step references'}
& python (Join-Path $PSScriptRoot 'replay_original_step.py') --exe $exe --fixtures $paths --report (Join-Path $root 'local\recon\original-step-offline-v5.json')
Assert-OriginalExit 'Every-frame original main-step offline replay failed'
New-Item -ItemType Directory -Force $results | Out-Null
foreach($path in $paths){
 $name=[IO.Path]::GetFileNameWithoutExtension($path)
 $inputPath=Join-Path $inputs ($name+'.tmstepnative')
 & python (Join-Path $PSScriptRoot 'compile_original_step_fixture.py') --fixture $path --exe $exe --output $inputPath --report (Join-Path $results ($name+'-input.json')) --verify-existing
 Assert-OriginalExit ('Original main-step native input verification failed: '+$name)
 & (Join-Path $build 'tm2020_original_step_native.exe') $exe $inputPath (Join-Path $results ($name+'.json'))
 Assert-OriginalExit ('Every-frame original main-step native comparison failed: '+$name)
}
& python (Join-Path $PSScriptRoot 'audit_original_step.py') --capture (Join-Path $root 'local\recon\original-step-capture-v5.json') --offline (Join-Path $root 'local\recon\original-step-offline-v5.json') --fixtures $fixtures --native $results --inputs $inputs --report (Join-Path $root 'local\recon\original-step-qualification.json')
Assert-OriginalExit 'Original main-step provenance/scope audit failed'
