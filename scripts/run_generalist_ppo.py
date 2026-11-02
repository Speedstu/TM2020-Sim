#!/usr/bin/env python3
"""Build/train/evaluate one route-free map-reading policy, or load it into Solo.

No expert route is required for training from scratch or deployment.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import struct
import sys
from run_fast_ppo import steam_packs

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'cache/fast-training-final-target'
LIBRARY=TARGET/'release/libtm2020_generalist.so'
TRAINER=ROOT/'native/build-linux/tm2020_generalist_train'
DEFAULT_MAP=ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx'


def run(command):subprocess.run(list(map(str,command)),cwd=ROOT,check=True)


def build(windows=False,zig=None):
    run([sys.executable,ROOT/'scripts/prepare_fast_training.py'])
    run(['cargo','build','--release','--offline','--locked','--manifest-path',
         ROOT/'integrations/generalist-training/Cargo.toml','--target-dir',TARGET])
    run(['cmake','-S',ROOT/'native','-B',ROOT/'native/build-linux','-DCMAKE_BUILD_TYPE=Release'])
    run(['cmake','--build',ROOT/'native/build-linux','--target',
         'tm2020_generalist_train','tm2020_generalist_warmstart','tm2020_gpu_helpers','tm2020_policy','-j','8'])
    if windows:
        run([sys.executable,ROOT/'scripts/build_internal_runtime.py',*(['--zig',zig] if zig else [])])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['build','checks','bench','train','eval','live'])
    p.add_argument('--windows',action='store_true');p.add_argument('--zig')
    p.add_argument('--packs',type=Path);p.add_argument('--map',type=Path,default=DEFAULT_MAP)
    p.add_argument('--library',type=Path,default=LIBRARY)
    p.add_argument('--map-list',type=Path,help='One absolute GBX map path per line; no replay')
    p.add_argument('--output',type=Path);p.add_argument('--model',type=Path);p.add_argument('--resume',type=Path)
    p.add_argument('--updates',type=int,default=100);p.add_argument('--environments',type=int,default=16)
    p.add_argument('--threads',type=int,default=12);p.add_argument('--rollout',type=int,default=128)
    p.add_argument('--horizon',type=int,default=4000);p.add_argument('--seed',type=int,default=2026)
    p.add_argument('--trials',type=int,default=3);p.add_argument('--noise',type=float,default=.3)
    p.add_argument('--seconds',type=float,default=20.);p.add_argument('--eval-every',type=int,default=20)
    p.add_argument('--live-mode',choices=['observe','control'],default='observe')
    p.add_argument('--qualification',type=Path);p.add_argument('--map-uid',default='ypPmohQofd72MyTsIsijKfrJH98')
    a=p.parse_args()
    if a.mode=='build':build(a.windows,a.zig);return
    if a.output is None:p.error('--output is required and must be new')
    if a.output.exists():p.error('output already exists; prior evidence is retained')
    packs=(a.packs or steam_packs()).resolve(strict=True)
    if a.mode=='checks':
        run([sys.executable,ROOT/'scripts/test_generalist_engine.py','--library',a.library,'--map',a.map,
             '--packs',packs,'--output',a.output]);return
    if a.mode=='live':
        command=[sys.executable,ROOT/'scripts/run_internal_live.py','--mode',a.live_mode,'--map',a.map,'--packs',packs,
                 '--map-uid',a.map_uid,'--seconds',a.seconds,'--output',a.output]
        if a.model:command+=['--model',a.model]
        if a.qualification:command+=['--qualification',a.qualification]
        run(command);return
    if a.mode=='eval' and not a.model:p.error('--model required')
    actions=3
    source=a.resume or a.model
    if source is not None:
        header=source.read_bytes()[:32]
        expected=b'TMTRAIN1' if a.resume else b'TMPPO001'
        if len(header)!=32 or header[:8]!=expected:p.error('Invalid checkpoint/model header')
        version,nx,actions,hidden,ns,reserved=struct.unpack_from('<6I',header,8)
        if version!=1 or nx not in (48,144,240) or actions not in (1,3):p.error('Policy dimensions differ')
    command=[TRAINER,'--mode',a.mode,'--library',a.library,'--map',a.map.resolve(strict=True),
             '--packs',packs,'--route','/dev/null','--output',a.output.resolve(),'--actions',actions,
             '--planner',0,'--residual',1,'--environments',a.environments,'--threads',a.threads,
             '--rollout',a.rollout,'--horizon',a.horizon,'--seed',a.seed,'--noise',a.noise,
             '--updates',a.updates,'--trials',a.trials,'--eval-every',a.eval_every]
    if a.map_list:command+=['--map-list',a.map_list.resolve(strict=True)]
    if a.model:command+=['--model',a.model.resolve(strict=True)]
    if a.resume:command+=['--resume',a.resume.resolve(strict=True)]
    run(command)


if __name__=='__main__':main()
