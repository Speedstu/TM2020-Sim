param([switch]$SkipLegacy,[switch]$ReuseQualifiedPhysics)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=Join-Path $root 'cache\temp';$env:TMP=$env:TEMP
$env:CARGO_TARGET_DIR=Join-Path $root 'cache\rust-target'
$build=Join-Path $root 'native\build'
function Assert-Exit([string]$Message){if($LASTEXITCODE -ne 0){throw $Message}}
if(!$SkipLegacy){& (Join-Path $PSScriptRoot 'run-framework-tests.ps1');Assert-Exit 'Legacy framework regression failed'}
& (Join-Path $PSScriptRoot 'install-re-tools.ps1')
Assert-Exit 'Portable reverse tool verification failed'
& cmake -S (Join-Path $root 'native') -B $build -G 'MinGW Makefiles' -DCMAKE_BUILD_TYPE=Release
Assert-Exit 'CMake configure failed'
& cmake --build $build --parallel 6
Assert-Exit 'Native release build failed'
& ctest --test-dir $build --output-on-failure
Assert-Exit 'Native PPO/decoder/DLL/owned-process loader checks failed'
& python (Join-Path $PSScriptRoot 'reverse_reflection.py')
Assert-Exit 'SHA-pinned installed executable reflection extraction failed'
& python (Join-Path $PSScriptRoot 'reverse_member_types.py')
Assert-Exit 'SHA-pinned member type extraction failed'
$memberTypes=Get-Content (Join-Path $root 'local\recon\reflected-member-types.json') -Raw | ConvertFrom-Json
$reflection=Get-Content (Join-Path $root 'local\recon\reflection-current-build.json') -Raw | ConvertFrom-Json
& (Join-Path $PSScriptRoot 'run-physics-research-checks.ps1') -SkipBuild -ReuseQualifiedPhysics:$ReuseQualifiedPhysics
Assert-Exit 'Recovered physics kernel qualification failed'
$vehicle=@($reflection.classes | Where-Object name -eq 'CSceneVehicleVisState')
if($vehicle.Count -ne 1 -or $vehicle[0].registeredSize -ne 0x360){throw 'Reflected visual class extent changed'}
foreach($pair in @(@('Loc.translation',0x50),@('WorldVel',0x5c),@('InputSteer',0x10))){
 $field=@($vehicle[0].properties | Where-Object name -eq $pair[0])
 if($field.Count -ne 1 -or $field[0].offset -ne $pair[1]){throw "Reflected field changed: $($pair[0])"}
}
$replays=Join-Path $root 'local\campaign-2026-autumn\native-replays'
$model=Join-Path $root 'local\native-datasets\campaign-neural-v1.tmppo'
$metrics=Join-Path $root 'local\native-datasets\campaign-neural-v1.csv'
& (Join-Path $build 'tm2020_ppo_warmstart.exe') (Join-Path $replays '4634.tmreplay') (Join-Path $replays '4902.tmreplay') (Join-Path $replays '4754.tmreplay') $model $metrics
Assert-Exit 'Native neural BC -> PPO warmstart failed'
$crate=Join-Path $root 'rust\tm2020-sdk\Cargo.toml'
& cargo fmt --manifest-path $crate --check
Assert-Exit 'Rust formatting failed'
& cargo clippy --offline --manifest-path $crate --all-targets -- -D warnings
Assert-Exit 'Rust binding lint failed'
& cargo run --release --offline --manifest-path $crate --example policy -- (Join-Path $build 'libtm2020_policy.dll') (Join-Path $build 'test-policy.tmppo') '0.45'
Assert-Exit 'Rust -> native DLL inference failed'
$prefix=Join-Path $root 'dist\sdk-windows-x64'
& cmake --install $build --prefix $prefix
Assert-Exit 'SDK installation failed'
$rustDestination=Join-Path $prefix 'rust\tm2020-sdk'
New-Item -ItemType Directory -Force $rustDestination | Out-Null
foreach($name in @('Cargo.toml','Cargo.lock','src','examples')){
 Copy-Item -LiteralPath (Join-Path (Split-Path -Parent $crate) $name) -Destination $rustDestination -Recurse -Force
}
$report=[ordered]@{
 schema='tm2020_native_release_0_26_0';nativePpoTrainerCAbiVersion=1;qualifiedArithmeticEvidenceReused=[bool]$ReuseQualifiedPhysics;completeOriginalMainStepReferenceQualified=$true;originalMainStepActiveReferenceFrames=100;originalMainStepInactiveReferenceFrames=100;updatedUtc=[DateTime]::UtcNow.ToString('o')
 nativePpoEngineValidated=$true;nativePpoRealGameTrainingValidated=$false
 neuralWarmstartValidated=$true;neuralWarmstartHeldoutMetrics=(Import-Csv $metrics | Select-Object -First 1)
 nativePolicyDllAbiVersion=1;nativeGameBridgeAbiVersion=3;rustToNativeInferenceValidated=$true
 reflectedClassCount=$reflection.classCount;reflectedPropertyCount=$reflection.propertyCount
 reflectedVisualStateBytes=0x360;reflectedOffsetsPinnedToExeSha256=$reflection.exeSha256
 portableRadare2Version='6.2.4';loaderOwnedFixtureValidated=$true
 authoritativePhysicsOwnerVerified=$false;fullHeadlessTrackmaniaPhysicsReady=$false
 completeOriginalForceWorkerQualifiedForEightFrozenInputs=$true;originalForceWorkerRuntimeGameRequired=$false;originalForceWorkerRequiresPinnedExe=$true;recoveredArithmeticPhysicsOperations=72;newStepParameterPublicOperations=2;newBodyActivationPublicOperations=2;newSteeringSurfacePublicOperations=4;exactConstructedVehicleIntervalQualified=$true;forceCallbackContextBindingQualified=$true;newGeometryPublicOperations=18;newVehicleAndMaterialPublicOperations=15;newContactSchedulerPublicOperations=2;newJointVelocityPublicOperations=3;newJointPositionPublicOperations=4;newRigidFramePublicOperations=1;newPositionSchedulerPublicOperations=1;boundedInstructionSliceOperations=4
 convexManifoldsQualifiedWithinDefinedDomain=$true;contactIslandSchedulerQualifiedWithJointSpansEmpty=$true
 jointVelocityIslandScheduleQualifiedWithExternalCallbacksEmpty=$true;contactPatchGroupingQualified=$true
 autonomousRigidMeshCompositionValidated=$true;completeAuxiliaryVehicleForce84da80QualifiedWithWakeQueueDisabled=$true
 completeWheelKinematicUpdateQualified=$true;completeWheelSpinUpdateQualified=$true
 completeVehicleResistance846010QualifiedWithWakeQueueDisabled=$true;completeLocalTorqueApplicationQualified=$true
 boundedAvxFmaPositionSweepsQualified=$true;capturedMeshPrototypes=351;capturedRayCacheTriangles=795089;completeMapCollisionVerified=$false;physicalSurfaceNamesRecovered=80;effectiveMaterialRecordsCaptured=80;effectiveCurvesCaptured=412;wholeOriginalFmaPositionIslandLoopQualified=$false
 completeWheelMaterialAggregationQualified=$true;fastVehicleSinCosQualifiedWithinArgumentDomain=$true
 positionIslandOrderQualifiedWithinScalarTrigDomain=$true;modelCenterFrameShiftQualified=$true;preparedGeneralJointPositionPassesQualified=$true;generalJointPreparationQualified=$false
 contactPreparationArithmeticProcedures=2;boundedPositionRotationProcedures=4
 recoveredKernelCasesEach=20000;recoveredKernelDifferentialsBitExact=$true
 standaloneRecoveredKernelRunner=$true;completeVehicleForceModelRecovered=$false
 debuggerOwnedFixtureValidated=$true;debuggerOwnedAbortCleanupValidated=$true
 actualGamePhaseCaptureValidated=$false;liveDebuggerCaptureEnabledByDefault=$false
 actualFinishVerified=$false
 realtimeResidualPpoAdapterImplemented=$true;variableDurationGaeValidated=$true
 calibratedActuatorAndVisualFreshnessValidated=$true;runtimeSmallStackHashValidated=$true
 injectedRuntimeWorkerImplemented=$true;injectedDrivingValidated=$false
 resumablePpoCheckpointValidated=$true;deterministicPpoEvaluationImplemented=$true
 reflectedMemberTypeEdges=$memberTypes.edgeCount
}
& python (Join-Path $PSScriptRoot 'summarize_live_qualification.py')
Assert-Exit 'Live-trial evidence summary failed'
& python (Join-Path $PSScriptRoot 'summarize_injected_learning.py')
Assert-Exit 'Retained native learning audit failed'
$learning=Get-Content (Join-Path $root 'local\recon\injected-learning-qualification.json') -Raw | ConvertFrom-Json
$report.injectedDrivingValidated=[bool]$learning.injected_driving_verified
$report.nativePpoRealGameTrainingValidated=$learning.real_game_ppo_updates -gt 0
$report.realGameAuditedPpoTransitions=$learning.audited_real_game_transitions
$report.realGameAdamResumeVerified=[bool]$learning.real_game_adam_resume_verified
$report.deterministicPpoEvaluationValidated=[bool]$learning.deterministic_evaluation_verified
$driving=Get-Content (Join-Path $root 'local\recon\live-driving-qualification.json') -Raw | ConvertFrom-Json
$report.actualFinishVerified=[bool]$driving.game_finish_verified
$report.historicalFinishEvidence=$driving.independent_finish_evidence
$injectedTraces=@($learning.all_retained_trials | Where-Object injected_driving_verified | Select-Object -ExpandProperty trace)
$report.injectedFinishVerified=@($driving.independent_finish_evidence | Where-Object {$_.trial -in $injectedTraces}).Count -gt 0
$report | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $root 'local\release-0.26.0.json') -Encoding UTF8
$capPath=Join-Path $root 'local\framework-capabilities.json'
if(Test-Path -LiteralPath $capPath){
 $caps=Get-Content -LiteralPath $capPath -Raw | ConvertFrom-Json
 $caps.schema='tm2020_framework_capabilities_v25';$caps.updatedUtc=[DateTime]::UtcNow.ToString('o')
 $caps.sdkNativeReleaseVersion='0.26.0'
 $caps.PSObject.Properties.Remove('recoveredArithmeticPhysicsKernels')
 $caps | Add-Member -Force -NotePropertyName recoveredBoundedSliceOperations -NotePropertyValue 3
 $caps | Add-Member -Force -NotePropertyName recoveredPublicArithmeticOperations -NotePropertyValue 72
 $caps | Add-Member -Force -NotePropertyName contactPreparationArithmeticProcedures -NotePropertyValue 2
 $caps | Add-Member -Force -NotePropertyName boundedPositionRotationProcedures -NotePropertyValue 4
 $caps | Add-Member -Force -NotePropertyName collisionDispatchRegisteredOrderedPairs -NotePropertyValue 68
 $caps | Add-Member -Force -NotePropertyName sphereSphereGeometryQualified -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName recoveredKernelDifferentialsBitExact -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName standaloneRecoveredKernelRunner -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName autonomousRigidMeshCompositionValidated -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName contactPatchGroupingQualified -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName nativePpoEngineValidated -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName nativePpoRealGameTrainingValidated -NotePropertyValue ($learning.real_game_ppo_updates -gt 0)
 $caps | Add-Member -Force -NotePropertyName rustPolicyInferenceValidated -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName nativePolicyCAbiVersion -NotePropertyValue 1
 $caps | Add-Member -Force -NotePropertyName reflectedVisualClassCount -NotePropertyValue $reflection.classCount
 $caps | Add-Member -Force -NotePropertyName reflectedPropertyCount -NotePropertyValue $reflection.propertyCount
 $caps | Add-Member -Force -NotePropertyName gameFinishVerified -NotePropertyValue ([bool]$driving.game_finish_verified)
 $caps | Add-Member -Force -NotePropertyName realtimeResidualPpoAdapterImplemented -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName variableDurationGaeValidated -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName runtimeSmallStackHashValidated -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName calibratedActuatorValidated -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName injectedDrivingValidated -NotePropertyValue ([bool]$learning.injected_driving_verified)
 $caps | Add-Member -Force -NotePropertyName injectedFinishVerified -NotePropertyValue $report.injectedFinishVerified
 $caps | Add-Member -Force -NotePropertyName resumablePpoCheckpointValidated -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName deterministicPpoEvaluationValidated -NotePropertyValue ([bool]$learning.deterministic_evaluation_verified)
 $caps | Add-Member -Force -NotePropertyName realGameAuditedPpoTransitions -NotePropertyValue $learning.audited_real_game_transitions
 $caps | Add-Member -Force -NotePropertyName reflectedMemberTypeEdges -NotePropertyValue $memberTypes.edgeCount
 $evidence=Join-Path $root 'local\recon\injected-policy-module.json'
 if(Test-Path -LiteralPath $evidence){
  $live=Get-Content -LiteralPath $evidence -Raw | ConvertFrom-Json
  if($live.gameExeSha256 -eq $reflection.exeSha256 -and $live.modulePathVerified -and $live.sdkEntryExecutedInGameProcess){
   $caps.nativeDllActuallyInjectedIntoTrackmania=$true
   $caps | Add-Member -Force -NotePropertyName injectedSdkEntryReturnedPolicyAbi1 -NotePropertyValue $true
   $caps | Add-Member -Force -NotePropertyName inGamePhysicsHooksInstalled -NotePropertyValue $false
   $caps | Add-Member -Force -NotePropertyName botExecutionInsideGameValidated -NotePropertyValue ([bool]$learning.injected_driving_verified)
  }
 }
 $drivingEvidence=Join-Path $root 'local\recon\live-driving-qualification.json'
 if(Test-Path -LiteralPath $drivingEvidence){
  $driving=Get-Content -LiteralPath $drivingEvidence -Raw | ConvertFrom-Json
  $caps.fall2026ControllerClosedLoopInGameVerified=[bool]$driving.partial_closed_loop_observed
  $caps | Add-Member -Force -NotePropertyName historicalBestReferenceProgress -NotePropertyValue $driving.best_reference_progress
 }
 $caps | Add-Member -Force -NotePropertyName completeOriginalForceWorkerQualifiedForEightFrozenInputs -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName originalForceWorkerRuntimeGameRequired -NotePropertyValue $false
 $caps | Add-Member -Force -NotePropertyName originalForceWorkerRequiresPinnedExe -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName completeOriginalMainStepReferenceQualified -NotePropertyValue $true
 $caps | Add-Member -Force -NotePropertyName originalMainStepActiveReferenceFrames -NotePropertyValue 100
 $caps | Add-Member -Force -NotePropertyName arbitraryActionSimulatorQualified -NotePropertyValue $false
 $caps.note='SDK 0.25.0: Complete original 0x7bd0e0 main steps reproduce every observed physical byte on 100 active plus 100 inactive reference frames, in emulated and native owned processes with explicit platform adapters; arbitrary actions and complete world coverage remain unqualified.  72 public arithmetic operations pass 20,000 original-instruction cases each within documented domains. New ports cover mesh cooking, native AABB construction/traversal, sphere/mesh, convex SAT, polygon/face clipping, engine curve interpolation and mode-2 spring force/torque with wake queue disabled. Convex manifolds and contact island scheduling are qualified within documented domains. General point/angular velocity sweeps and the complete island iteration order with external callbacks empty are qualified. Effective Solo material records and bounded AVX/FMA position sweeps are now qualified. Complete placement/shape coverage, complete tire/slip forces, joint construction and contact-interleaved adaptive scheduling remain incomplete.'
 $caps | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $capPath -Encoding UTF8
}
$consumerBuild=Join-Path $root 'cache\consumer-0.26'
$consumerLog=Join-Path $root 'local\physics-installed-consumer-0.26.0.log'
& cmake -S (Join-Path $root 'native\tests\consumer') -B $consumerBuild -G 'MinGW Makefiles' -DCMAKE_BUILD_TYPE=Release ("-Dtm2020_DIR="+(Join-Path $prefix 'lib\cmake\tm2020')) *> $consumerLog
Assert-Exit 'Installed consumer configuration failed'
& cmake --build $consumerBuild --parallel 4 *>> $consumerLog
Assert-Exit 'Installed consumer build failed'
$consumerSearchPath=$env:PATH
try{
 $env:PATH=(Join-Path $prefix 'bin')+';'+$env:PATH
 & (Join-Path $consumerBuild 'tm2020_consumer.exe') *>> $consumerLog
 Assert-Exit 'Installed consumer execution failed'
}finally{$env:PATH=$consumerSearchPath}
$report.installedCppConsumerValidated=$true
$report | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $root 'local\release-0.26.0.json') -Encoding UTF8
if(Test-Path (Join-Path $root 'local\recon\owned-training-milestone-audit.json')){
 & python (Join-Path $PSScriptRoot 'update_owned_training_capabilities.py')
 Assert-Exit 'Bounded training capability evidence failed'
}
& python (Join-Path $PSScriptRoot 'snapshot_source.py')
Assert-Exit 'Versioned source snapshot failed'
Write-Output 'PASS RELEASE CHECKS: native PPO + neural BC + C/Rust ABI + reflection; real-game qualification is documented separately.'
