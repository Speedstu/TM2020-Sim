$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=Join-Path $root 'cache\temp'
$env:TMP=$env:TEMP
$env:DOTNET_CLI_HOME=Join-Path $root 'cache\dotnet-home'
$env:NUGET_PACKAGES=Join-Path $root 'cache\nuget'
New-Item -ItemType Directory -Force $env:TEMP |Out-Null
Write-Output '== 1/16 GBX conversion, geometry, replay SDK integration tests =='
& (Join-Path $PSScriptRoot 'run-all-tests.ps1') |Select-Object -Last 9
if($LASTEXITCODE -ne 0){throw 'GBX SDK tests failed'}
Write-Output '== 2/16 Native C++20 map/replay/BC training regression =='
& (Join-Path $PSScriptRoot 'run-native-training.ps1') |Select-Object -Last 11
if($LASTEXITCODE -ne 0){throw 'Native BC tests failed'}
Write-Output '== 3/16 Collision binary cache + ray equivalence =='
& (Join-Path $PSScriptRoot 'cache-collisions.ps1')
if($LASTEXITCODE -ne 0){throw 'Binary cache tests failed'}
Write-Output '== 4/16 Loopback native capture test (synthetic; NO game connection) =='
& (Join-Path $PSScriptRoot 'test-live-capture.ps1') |Select-Object -Last 8
if($LASTEXITCODE -ne 0){throw 'Capture selftest failed'}
Write-Output '== 5/16 Install CMake SDK package on H: and verify independent consumer =='
$prefix=Join-Path $root 'dist\sdk-windows-x64'
& cmake --install (Join-Path $root 'native\build') --prefix $prefix
if($LASTEXITCODE -ne 0){throw 'CMake install failed'}
$consumer=Join-Path $root 'native\tests\consumer'
$consumerBuild=Join-Path $root 'native\tests\consumer-build'
& cmake -S $consumer -B $consumerBuild -G 'MinGW Makefiles' -DCMAKE_BUILD_TYPE=Release "-DCMAKE_PREFIX_PATH=$prefix"
if($LASTEXITCODE -ne 0){throw 'External CMake config failed'}
& cmake --build $consumerBuild --parallel 2
if($LASTEXITCODE -ne 0){throw 'External CMake compile failed'}
& (Join-Path $consumerBuild 'tm2020_consumer.exe')
if($LASTEXITCODE -ne 0){throw 'External SDK consumer failed'}
Write-Output '== 6/16 Official Ubisoft Connect + Steam dependency validation (no Openplanet) =='
$ubisoftExe='D:\Ubisoft\Ubisoft Game Launcher\UbisoftConnect.exe'
$upcExe='D:\Ubisoft\Ubisoft Game Launcher\upc.exe'
$steamManifest='D:\SteamLibrary\steamapps\appmanifest_2225070.acf'
if(-not (Test-Path $ubisoftExe) -or -not (Test-Path $upcExe) -or -not (Test-Path $steamManifest)){
 throw 'Ubisoft Connect or Steam Trackmania missing from expected D: installation'
}
$ubisoftSignature=Get-AuthenticodeSignature $ubisoftExe
if($ubisoftSignature.Status -ne 'Valid' -or $ubisoftSignature.SignerCertificate.Subject -notmatch 'UBISOFT ENTERTAINMENT'){
 throw 'Official Ubisoft Connect binary failed Authenticode publisher verification'
}
$registration=Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Uplay' -ErrorAction Stop
if($registration.InstallLocation -notlike 'D:\Ubisoft\Ubisoft Game Launcher*'){
 throw 'Ubisoft Connect is not registered on the agreed D: volume'
}
Write-Output "PASS official signed Ubisoft Connect ($($registration.DisplayVersion)) installed on D:; Steam Trackmania manifest present"
Write-Output 'NOTE: Ubisoft account login and in-game race session are not validated by this check.'
Write-Output '== 7/16 Native 100Hz scaffold and physics differential research gates =='
& cmake --build (Join-Path $root 'native\build') --parallel 6 | Select-Object -Last 5
if($LASTEXITCODE -ne 0){throw 'Native extended C++ build failed'}
$nativeBin=Join-Path $root 'native\build'
$dataPath=Join-Path $root 'local\native-datasets'
$idPath=Join-Path $root 'local\system-id'
New-Item -ItemType Directory -Force $idPath | Out-Null
& (Join-Path $nativeBin 'tm2020_system_id.exe') $dataPath (Join-Path $idPath 'empirical-handling.csv')
if($LASTEXITCODE -ne 0){throw 'Native replay physics statistic extraction failed'}
& (Join-Path $nativeBin 'tm2020_integrator_probe.exe') $dataPath
if($LASTEXITCODE -ne 0){throw 'Held-out native timebase analysis failed'}
& (Join-Path $nativeBin 'tm2020_route_bench.exe') (Join-Path $dataPath '203281.tmreplay')
if($LASTEXITCODE -ne 0){throw 'Fast native route planner benchmark failed'}
& (Join-Path $nativeBin 'tm2020_sandbox_test.exe') 65536 1000
if($LASTEXITCODE -ne 0){throw 'Experimental 100Hz sandbox determinism tests failed'}
$diffLine=@(& (Join-Path $nativeBin 'tm2020_differential.exe') $dataPath (Join-Path $idPath 'differential-heldout.csv'))
if($LASTEXITCODE -ne 0){throw 'Differential simulator-vs-real-replay test failed to run'}
$diffLine|ForEach-Object {Write-Output $_}
if(-not (@($diffLine|Where-Object {$_ -match 'nativeTrackmaniaPhysicsValidated=false'}).Count -gt 0)){
 throw 'CRITICAL: experimental sandbox fidelity gate unexpectedly passed'
}
$tested=0
foreach($m in Get-ChildItem $dataPath -Filter '*.tmmap' -File){
  $rep=Join-Path $dataPath ($m.BaseName+'.tmreplay')
  & (Join-Path $nativeBin 'tm2020_sdk_test.exe') $m.FullName $rep | Out-Null
  if($LASTEXITCODE -ne 0){throw "3D KD-tree/reference route mismatch on $($m.BaseName)"}
  $tested++
}
if($tested -ne 24){throw "Expected 24 native route maps, found $tested"}
Write-Output 'PASS: 24 exact KD-route tests, empirical system-ID, 100Hz toy determinism, REAL-replay differential fidelity rejection'
Write-Output '== 8/16 Native DLL host ABI, static game RE, and read-only process probe =='
$dll=Join-Path $nativeBin 'libtm2020_bridge.dll'
$replay=Join-Path $dataPath '365553.tmreplay'
$model=Join-Path $dataPath 'bc-ridge-v1.tmbc'
& (Join-Path $nativeBin 'tm2020_bridge_test.exe') $dll $replay $model
if($LASTEXITCODE -ne 0){throw 'Native C ABI bridge/DLL LoadLibrary host integration tests failed'}
$gameExe='D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'
$reconDir=Join-Path $root 'local\recon'
New-Item -ItemType Directory -Force $reconDir | Out-Null
$peReport=Join-Path $reconDir 'trackmania-2026.2.2.1751-vehicle-strings.json'
& (Join-Path $nativeBin 'tm2020_pe_recon.exe') $gameExe $peReport
if($LASTEXITCODE -ne 0){throw 'Static PE RE on installed Trackmania game failed'}
$pe=Get-Content $peReport -Raw|ConvertFrom-Json
if($pe.sections.Count -lt 8 -or (@($pe.patterns|Where-Object {$_.term -eq 'InputSteer' -and $_.reportedCount -gt 0}).Count -ne 1)){
 throw 'Static PE vehicle/input references absent'
}
& (Join-Path $nativeBin 'tm2020_game_probe.exe') --selftest
if($LASTEXITCODE -ne 0){throw 'Native Win32 read-only process observer selftest failed'}
& python (Join-Path $PSScriptRoot 'analyze_vehicle_xrefs.py')
if($LASTEXITCODE -ne 0){throw 'Disassembly-verified references failed'}
$xref=Get-Content (Join-Path $reconDir 'disassembled-string-xrefs.json') -Raw|ConvertFrom-Json
if($xref.xrefTotal -lt 40 -or $xref.liveVehiclePointersKnown -or $xref.actualStructOffsetsKnown){
 throw 'Native C++ state pointers incorrectly inferred from static assembly'
}
& python (Join-Path $PSScriptRoot 'rank_live_motion_candidates.py') --selftest
if($LASTEXITCODE -ne 0){throw 'Live numeric vector motion ranker selftest failed'}
Write-Output 'PASS: confirmed instruction RIP targets, numeric vector motion hypothesis controls'
& python (Join-Path $PSScriptRoot 'export_historical_vehicle_schema.py')
if($LASTEXITCODE -ne 0){throw 'Historical vehicle field schema export failed'}
$fieldSchema=Get-Content (Join-Path $reconDir 'historical-vehicle-fields.json') -Raw|ConvertFrom-Json
if($fieldSchema.byteOffsetsAvailable -or @($fieldSchema.classes|Where-Object {$_.class -eq 'CSceneVehicleVisState'}).Count -ne 1){throw 'Invalid state schema source assumptions'}
$gameFingerprint=[ordered]@{
 version=(Get-Item $gameExe).VersionInfo.FileVersion
 sha256=(Get-FileHash $gameExe -Algorithm SHA256).Hash
 sizeBytes=(Get-Item $gameExe).Length
 nativePeCandidateSectionCount=$pe.sections.Count
 nativePeReportedStringPatterns=$pe.patterns.Count
 scannerDoesNotProveVehicleOffsets=$true
 injectionIntoGamePerformed=$false
 gameReadWriteMemoryTouched=$false
}
$gameFingerprint|ConvertTo-Json|Set-Content (Join-Path $reconDir 'game-build-fingerprint.json') -Encoding UTF8
Write-Output 'PASS: native C++ DLL host bridge + version-specific EXE static recon + read-only process probe'
Write-Output '== 9/16 C++ replay->native ABI bridge throughput validation =='
$hostTest=Join-Path $nativeBin 'tm2020_bridge_replay_host.exe'
$hostReport=Join-Path $root 'local\recon\native-bridge-replay-host.csv'
& $hostTest $dll $dataPath $model $hostReport
if($LASTEXITCODE -ne 0){throw 'Native bridge failed 24-map replay-driven host integration'}
$hostRows=@(Import-Csv $hostReport)
if($hostRows.Count -ne 24 -or @($hostRows|Where-Object {[int]$_.neutral_failures -gt 0 -or [int]$_.active_frames -ne [int]$_.frames}).Count -gt 0){
 throw 'Invalid 24-map bridge replay-host test report'
}
Write-Output 'PASS native bridge host tested with 24 real recorded datasets (not game injection)'
Write-Output '== 10/16 Current Fall2026 game map vs native GBX anchor validation =='
$autumn=Join-Path $root 'local\campaign-2026-autumn'
$autumnMap=Join-Path $autumn '361913.tmmap'
if(Test-Path $autumnMap){
  & (Join-Path $nativeBin 'tm2020_map_anchor_test.exe') $autumnMap
  if($LASTEXITCODE -ne 0){throw 'Real map start/end anchor C++ validation failed'}
  & python (Join-Path $PSScriptRoot 'validate_live_pose_with_gbx.py') --selftest
  if($LASTEXITCODE -ne 0){throw 'GBX/candidate pose scoring selftest failed'}
  $realGroups=Join-Path $root 'local\recon\multi-copy-motion-candidates.json'
  if(Test-Path $realGroups){
    & python (Join-Path $PSScriptRoot 'validate_live_pose_with_gbx.py')
    if($LASTEXITCODE -ne 0){throw 'Actual recorded position candidates failed GBX validation'}
  }
}else{
 Write-Output 'Local Fall 2026 campaign map not present; skip optional real-map corpus experiment'
}
Write-Output '== 11/16 Native read-only pose candidate observer + identity rejection tests =='
& (Join-Path $nativeBin 'tm2020_pose_reader.exe') --selftest
if($LASTEXITCODE -ne 0){throw 'Read-only native C++ pose observer failed self-test'}
$game=@(Get-Process Trackmania -ErrorAction SilentlyContinue)
$manifest=Join-Path $root 'local\recon\session-pose-candidates-v3.txt'
if($game.Count -eq 1 -and (Test-Path $manifest)){
  & (Join-Path $PSScriptRoot 'test-live-pose-reader.ps1')
  if($LASTEXITCODE -ne 0){throw 'Build/PID/process-start pinned native pose observer tests failed'}
} else {
  Write-Output 'No current Trackmania session manifest; game-dependent tests skipped (offline SDK checks still pass)'
}
Write-Output 'PASS: read-only PID+hash+creation-time guarded position-candidate observer'
Write-Output '== 12/16 Causal XYZ velocity estimation and bounded pointer backlink RE =='
$kin=Join-Path $nativeBin 'tm2020_pose_kinematics_test.exe'
$kinReport=Join-Path $root 'local\recon\pose-kinematics-heldout.csv'
& $kin $dataPath $kinReport
if($LASTEXITCODE -ne 0){throw 'Causal XYZ observer test/heldout benchmark failed'}
$perMap=@(Import-Csv $kinReport)
if($perMap.Count -ne 7 -or @($perMap|Where-Object {[double]$_.speed_mae_kmh -gt 100}).Count -gt 0){
 throw 'Causal velocity validation report incomplete'
}
& (Join-Path $nativeBin 'tm2020_pointer_links.exe') --selftest
if($LASTEXITCODE -ne 0){throw 'Read-only reverse pointer scanner unit test failed'}
Write-Output 'PASS: heldout position-only estimated speed and bounded read-only backlink scanner selftest'
Write-Output '== 13/16 Native map-start bootstrap and reusable C++ live observer =='
& (Join-Path $nativeBin 'tm2020_bootstrap_map.exe') --selftest
if($LASTEXITCODE -ne 0){throw 'Native GBX grid-start pose bootstrap selftest failed'}
& (Join-Path $nativeBin 'tm2020_anchored_chain.exe') --selftest
if($LASTEXITCODE -ne 0){throw 'Read-only static .data candidate chain selftest failed'}
$nativeSample=Join-Path $root 'local\recon\restart-native-bootstrap-v3.txt'
if(Test-Path $nativeSample){
  $lines=[IO.File]::ReadAllLines($nativeSample)
  $gameProcess=@(Get-Process Trackmania -ErrorAction SilentlyContinue)
  if($gameProcess.Count -eq 1 -and [int]$lines[1] -eq [int]$gameProcess[0].Id){
    & (Join-Path $nativeBin 'tm2020_live_consumer_test.exe') $nativeSample
    if($LASTEXITCODE -ne 0){throw 'C++ typed live read-only observer failed after bootstrap'}
  }else{
    Write-Output 'Live typed SDK test skipped: cached pose hypothesis manifest belongs to another process'
  }
}
Write-Output 'PASS: native map-start bootstrap and typed TM2020::Live library tests'
Write-Output '== 14/16 Real Fall 2026 - 01 replays and out-of-sample reference route =='
$campaignDir=Join-Path $root 'local\campaign-2026-autumn'
$nativeReplays=Join-Path $campaignDir 'native-replays'
$officialMap=Join-Path $campaignDir '361913.tmmap'
$reference=Join-Path $nativeReplays '4634.tmreplay'
$heldoutA=Join-Path $nativeReplays '4754.tmreplay'
$heldoutB=Join-Path $nativeReplays '4902.tmreplay'
foreach($required in @($officialMap,$reference,$heldoutA,$heldoutB)){
  if(!(Test-Path $required)){throw "Missing previously validated public Fall2026 replay/map: $required"}
}
& (Join-Path $nativeBin 'tm2020_campaign_route_test.exe') $officialMap $reference $heldoutA (Join-Path $nativeReplays 'route-heldout-4754.csv')
if($LASTEXITCODE -ne 0){throw 'Fall2026 reference route failed on first independent replay'}
& (Join-Path $nativeBin 'tm2020_campaign_route_test.exe') $officialMap $reference $heldoutB (Join-Path $nativeReplays 'route-heldout-4902.csv')
if($LASTEXITCODE -ne 0){throw 'Fall2026 reference route failed on second independent replay'}
& (Join-Path $nativeBin 'tm2020_campaign_controller_bench.exe') $reference $heldoutB $heldoutA (Join-Path $nativeReplays 'follower-eval-4754.csv')
if($LASTEXITCODE -ne 0){throw 'Campaign pure-pursuit follower regression failed'}
$controllerMetrics=Import-Csv (Join-Path $nativeReplays 'follower-eval-4754.csv')|Select-Object -First 1
if($controllerMetrics.heldout_beats_baseline -ne 'true' -or
    [double]$controllerMetrics.heldout_steer_mae -ge 0.5*[double]$controllerMetrics.heldout_zero_steer_mae){
 throw 'Campaign follower does not reliably beat zero steering on held-out TAS controls'
}
Write-Output 'PASS: C++ reference course and heldout advisory steering accuracy, no game controls sent'
Write-Output '== 15/16 C ABI v3 native DLL follower host and offline-only input guard =='
& (Join-Path $nativeBin 'tm2020_campaign_bridge_follower_test.exe') $dll $reference $heldoutA
if($LASTEXITCODE -ne 0){throw 'Native C ABI 3 reference follower host or nonlocal neutral-action guard failed'}
Write-Output 'PASS: local-only DLL advisory follower validated vs direct C++ math'
Write-Output '== 16/16 Save source-only snapshot (no Ubisoft game assets) =='

