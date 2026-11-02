#!/usr/bin/env python3
"""Build the offline internal DLL, loader, owned probes and vector physics.

Cross tools are private to this repository. No system installs or game changes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from run_fast_ppo import ROOT

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--zig')
    p.add_argument('--output',type=Path,default=ROOT/'local/recon/deployment-0.46')
    p.add_argument('--native-build',type=Path,default=ROOT/'native/build-linux');a=p.parse_args()
    zig=a.zig or shutil.which('zig') or str(Path.home()/'Projects/EvilRLBot-Windows/build/zig/zig')
    if not Path(zig).is_file():raise FileNotFoundError('Use --zig with a Zig compiler')
    output=a.output.resolve();(output/'include').mkdir(parents=True,exist_ok=True)
    def run(args,env=None):subprocess.run(list(map(str,args)),cwd=ROOT,env=env,check=True)
    for name in ('Windows.h','TlHelp32.h'):(output/'include'/name).write_text('#include <'+name.lower()+'>\n')
    common=[zig,'c++','-target','x86_64-windows-gnu','-std=c++20','-O2','-I',output/'include',
            '-I',ROOT/'native/include','-I',ROOT/'integrations/generalist-training']
    shared=[ROOT/'native/src/read_only_live.cpp',ROOT/'native/src/visual_state.cpp']
    targets={
        'tm2020_local_dll_loader.exe':[*common,ROOT/'native/src/local_dll_loader.cpp',*shared,'-ladvapi32','-luser32'],
        'tm2020_generalist_runtime.dll':[*common,'-shared',ROOT/'integrations/generalist-training/runtime.cpp',*shared,ROOT/'native/src/rl.cpp','-ladvapi32','-luser32'],
        'tm2020_internal_perception_probe.exe':[*common,ROOT/'native/src/internal_perception_probe.cpp'],
        'tm2020_internal_policy_probe.exe':[*common,ROOT/'native/src/internal_policy_probe.cpp',ROOT/'native/src/rl.cpp']}
    for name,command in targets.items():
        tmp=output/('next-'+name);run([*command,'-o',tmp]);tmp.replace(output/name)
    rust=ROOT/'tools/rust-cross-0.46';mingw=ROOT/'tools/mingw-0.46/usr/bin'
    for exe in (rust/'bin/rustc',mingw/'x86_64-w64-mingw32-gcc',mingw/'x86_64-w64-mingw32-dlltool'):
        if not exe.is_file():raise FileNotFoundError(f'Private cross tool missing: {exe}')
    env=dict(os.environ,RUSTC=str(rust/'bin/rustc'),TM2020_ZIG=zig,
             CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER=str(mingw/'x86_64-w64-mingw32-gcc'),
             CARGO_TARGET_X86_64_PC_WINDOWS_GNU_RUSTFLAGS=f'--sysroot {rust} -C dlltool={mingw}/x86_64-w64-mingw32-dlltool',
             CC_x86_64_pc_windows_gnu=str(ROOT/'scripts/zig_link_windows.sh'),
             AR_x86_64_pc_windows_gnu=str(ROOT/'scripts/zig_ar_windows.sh'))
    run(['cargo','build','--release','--offline','--locked','--manifest-path','integrations/internal-perception/Cargo.toml',
         '--target','x86_64-pc-windows-gnu','--target-dir','cache/internal-perception-0.46-target','-j8'],env)
    shutil.copy2(ROOT/'cache/internal-perception-0.46-target/x86_64-pc-windows-gnu/release/tm2020_internal_perception.dll',output)
    run(['cmake','-S','native','-B',a.native_build,'-DCMAKE_BUILD_TYPE=Release'])
    run(['cmake','--build',a.native_build,'--target','tm2020_internal_tick_test','tm2020_hybrid_actions_test',
         'tm2020_internal_policy_probe','tm2020_vector_physics','tm2020_trajectory','-j8'])
    files=[*targets,'tm2020_internal_perception.dll']
    manifest={'files':{name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in files},
              'primaryActuation':'internal physics consumer, no peripheral fallback','gameFinishVerified':False}
    (output/'build.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
