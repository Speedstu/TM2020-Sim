param([switch]$SkipBuild,[switch]$ReuseQualifiedPhysics)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=Join-Path $root 'cache\temp';$env:TMP=$env:TEMP
$build=Join-Path $root 'native\build'
function Assert-PhysicsExit([string]$Message){if($LASTEXITCODE -ne 0){throw $Message}}
if(!$SkipBuild){
 & cmake -S (Join-Path $root 'native') -B $build -G 'MinGW Makefiles' -DCMAKE_BUILD_TYPE=Release
 Assert-PhysicsExit 'Physics CMake configure failed'
 & cmake --build $build --parallel 6
 Assert-PhysicsExit 'Physics build failed'
 & ctest --test-dir $build --output-on-failure
 Assert-PhysicsExit 'Native regression failed'
}
$emulator=Join-Path $root 'tools\physics-python'
if(!(Test-Path (Join-Path $emulator 'unicorn'))){
 & python -m pip install --target $emulator --cache-dir (Join-Path $root 'cache\pip') 'unicorn==2.1.4'
 Assert-PhysicsExit 'Isolated development emulator installation failed'
}
if(!$ReuseQualifiedPhysics){
& python (Join-Path $PSScriptRoot 'test_pe_unwind.py')
Assert-PhysicsExit 'Chained unwind tests failed'
& python (Join-Path $PSScriptRoot 'reverse_reflection.py') --selftest
Assert-PhysicsExit 'Reflection extraction selftest failed'
& python (Join-Path $PSScriptRoot 'reverse_physics.py')
Assert-PhysicsExit 'SHA-pinned physics graph/dispatch validation failed'
& python (Join-Path $PSScriptRoot 'check_reverse_atlas.py')
Assert-PhysicsExit 'Whole ordinary-text atlas validation failed'
& python (Join-Path $PSScriptRoot 'reverse_wheel_pipeline.py')
Assert-PhysicsExit 'Wheel/contact/CCD evidence extraction failed'
& python (Join-Path $PSScriptRoot 'reverse_constraint_evidence.py')
Assert-PhysicsExit 'Constraint layouts/constants evidence extraction failed'
& python (Join-Path $PSScriptRoot 'reverse_collision_dispatch.py')
Assert-PhysicsExit 'Original collision dispatch initializer qualification failed'
& (Join-Path $build 'tm2020_recovered_oracle.exe') 'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe' (Join-Path $root 'local\recon\recovered-kernel-oracle.json')
Assert-PhysicsExit 'Original arithmetic differential failed'
& python (Join-Path $PSScriptRoot 'test_recovered_forces.py') --cases 20000
Assert-PhysicsExit 'Unmodified original force emulation differential failed'
& (Join-Path $build 'tm2020_contact_oracle.exe') 'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe' (Join-Path $root 'local\recon\recovered-contact-oracle.json')
Assert-PhysicsExit 'Original native contact solver differential failed'
& (Join-Path $build 'tm2020_jacobian_oracle.exe') 'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe' (Join-Path $root 'local\recon\recovered-jacobian-oracle.json')
Assert-PhysicsExit 'Original Jacobian/friction differential failed'
& (Join-Path $build 'tm2020_contact_build_oracle.exe') 'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe' (Join-Path $root 'local\recon\recovered-contact-build-oracle.json')
Assert-PhysicsExit 'Original contact preparation differential failed'
& (Join-Path $build 'tm2020_rotation_oracle.exe') 'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe' (Join-Path $root 'local\recon\recovered-rotation-oracle.json')
Assert-PhysicsExit 'Original bounded rotation correction differential failed'
& python (Join-Path $PSScriptRoot 'test_recovered_positions.py') --cases 20000
Assert-PhysicsExit 'Original complete position sweep differential failed'
& (Join-Path $build 'tm2020_sphere_oracle.exe') 'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe' (Join-Path $root 'local\recon\recovered-sphere-oracle.json')
Assert-PhysicsExit 'Original sphere contact geometry differential failed'
& python (Join-Path $PSScriptRoot 'test_recovered_selection.py') --cases 20000
Assert-PhysicsExit 'Original substep/suspension instruction differential failed'
& python (Join-Path $PSScriptRoot 'reverse_mesh_evidence.py')
Assert-PhysicsExit 'Mesh/convex/polygon evidence extraction failed'
& python (Join-Path $PSScriptRoot 'reverse_vehicle_evidence.py')
Assert-PhysicsExit 'Vehicle arithmetic evidence extraction failed'
& python (Join-Path $PSScriptRoot 'test_recovered_cooking.py') --cases 20000
Assert-PhysicsExit 'Original complete mesh cooker differential failed'
& python (Join-Path $PSScriptRoot 'test_recovered_bounds.py')
Assert-PhysicsExit 'Original bounded triangle AABB differential failed'
& python (Join-Path $PSScriptRoot 'compile_effective_materials.py')
Assert-PhysicsExit 'Retained effective material fixture validation failed'
foreach($operation in @(@('mesh','recovered-mesh-oracle.json'),@('tree_builder','recovered-tree-builder-oracle.json'),@('convex','recovered-convex-oracle.json'),@('polygon','recovered-polygon-oracle.json'),@('vehicle_kernel','recovered-vehicle-kernel-oracle.json'),@('features','recovered-features-oracle.json'),@('joints','recovered-joints-oracle.json'),@('vehicle_auxiliary','recovered-vehicle-auxiliary-oracle.json'),@('wheel_update','recovered-wheel-update-oracle.json'),@('wheel_spin','recovered-wheel-spin-oracle.json'),@('joint_position','recovered-joint-position-oracle.json'),@('frame','recovered-frame-oracle.json'),@('step','recovered-step-parameter-oracle.json'),@('activation','recovered-activation-oracle.json'),@('steering','recovered-steering-surface-oracle.json'),@('resistance','recovered-resistance-oracle.json'))){
 & (Join-Path $build ('tm2020_'+$operation[0]+'_oracle.exe')) 'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe' (Join-Path $root ('local\recon\'+$operation[1]))
 Assert-PhysicsExit ('Original differential failed: '+$operation[0])
}
& (Join-Path $build 'tm2020_wheel_material_oracle.exe') 'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe' (Join-Path $root 'local\recon\recovered-wheel-material-oracle.json') (Join-Path $root 'local\recon\effective-materials-26616.bin')
Assert-PhysicsExit 'Complete wheel materials with captured race records differential failed'
& (Join-Path $build 'tm2020_position_fma_oracle.exe') 'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe' (Join-Path $root 'local\recon\position-oracle\position-input.bin') (Join-Path $root 'local\recon\recovered-position-fma-oracle.json')
Assert-PhysicsExit 'Complete native AVX/FMA position sweeps differential failed'
& python (Join-Path $PSScriptRoot 'test_recovered_materials.py') --cases 20000
Assert-PhysicsExit 'Original complete material response differential failed'
& python (Join-Path $PSScriptRoot 'test_recovered_convex_collision.py') --cases 20000
Assert-PhysicsExit 'Original complete convex manifold differential failed'
& python (Join-Path $PSScriptRoot 'test_recovered_convex_mesh.py') --cases 20000
Assert-PhysicsExit 'Original complete convex mesh manifold differential failed'
& python (Join-Path $PSScriptRoot 'test_recovered_solver.py') --cases 20000
Assert-PhysicsExit 'Original complete contact island scheduler differential failed'
& python (Join-Path $PSScriptRoot 'test_recovered_solver.py') --joints --cases 20000 --out (Join-Path $root 'local\recon\joint-solver-oracle')
Assert-PhysicsExit 'Original complete contact/joint island scheduler differential failed'
& python (Join-Path $PSScriptRoot 'test_recovered_patches.py') --cases 20000
Assert-PhysicsExit 'Original complete contact patch grouping differential failed'
& python (Join-Path $PSScriptRoot 'test_recovered_position_islands.py') --cases 20000
Assert-PhysicsExit 'Original eight-pass position island loop differential failed'
& (Join-Path $build 'tm2020_rigid_mesh_demo.exe') 10000 (Join-Path $root 'local\recon\rigid-mesh-trace.csv') (Join-Path $root 'local\recon\rigid-mesh-demo.json')
Assert-PhysicsExit 'Autonomous recovered rigid mesh world/snapshot replay failed'
& (Join-Path $build 'tm2020_rigid_mesh_demo.exe') 10000 (Join-Path $root 'local\recon\rigid-mesh-fma-trace.csv') (Join-Path $root 'local\recon\rigid-mesh-fma-demo.json') fma
Assert-PhysicsExit 'Autonomous FMA scene replay failed'
& python (Join-Path $PSScriptRoot 'reverse_force_context.py')
Assert-PhysicsExit 'Force callback context layout qualification failed'
& python (Join-Path $PSScriptRoot 'reverse_steering_surface.py')
Assert-PhysicsExit 'Complete steering/inverse-trig/surface-scalar qualification failed'
& python (Join-Path $PSScriptRoot 'reverse_activation.py')
Assert-PhysicsExit 'Body activation scope/original evidence failed'
& python (Join-Path $PSScriptRoot 'reverse_step_timing.py')
Assert-PhysicsExit 'Exact vehicle interval/time flow evidence failed'
& python (Join-Path $PSScriptRoot 'reverse_world_tick.py')
Assert-PhysicsExit 'Caller-side 10 ms scene tick evidence failed'
& python (Join-Path $PSScriptRoot 'reverse_vehicle_control_fields.py')
Assert-PhysicsExit 'Internal vehicle control scalar evidence failed'
& python (Join-Path $PSScriptRoot 'reverse_step_parameters.py')
Assert-PhysicsExit 'Step parameter bounds/constants qualification failed'
& python (Join-Path $PSScriptRoot 'reverse_surface_names.py')
Assert-PhysicsExit 'Physical surface ID/name table differs from SDK'
& python (Join-Path $PSScriptRoot 'build_live_collision_cache.py')
Assert-PhysicsExit 'Captured mesh ray-cache reconstruction failed'
& (Join-Path $build 'tm2020_collision_replay_audit.exe') (Join-Path $root 'local\collision-maps\ypPmohQofd72MyTsIsijKfrJH98-live-meshes.tmcol') (Join-Path $root 'local\collision-maps\ypPmohQofd72MyTsIsijKfrJH98-live-meshes.surfaces') (Join-Path $root 'local\campaign-2026-autumn\native-replays\4634.tmreplay') (Join-Path $root 'local\recon\captured-collision-replay-26616.json')
Assert-PhysicsExit 'Captured geometry native replay-ray audit failed'
& python (Join-Path $PSScriptRoot 'test_captured_ray_cache.py')
Assert-PhysicsExit 'Native BVH versus independent exhaustive closest-distance differential failed'
& python (Join-Path $PSScriptRoot 'audit_live_geometry.py')
Assert-PhysicsExit 'Captured geometry evidence/hash audit failed'
}else{
 & python (Join-Path $PSScriptRoot 'reuse_qualified_physics.py')
 Assert-PhysicsExit 'Qualified arithmetic source/binary/evidence changed; run full checks'
 & python (Join-Path $PSScriptRoot 'audit_live_geometry.py')
 Assert-PhysicsExit 'Retained captured geometry changed'
}
& (Join-Path $PSScriptRoot 'run-force-worker-checks.ps1') -SkipBuild
Assert-PhysicsExit 'Complete original force worker offline/native qualification failed'
& (Join-Path $PSScriptRoot 'run-original-step-checks.ps1') -SkipBuild
Assert-PhysicsExit 'Complete original main-step every-frame comparison failed'
& python (Join-Path $PSScriptRoot 'audit_recovered_geometry.py')
Assert-PhysicsExit 'Geometry/vehicle evidence audit failed'
& (Join-Path $build 'tm2020_rigid_benchmark.exe') 65536 100 (Join-Path $root 'local\recon\recovered-kernel-benchmark.json')
Assert-PhysicsExit 'Autonomous kernel benchmark/restore failed'
& python (Join-Path $PSScriptRoot 'summarize_physics.py')
Assert-PhysicsExit 'Retained physics evidence audit failed'
& python (Join-Path $PSScriptRoot 'summarize_wheels.py')
Assert-PhysicsExit 'Retained wheel evidence audit failed'
& python (Join-Path $PSScriptRoot 'summarize_debug_capture.py')
Assert-PhysicsExit 'Owned debugger evidence audit failed'
$oracle=Get-Content (Join-Path $root 'local\recon\recovered-kernel-oracle.json') -Raw | ConvertFrom-Json
$forces=Get-Content (Join-Path $root 'local\recon\force-oracle\recovered-force-oracle.json') -Raw | ConvertFrom-Json
$graph=Get-Content (Join-Path $root 'local\recon\physics\physics-procedure-graph.json') -Raw | ConvertFrom-Json
$contacts=Get-Content (Join-Path $root 'local\recon\recovered-contact-oracle.json') -Raw | ConvertFrom-Json
$selection=Get-Content (Join-Path $root 'local\recon\selection-oracle\selection-suspension-oracle.json') -Raw | ConvertFrom-Json
$atlas=Get-Content (Join-Path $root 'local\recon\game-atlas.json') -Raw | ConvertFrom-Json
$jacobian=Get-Content (Join-Path $root 'local\recon\recovered-jacobian-oracle.json') -Raw | ConvertFrom-Json
$builders=Get-Content (Join-Path $root 'local\recon\recovered-contact-build-oracle.json') -Raw | ConvertFrom-Json
$rotation=Get-Content (Join-Path $root 'local\recon\recovered-rotation-oracle.json') -Raw | ConvertFrom-Json
$position=Get-Content (Join-Path $root 'local\recon\position-oracle\recovered-position-oracle.json') -Raw | ConvertFrom-Json
$sphere=Get-Content (Join-Path $root 'local\recon\recovered-sphere-oracle.json') -Raw | ConvertFrom-Json
$dispatch=Get-Content (Join-Path $root 'local\recon\collision-dispatch.json') -Raw | ConvertFrom-Json
if(!$jacobian.bit_exact -or !$builders.bit_exact -or !$rotation.bit_exact -or !$position.bitExact -or !$sphere.bit_exact -or !$dispatch.reconstructedTableMatchesExecutedTable){throw 'New constraint/collision qualification failed'}
if(!$oracle.bit_exact -or !$forces.bitExact -or $forces.originalCodeModified -or $forces.functionsSkipped -or !$contacts.bit_exact -or !$selection.bitExact -or $selection.originalCodeModified){throw 'Physics qualification flags invalid'}
$report=[ordered]@{
 schema='tm2020_physics_research_0_25_0';qualifiedArithmeticEvidenceReused=[bool]$ReuseQualifiedPhysics;completeOriginalMainStepReferenceQualified=$true;originalMainStepActiveReferenceFrames=100;originalMainStepInactiveReferenceFrames=100;updatedUtc=[DateTime]::UtcNow.ToString('o');sha256=$oracle.sha256
 completeOriginalForceWorkerQualifiedForEightFrozenInputs=$true;originalForceWorkerRuntimeGameRequired=$false;originalForceWorkerRequiresPinnedExe=$true;originalForceWorkerIsPortablePort=$false;recoveredArithmeticOperations=72;newStepParameterPublicOperations=2;newBodyActivationPublicOperations=2;newSteeringSurfacePublicOperations=4;completeSteeringAndSurfaceScalarQualified=$true;bodyActivationPreparationQualified=$true;exactConstructedVehicleIntervalQualified=$true;completeStepParameterConstructorQualified=$true;forceCallbackContextBindingQualified=$true;newGeometryPublicOperations=18;newVehicleAndMaterialPublicOperations=15;newContactSchedulerPublicOperations=2;newJointVelocityPublicOperations=3;newJointPositionPublicOperations=4;newRigidFramePublicOperations=1;newPositionSchedulerPublicOperations=1;boundedInstructionSliceOperations=4
 contactPreparationArithmeticProcedures=2;positionRotationProceduresWithBoundedTrigDomain=4
 preparedFrictionSolversQualified=$true;positionSweepsQualifiedWithinAngularDomain=$true
 convexManifoldsQualifiedWithinDefinedDomain=$true;convexMeshCandidateCapQualified=$true
 contactIslandSchedulerQualifiedWithJointSpansEmpty=$true;generalJointVelocityConstraintsQualified=$true
 jointVelocityIslandScheduleQualifiedWithExternalCallbacksEmpty=$true
 contactPatchGroupingQualified=$true;negativeRestitutionContactPreparationQualified=$true
 autonomousRigidMeshCompositionValidated=$true;wholeGameStepInstructionOracleQualified=$false
 completeAuxiliaryVehicleForce84da80QualifiedWithWakeQueueDisabled=$true
 completeWheelKinematicUpdateQualified=$true;completeWheelSpinUpdateQualified=$true
 completeVehicleResistance846010QualifiedWithWakeQueueDisabled=$true;completeLocalTorqueApplicationQualified=$true
 completeWheelMaterialAggregationQualified=$true;fastVehicleSinCosQualifiedWithinArgumentDomain=$true
 positionIslandOrderQualifiedWithinScalarTrigDomain=$true;modelCenterFrameShiftQualified=$true;preparedGeneralJointPositionPassesQualified=$true;generalJointPreparationQualified=$false
 positionAngularCorrectionLimit=1.57079625;boundedAvxFmaTrigQualified=$true;largeAngleTrigReductionQualified=$false;originalWholeFmaPositionIslandLoopQualified=$false
 sphereSphereGeometryQualified=$true;sphereCookedMeshGeometryQualified=$true;nativeTreeConstructionQualified=$true;convexSatQualified=$true;faceContactClippingQualifiedWithinDomain=$true;collisionDispatchTypes=20;collisionDispatchEntries=400
 collisionRegisteredOrderedPairs=$dispatch.registeredOrderedPairs;allRegisteredCollisionHandlersPorted=$false
 casesPerOperation=20000;bitExactInDifferentialTests=$true
 normalContactSolversQualified=$true;poseFractionSelectionQualified=$true;conditionalSuspensionMode2Qualified=$true
 mode2SuspensionForceTorqueQualifiedWithWakeQueueDisabled=$true;fullSuspensionForceApplicationQualified=$false;completeAdaptiveSchedulerQualified=$false
 wholeOrdinaryTextAtlasProcedures=$atlas.procedures;wholeAtlasLinearEdges=$atlas.edges;wholeAtlasRejectedIncompleteProcedures=$atlas.rejectedIncompleteProcedures
 capturedMeshPrototypes=351;capturedRayCacheTriangles=795089;capturedGroundedReferenceRayHits=400;capturedGroundedMaterialMatches=399;completeMapCollisionVerified=$false
 completeSemanticReverseOfGame=$false
 boundedDebuggerOwnedFixtureValidated=$true;boundedDebuggerAbortCleanupValidated=$true
 actualGamePhaseCaptureValidated=$false;liveDebuggerCaptureEnabledByDefault=$false
 poseQuaternionMatrixOracle='original instructions executed in owned test process'
 forceVelocityOracle='unmodified original x64 procedure emulated with synthetic inputs/TLS'
 originalSolverConstructorDefaultsExact=[bool]$oracle.solver_constructor_bytes_exact
 standaloneKernelRunner=$true;snapshotRestoreVerified=$true;gameRequiredByRunner=$false
 physicsProceduresInspected=$graph.analyzedProcedures.Count;graphTruncated=[bool]$graph.graphTruncated
 vehicleCase5Root='0x851f00';stablePlayerRootVerified=$false;internalPhysicsTickVerified=$false
 completeVehiclePhysicsPorted=$false;fullHeadlessTrackmaniaSimulatorReady=$false
}
$report | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $root 'local\physics-research-0.25.0.json') -Encoding UTF8
Write-Output 'PASS PHYSICS RESEARCH: 72 public arithmetic operations, including cooked mesh/tree, convex SAT/face clipping and curve/suspension force arithmetic; full simulator remains unqualified.'