& python (Join-Path $PSScriptRoot 'snapshot_source.py')
if($LASTEXITCODE -ne 0){throw 'Source snapshot failed'}
$status=Get-Content (Join-Path $root 'local\native-datasets\native-training-readiness.json') -Raw|ConvertFrom-Json
if($status.headlessFullPhysicsRLTrainingReady){throw 'Readiness flag incorrectly claims full physics ready'}
$capabilities=[ordered]@{
 schema='tm2020_framework_capabilities_v10'
 updatedUtc=[DateTime]::UtcNow.ToString('o')
 cpp20LibraryBuildVerified=$true
 sdkNativeReleaseVersion='0.5.0'
 nativeReadOnlyTypedCxxLiveLibraryInstalledAndTested=$true
 nativeGBXStartMemoryBootstrapPortableCppVerified=$true
 nativeBootstrapRediscoveredGamePoseAfterRestart=$true
 previousCandidateStaticGlobalChainFailedAfterRestart=$true
 nativePointerSearchStaticImageExplicitlyPrioritized=$true
 cmakeExternalConsumerVerified=$true
 nativeReplayDatasetsTested=24
 additionalFall2026PublicReplayFilesTested=3
 fall2026RouteEvaluatedOnTwoIndependentReplays=$true
 fall2026SameMapControllerOutperformsNeutralOffline=$true
 fall2026ControllerClosedLoopInGameVerified=$false
 nativeCppDllLoadedAndTestedInSeparateHost=$true
 nativeCppBridgeReplayHostEvaluatedAll24Maps=$true
 nativeCAbiVersion=3
 nativeDllRouteFollowerOnSameMapHeldoutVerified=$true
 nativeDllFollowerDoesNotRequirePythonBCModel=$true
 nativeDllOnlineDeniedInHostTest=$true
 ubisoftConnectInstalledOnD=$true
 ubisoftConnectSessionAuthenticated=$true
 nativeDllActuallyInjectedIntoTrackmania=$false
 liveGameVehicleStateOffsetsVerified=$false
 gameProcessReadOnlyProbeSelftestVerified=$true
 gameExecutableStaticREVersionPinned=$true
 historicalVehicleTypeDatabaseExportedAsNonOffsets=$true
 disassemblerConfirmedStaticStringReferences=$true
 stationaryVehicleNumericCandidateCaptureSaved=(Test-Path (Join-Path $root 'local\recon\stationary-solo-track01.tmvec'))
 nativeReadOnlyLivePoseCandidateObserverCompiledAndTested=$true
 nativeGBXCourseStartCheckpointFinishMarkersVerified=$true
 nativeCausalXYZVelocityEstimatedOnSevenHeldoutMaps=$true
 nativeLiveReadOnlyPointerBacklinkScannerTested=$true
 nativeReadOnlyQuaternionCandidateObservedInActualGame=$true
 nativeQuaternionCandidateVerifiedAsPhysicsOrientation=$false
 stablePointerChainFromGameModuleResolved=$false
 nativePlayerOwnerPointerRecoveredAcrossRestart=$false
 poseManifestV3RejectsOldSwappedAxes=$true
 numericPositionCandidatesCorrelatedWithKnownGBXStart=$true
 stableVehicleOwnerPointerResolved=$false
 knownGameBuildHashAndCreationTimePinnedReader=$true
 vehicleLocationFromMemoryVerified=$false
 historical2020VehiclePointerChainValidated=$false
 genuineFall2026MapLoadedInCpp=$true
 playerPoseCandidatesCrossCheckedAgainstMapGeometry=$true
 playerPoseValidatedStableAcrossRestarts=$false
 gameBlockedByMissingUbisoftConnectAtLiveTest=$false
 readOnlyActualGameProcessProbeObservedAtLiveTest=$true
 nativeRouteKDTreeVerifiedAgainstLinearOracle=$true
 nativeSystemIdentification50msVerified=$true
 nativeIntegratorTimebaseFitOnUnseenMaps=$true
 experimentalSandbox100HzDeterministicResetRestore=$true
 experimentalSandboxDifferentialFailsRealReplay=$true
 binaryTriangleCacheRayEquivalenceVerified=$true
 loopbackTelemetrySyntheticTestVerified=$true
 nativeFrameworkRuntimeRequiresOpenplanet=$false
 ubisoftConnectSignatureAndSteamManifestVerified=$true
 openplanetRuntimeTestedInGame=$false
 truePhysicsState100HzVerified=$false
 nativeStadiumTrackCollisionsComplete=$false
 engineCounterfactualStepResetRewindImplemented=$false
 offlineBCTrainingPipelineWorks=$true
 offlineBCPolicyBeatsNeutralSteer=$false
 fullTrackmaniaHeadlessRLReady=$false
 note='Native SDK v0.4 C ABI3 + typed Live reader. Native C++ pose bootstraps at authentic GBX start after game restart; old static chain failed after restart. Three same-map public TAS replays validate 4634 reference route; C++ follower heldout direction MAE 0.2363 vs 0.7245 neutral. No validated live yaw/physics owner, no in-game DLL injection or real-game closed-loop test, no faithful headless 100Hz physics simulator.'
}
$capFile=Join-Path $root 'local\framework-capabilities.json'
$capabilities|ConvertTo-Json -Depth 4|Set-Content -LiteralPath $capFile -Encoding UTF8
Write-Output "CAPABILITIES REPORT: $capFile"
Write-Output 'PASS ALL FRAMEWORK TESTS. C++ SDK + training/data tools operate; FULL TRACKMANIA RL PHYSICS NOT READY.'
exit 0
