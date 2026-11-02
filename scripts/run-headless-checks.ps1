param(
 [string]$Packs='D:/SteamLibrary/steamapps/common/Trackmania/Packs',
 [Parameter(Mandatory=$true)][string]$Output,
 [string[]]$Maps,
 [switch]$Train
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
function Assert-HeadlessExit([string]$message){if($LASTEXITCODE -ne 0){throw $message}}
$destination=[IO.Path]::GetFullPath($Output)
if(Test-Path -LiteralPath $destination){throw 'Choose a new output directory; retained evidence is never overwritten'}
New-Item -ItemType Directory -Path $destination | Out-Null
$hostBinary=Join-Path $root 'cache/gearbox-host-target/release/tm2020-gearbox-host.exe'
$policy=Join-Path $root 'native/build/libtm2020_policy.dll'
if(!$Maps){$Maps=@((Join-Path $root 'cache/gearbox-upstream-e0583ee/tests/golden/maps/pf-364816.Map.Gbx'),(Join-Path $root 'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx'))}
ctest --test-dir (Join-Path $root 'native/build') --output-on-failure --output-junit (Join-Path $destination 'ctest.xml')
Assert-HeadlessExit 'Native tests failed'
python (Join-Path $PSScriptRoot 'test_headless_engine.py') --host $hostBinary --packs $Packs --maps @Maps --output (Join-Path $destination 'cold')
Assert-HeadlessExit 'Cold engine validation failed'
if($Train){
 $run=Join-Path $destination 'ppo'
 python (Join-Path $PSScriptRoot 'train_headless_ppo.py') --host $hostBinary --packs $Packs --policy-dll $policy --auditor (Join-Path $root 'native/build/tm2020_rollout_audit.exe') --initializer (Join-Path $root 'native/build/tm2020_init_headless_policy.exe') --maps @Maps --output $run
 Assert-HeadlessExit 'Native PPO training failed'
 python (Join-Path $PSScriptRoot 'audit_headless_ppo.py') --run $run --host $hostBinary --packs $Packs --policy-dll $policy --output (Join-Path $run 'physics-audit')
 Assert-HeadlessExit 'Accepted PPO trajectories failed independent replay'
 python (Join-Path $PSScriptRoot 'evaluate_headless_ppo.py') --run $run --host $hostBinary --packs $Packs --policy-dll $policy --maps @Maps --output (Join-Path $run 'evaluation')
 Assert-HeadlessExit 'Deterministic policy evaluation failed'
}
