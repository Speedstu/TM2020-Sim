$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Write-Output '=== TRACKMANIA 2020 RE / SDK ==='
Write-Output "Workspace: $root (H:)"
Write-Output 'Game: D:\SteamLibrary\steamapps\common\Trackmania'
$inv=Get-Content (Join-Path $root 'local\game-inventory.json') -Raw|ConvertFrom-Json
Write-Output "Game version $($inv.version); NadeoPak asset containers: $($inv.packsCount)"
$orig=Get-Content (Join-Path $root 'local\dataset-manifest.json') -Raw|ConvertFrom-Json
$extra=Get-Content (Join-Path $root 'local\corpus\manifest.json') -Raw|ConvertFrom-Json
$number=$orig.count+$extra.pairs.Count
$frames=$orig.totalVehicleSamples+($extra.pairs|Measure-Object vehicleSamples -Sum).Sum
Write-Output "Distinct map/replay pairs: $number | vehicle frames: $frames"
$base=Get-Content (Join-Path $root 'local\physics_baseline\validation.json') -Raw|ConvertFrom-Json
Write-Output ("Ridge 50ms: {0} maps, {1} transitions | speed {2:N3} vs naive {3:N3} km/h | yaw {4:N3} vs naive {5:N3} deg" -f $base.sourceMaps,$base.sourceTransitions,$base.weightedMeanSpeedMAE,$base.weightedNaiveSpeedMAE,$base.weightedMeanYawMAEDeg,$base.weightedNaiveYawMAEDeg)
$nn=Join-Path $root 'local\surrogate_v1\cross_map_validation.json'
if(Test-Path $nn) {
 $m=Get-Content $nn -Raw|ConvertFrom-Json
 Write-Output ("MLP 50ms: speed {0:N3} vs naive {1:N3}; yaw {2:N3} vs naive {3:N3}; beats both: {4}" -f $m.speedMAE_kmh,$m.speedNaiveMAE_kmh,$m.yawMAE_deg,$m.yawNaiveMAE_deg,$m.beatsNaiveBoth)
}
$input=Join-Path $root 'local\input_calibration.json'
if(Test-Path $input) {
 $m=Get-Content $input -Raw|ConvertFrom-Json
 Write-Output ("Input calibration: {0}ms shift; heldout steering MAE {1:N5}, within 1/255: {2:P2}; gas disagreements {3}; brake disagreements {4}; test frames {5}" -f $m.chosenEventOffsetShiftMs,$m.heldoutFitMetrics.steerMAE,$m.heldoutFitMetrics.steerWithinOne255,$m.heldoutFitMetrics.gasMismatchSamples,$m.heldoutFitMetrics.brakeMismatchSamples,$m.heldoutFitMetrics.count)
}
foreach($id in 365553,364956,361930,2154){
 $f=Join-Path $root "local\collision\$id\coverage.json"
 if(Test-Path $f) {
  $m=Get-Content $f -Raw|ConvertFrom-Json
  Write-Output "TMX ${id}: known partial physical triangles $($m.worldTriangles) | matched items $($m.matchedEmbeddedInstances)/$($m.totalAnchoredObjects)"
 }
}
Write-Output "C++ raycaster: $(Test-Path (Join-Path $root 'bin\trackray.exe'))"
Write-Output "In-process native Python BVH library: $(Test-Path (Join-Path $root 'bin\TrackrayNative.dll'))"
Write-Output "SDK quality report: $(Test-Path (Join-Path $root 'local\sdk_validation.json'))"
$nativeReport=Join-Path $root 'local\native-datasets\native-training-readiness.json'
if(Test-Path $nativeReport){
 $status=Get-Content $nativeReport -Raw|ConvertFrom-Json
 Write-Output "Native C++ SDK: $($status.nativeMapReplayDatasets) maps; offline BC pipeline: $($status.offlineSupervisedTrainingPipelineWorks)"
 Write-Output "Native BC steering error: $($status.metrics.steer_MAE) vs zero-steer baseline: $($status.metrics.zero_steer_MAE)"
}
Write-Output 'Native Stadium colliders: MISSING'
Write-Output 'Verified 100Hz game physics state: MISSING'
Write-Output 'Deterministic 100Hz physics engine with reset/rewind: NOT IMPLEMENTED'
$capFile=Join-Path $root 'local\framework-capabilities.json'
if(Test-Path $capFile){
 $caps=Get-Content $capFile -Raw|ConvertFrom-Json
 Write-Output "CMake consumer test: $($caps.cmakeExternalConsumerVerified) | cached collider rays match OBJ: $($caps.binaryTriangleCacheRayEquivalenceVerified)"
 Write-Output "Native C++ requires Openplanet: $($caps.nativeFrameworkRuntimeRequiresOpenplanet) | in-game telemetry validated: $($caps.openplanetRuntimeTestedInGame)"
 Write-Output "Exact 3D KD-tree route planner: $($caps.nativeRouteKDTreeVerifiedAgainstLinearOracle)"
 Write-Output "Measured 50ms replay system-ID: $($caps.nativeSystemIdentification50msVerified)"
 Write-Output "100Hz flat-plane experimental sandbox deterministic: $($caps.experimentalSandbox100HzDeterministicResetRestore)"
 Write-Output "Sandbox fails real Trackmania replay differential: $($caps.experimentalSandboxDifferentialFailsRealReplay)"
}
Write-Output "Native C ABI bridge DLL available: $(Test-Path (Join-Path $root 'dist\sdk-windows-x64\bin\libtm2020_bridge.dll'))"
Write-Output "Historical policy DLL/entry verified in game: $($caps.nativeDllActuallyInjectedIntoTrackmania)"
Write-Output "Historical finish independently verified: $($caps.gameFinishVerified)"
Write-Output "Explicit injected driving qualified: $($caps.injectedDrivingValidated)"
Write-Output "Real-time PPO adapter implemented: $($caps.realtimeResidualPpoAdapterImplemented) | game training validated: $($caps.nativePpoRealGameTrainingValidated)"
Write-Output "Full PPO training checkpoint validated: $($caps.resumablePpoCheckpointValidated) | audited game transitions: $($caps.realGameAuditedPpoTransitions)"
Write-Output "Deterministic learned evaluation validated: $($caps.deterministicPpoEvaluationValidated) | injected finish: $($caps.injectedFinishVerified)"
Write-Output 'Native bridge runtime requires Openplanet: NO'
Write-Output 'Full-track counterfactual RL training: NOT READY'
