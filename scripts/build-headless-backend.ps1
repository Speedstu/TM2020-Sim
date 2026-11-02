param([switch]$InstallPythonDependencies)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$oldRustup=[Environment]::GetEnvironmentVariable('RUSTUP_HOME','Process')
$oldTarget=[Environment]::GetEnvironmentVariable('CARGO_TARGET_DIR','Process')
function Assert-HeadlessExit([string]$message){if($LASTEXITCODE -ne 0){throw $message}}
try {
 $env:RUSTUP_HOME=Join-Path $root 'cache/rustup-gearbox'
 $env:CARGO_TARGET_DIR=Join-Path $root 'cache/gearbox-host-target'
 rustup toolchain install 1.99 --profile minimal
 Assert-HeadlessExit 'Task-local Rust installation failed'
 cargo +1.99 build --release --locked --manifest-path (Join-Path $root 'integrations/gearbox-host/Cargo.toml') --bins
 Assert-HeadlessExit 'Pinned external engine host build failed'
 cmake -S (Join-Path $root 'native') -B (Join-Path $root 'native/build') -G 'MinGW Makefiles' -DCMAKE_BUILD_TYPE=Release
 Assert-HeadlessExit 'Native configure failed'
 cmake --build (Join-Path $root 'native/build') --parallel 4
 Assert-HeadlessExit 'Native SDK build failed'
 if($InstallPythonDependencies){
  python -m pip install --target (Join-Path $root 'tools/rl-python') -r (Join-Path $root 'integrations/gearbox-host/requirements-gym.txt')
  Assert-HeadlessExit 'Isolated Gym dependencies failed'
 }
} finally {
 [Environment]::SetEnvironmentVariable('RUSTUP_HOME',$oldRustup,'Process')
 [Environment]::SetEnvironmentVariable('CARGO_TARGET_DIR',$oldTarget,'Process')
}
