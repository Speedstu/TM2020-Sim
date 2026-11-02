param(
 [Parameter(Mandatory=$true)][string]$Output,
 [string]$Packs='D:/SteamLibrary/steamapps/common/Trackmania/Packs',
 [string]$Executable='D:/SteamLibrary/steamapps/common/Trackmania/Trackmania.exe',
 [switch]$SkipBuild
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$destination=[IO.Path]::GetFullPath($Output)
if(Test-Path -LiteralPath $destination){throw 'Evidence output must be a new directory'}
New-Item -ItemType Directory -Path $destination | Out-Null
function Assert-ExtensionExit([string]$message){if($LASTEXITCODE -ne 0){throw $message}}
python (Join-Path $PSScriptRoot 'prepare_gearbox_extensions.py')
Assert-ExtensionExit 'Pinned physics source preparation failed'
$patch=(Get-Content (Join-Path $root 'local/recon/gearbox-extensions-0.34-source-v2.json') -Raw | ConvertFrom-Json).physicsExtensionSha256
if(!$SkipBuild){
 $priorRustup=[Environment]::GetEnvironmentVariable('RUSTUP_HOME','Process')
 $priorTarget=[Environment]::GetEnvironmentVariable('CARGO_TARGET_DIR','Process')
 try {
  $env:RUSTUP_HOME=Join-Path $root 'cache/rustup-gearbox'
  $env:CARGO_TARGET_DIR=Join-Path $root 'cache/gearbox-extensions-target'
  rustup toolchain install 1.99 --profile minimal
  Assert-ExtensionExit 'Task-local Rust toolchain failed'
  cargo +1.99 build --release --locked --manifest-path (Join-Path $root 'integrations/gearbox-extensions/Cargo.toml') --bins
  Assert-ExtensionExit 'Extended engine build failed'
 } finally {
  [Environment]::SetEnvironmentVariable('RUSTUP_HOME',$priorRustup,'Process')
  [Environment]::SetEnvironmentVariable('CARGO_TARGET_DIR',$priorTarget,'Process')
 }
 cmake -S (Join-Path $root 'native') -B (Join-Path $root 'native/build') -G 'MinGW Makefiles' -DCMAKE_BUILD_TYPE=Release -DTM2020_ENABLE_EXPERIMENTAL_GAME_DEBUG_CAPTURE=OFF
 Assert-ExtensionExit 'Native SDK configure failed'
 cmake --build (Join-Path $root 'native/build') --parallel 4
 Assert-ExtensionExit 'Native SDK build failed'
}
$native=Join-Path $root 'native/build'
$binaries=Join-Path $root 'cache/gearbox-extensions-target/release'
$hostBinary=Join-Path $binaries 'tm2020-gearbox-extended-host.exe'
$map=Join-Path $root 'cache/gearbox-upstream-e0583ee/tests/golden/maps/pf-364816.Map.Gbx'
ctest --test-dir $native --output-on-failure --output-junit (Join-Path $destination 'native-tests.xml')
Assert-ExtensionExit 'Native regression failed'
& (Join-Path $native 'tm2020_geometry_gap_oracle.exe') $Executable (Join-Path $destination 'geometry-original') 20000
Assert-ExtensionExit 'Original geometry oracle failed'
& (Join-Path $native 'tm2020_wake_queue_oracle.exe') $Executable (Join-Path $destination 'wake-original')
Assert-ExtensionExit 'Original wake enqueue oracle failed'
python (Join-Path $PSScriptRoot 'test_active_slot_slice.py') --executable $Executable --oracle (Join-Path $native 'tm2020_active_slot_oracle.exe') --output (Join-Path $destination 'active-slot-original')
Assert-ExtensionExit 'Original active-list instruction slice failed'
& (Join-Path $binaries 'geometry_oracle_probe.exe') (Join-Path $destination 'geometry-original') (Join-Path $destination 'rust-oracle.json') (Join-Path $destination 'wake-original/wake-queue.cases')
Assert-ExtensionExit 'Rust/original differential failed'
$maps=@((Join-Path $root 'cache/gearbox-upstream-e0583ee/tests/golden/maps/pf-353727.Map.Gbx'),$map,(Join-Path $root 'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx'))
python (Join-Path $PSScriptRoot 'test_headless_engine.py') --host $hostBinary --packs $Packs --maps @maps --extension-sha256 $patch --output (Join-Path $destination 'cold')
Assert-ExtensionExit 'Extended cold-map checks failed'
python (Join-Path $PSScriptRoot 'test_engine_vehicle_matrix.py') --host $hostBinary --packs $Packs --map $map --extension-sha256 $patch --output (Join-Path $destination 'cars')
Assert-ExtensionExit 'Four-car integration checks failed'
python (Join-Path $PSScriptRoot 'test_headless_gym.py') --host $hostBinary --packs $Packs --map $map --extension-sha256 $patch --output (Join-Path $destination 'gym')
Assert-ExtensionExit 'Extended Gym boundary checks failed'
python (Join-Path $PSScriptRoot 'check_physics_extension_identity.py') --host $hostBinary --packs $Packs --map $map --extension-sha256 $patch --output (Join-Path $destination 'identity')
Assert-ExtensionExit 'Extension identity checks failed'
& (Join-Path $binaries 'physics_asset_catalog.exe') $Packs (Join-Path $destination 'asset-catalog.json')
Assert-ExtensionExit 'Installed vehicle reference catalog failed'
Write-Output "PASS PHYSICS EXTENSION CHECKS $destination"
