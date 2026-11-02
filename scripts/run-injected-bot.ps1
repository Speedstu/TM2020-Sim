param(
 [switch]$ConfirmLocalSolo,
 [string]$Manifest,
 [string]$Reference,
 [double]$Seconds=55,
 [double]$HeadingGain=-3,
 [double]$Deadzone=0.1,
 [string]$PpoModel,
 [switch]$Evaluate,
 [string]$ViGEmClient,
 [string]$OutputName
)
$ErrorActionPreference='Stop'
if(!$ConfirmLocalSolo){throw 'Explicit -ConfirmLocalSolo is required; put the game in a local Solo race first.'}
if($Evaluate -and !$PpoModel){throw '-Evaluate requires -PpoModel'}
$root=Split-Path -Parent $PSScriptRoot
$games=@(Get-Process -Name Trackmania -ErrorAction Stop)
if($games.Count -ne 1){throw 'Expected exactly one Trackmania process'}
$game=$games[0]
$gameExeSha256=(Get-FileHash -LiteralPath $game.Path -Algorithm SHA256).Hash.ToLowerInvariant()
if(!$Manifest){$Manifest=Join-Path $root "local\recon\live-cpp-$($game.Id)-v3.txt"}
if(!$Reference){$Reference=Join-Path $root 'local\campaign-2026-autumn\native-replays\4634.tmreplay'}
$Manifest=(Resolve-Path -LiteralPath $Manifest).Path
$Reference=(Resolve-Path -LiteralPath $Reference).Path
$source=Join-Path $root 'native\build\libtm2020_runtime.dll'
$loader=Join-Path $root 'native\build\tm2020_local_dll_loader.exe'
if(!(Test-Path -LiteralPath $source)){throw 'Build the native tm2020_runtime target first.'}
$dllHash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
$runtimeDir=Join-Path $root 'local\runtime'
New-Item -ItemType Directory -Force $runtimeDir | Out-Null
$dll=Join-Path $runtimeDir "tm2020-runtime-$($dllHash.Substring(0,16)).dll"
if(!(Test-Path -LiteralPath $dll)){Copy-Item -LiteralPath $source -Destination $dll}
if((Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $dllHash){throw 'Runtime copy hash mismatch'}
if(!$OutputName){$OutputName='injected-'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')}
if($OutputName -notmatch '^[a-zA-Z0-9_-]{1,80}$'){throw 'OutputName must be a simple filename stem'}
$trace=Join-Path $root "local\recon\codex-follower-$OutputName.csv"
$config=Join-Path $runtimeDir "$OutputName.args"
if((Test-Path -LiteralPath $trace) -or (Test-Path -LiteralPath $config)){
 throw 'OutputName already has retained evidence; choose a new name to preserve prior trials.'
}
$culture=[Globalization.CultureInfo]::InvariantCulture
$vigem=if($ViGEmClient){[IO.Path]::GetFullPath($ViGEmClient)}else{Join-Path $root 'tools\vigem\ViGEmClient.dll'}
if(!(Test-Path -LiteralPath $vigem)){throw 'Configure the installed ViGEmClient.dll path in this script'}
$arguments=@('TM2020_LOCAL_BOT_ARGUMENTS_V1','--confirm-local-solo',$Manifest,$Reference,$trace,'gamepad',$vigem,
 $Seconds.ToString($culture),'24',$HeadingGain.ToString($culture),'--tracking','--deadzone',$Deadzone.ToString($culture))
if($PpoModel){$arguments+=@($(if($Evaluate){'--ppo-evaluate'}else{'--ppo-update'}),[IO.Path]::GetFullPath($PpoModel))}
$modelBefore=if($PpoModel -and (Test-Path -LiteralPath $PpoModel)){(Get-FileHash -LiteralPath $PpoModel -Algorithm SHA256).Hash.ToLowerInvariant()}else{$null}
[IO.File]::WriteAllLines($config,$arguments,[Text.UTF8Encoding]::new($false))
& $loader --confirm-local-solo $Manifest $dll --run $config
$workerExit=$LASTEXITCODE
$statusPath=$config+'.status'
$status=if(Test-Path -LiteralPath $statusPath){[IO.File]::ReadAllLines($statusPath)}else{@()}
$statusValid=$status.Count -eq 4 -and $status[0] -eq 'TM2020_INJECTED_WORKER_STATUS_V1' -and [int]$status[1] -eq $game.Id
$rows=if(Test-Path -LiteralPath $trace){@(Import-Csv -LiteralPath $trace)}else{@()}
$hosts=@($rows | Select-Object -ExpandProperty host_pid -Unique)
$inside=$rows.Count -ge 100 -and $hosts.Count -eq 1 -and [int]$hosts[0] -eq $game.Id
$motion=0.0
if($rows.Count -gt 0){
 $first=$rows[0]
 foreach($row in $rows){
  $dx=[double]$row.x-[double]$first.x;$dy=[double]$row.y-[double]$first.y;$dz=[double]$row.z-[double]$first.z
  $motion=[math]::Max($motion,[math]::Sqrt($dx*$dx+$dy*$dy+$dz*$dz))
 }
}
$clocks=@($rows | Select-Object -ExpandProperty clock_candidate_ms -Unique)
$response=@($rows | Where-Object {[double]$_.measured_gas -gt 0.5 -and [double]$_.gas -gt 0.5}).Count
$stillRunning=Get-Process -Id $game.Id -ErrorAction SilentlyContinue
$module=if($stillRunning){@($stillRunning.Modules | Where-Object {$_.FileName -eq $dll})}else{@()}
$evidence=[ordered]@{
 schema='tm2020_injected_bot_execution_v1';updatedUtc=[DateTime]::UtcNow.ToString('o')
 processId=$game.Id;modulePath=$dll;moduleSha256=$dllHash;modulePathVerified=$module.Count -eq 1
 loaderExitCode=$workerExit;workerStatusValid=$statusValid;workerStatus=$status
 trace=$trace;traceRows=$rows.Count;traceHostProcessIds=$hosts
 botLoopExecutedInsideGame=$inside;finishedWorkerNormally=$statusValid -and $status[2] -eq 'RETURNED' -and $status[3] -eq '0'
 maxDisplacementMeters=$motion;distinctVisualClocks=$clocks.Count;throttleResponseObservations=$response
 partialInjectedDrivingObserved=$inside -and $motion -gt 10 -and $clocks.Count -ge 10 -and $response -ge 10
 traceSha256=if(Test-Path -LiteralPath $trace){(Get-FileHash -LiteralPath $trace -Algorithm SHA256).Hash.ToLowerInvariant()}else{$null}
 gameExeSha256=$gameExeSha256
 gameFinishVerified=$false;physicsHookInstalled=$false;authoritativePhysicsOwnerVerified=$false
 ppoMetrics=if(Test-Path -LiteralPath ($trace+'.ppo.csv')){Import-Csv -LiteralPath ($trace+'.ppo.csv') | Select-Object -First 1}else{$null}
 deterministicEvaluation=[bool]$Evaluate
 policyModelSha256Before=$modelBefore
 policyModelSha256After=if($PpoModel -and (Test-Path -LiteralPath $PpoModel)){(Get-FileHash -LiteralPath $PpoModel -Algorithm SHA256).Hash.ToLowerInvariant()}else{$null}
 evaluationMetrics=if(Test-Path -LiteralPath ($trace+'.evaluation.csv')){Import-Csv -LiteralPath ($trace+'.evaluation.csv') | Select-Object -First 1}else{$null}
}
$evidence | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $root "local\recon\$OutputName.json") -Encoding utf8
if($workerExit -ne 0 -or !$inside -or !$evidence.finishedWorkerNormally){throw 'Injected runtime qualification incomplete; inspect status and trace.'}
Write-Output "PASS INJECTED BOT: PID $($game.Id), $($rows.Count) actual in-process observations; race finish must be qualified separately."
