#!/usr/bin/env python3
"""Freeze verified binaries, shared policy, proofs and corresponding GPL source."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
VERSION='0.39.1'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    candidate=ROOT/'local/recon/generalist-0.39/release-candidate'
    package=ROOT/f'dist/generalist-linux-proton-{VERSION}'
    archive=ROOT/f'backups/trackmania2020-generalist-linux-proton-{VERSION}.zip'
    source=ROOT/f'backups/trackmania2020-re-source-{VERSION}-final.zip'
    for p in (package,archive,source):
        if p.exists():raise ValueError('Never overwrite retained delivery: '+str(p))
    selection=json.loads((candidate/'selection.json').read_text())
    library=ROOT/'cache/fast-training-final-target/release/libtm2020_generalist.so'
    if sha(candidate/'policy.tmppo')!=selection['policySha256'] or sha(library)!=selection['librarySha256']:
        raise ValueError('Frozen model or physics differs from selection evidence')
    live=json.loads((candidate/'live-4seconds/report.json').read_text())
    if not live['workerReturnedNormally'] or not live['inProcessInferenceObserved'] or live['modelSha256']!=selection['policySha256']:
        raise ValueError('The exact frozen policy has not passed injected inference')
    if sha(ROOT/'local/recon/deployment-0.39/tm2020_generalist_runtime.dll')!=live['dllSha256']:
        raise ValueError('Runtime DLL differs from injected driving evidence')
    files={
      'policy.tmppo':candidate/'policy.tmppo',
      'training.checkpoint':candidate/'training.checkpoint',
      'lib/libtm2020_generalist.so':library,
      'lib/libtm2020_policy.so':ROOT/'native/build-linux/libtm2020_policy.so',
      'bin/tm2020_generalist_train':ROOT/'native/build-linux/tm2020_generalist_train',
      'bin/tm2020_local_dll_loader.exe':ROOT/'local/recon/deployment-0.39/tm2020_local_dll_loader.exe',
      'bin/tm2020_generalist_runtime.dll':ROOT/'local/recon/deployment-0.39/tm2020_generalist_runtime.dll',
      'LANCER.md':ROOT/'docs/TRAIN_AND_PLAY_0_39.md',
      'LICENSE':ROOT/'integrations/generalist-training/LICENSE',
      'NOTICE.md':ROOT/'integrations/generalist-training/NOTICE.md',
      'training-maps.txt':ROOT/'local/recon/generalist-0.39/multimap-ppo-v3/maps.txt',
      'evidence/selection.json':candidate/'selection.json',
      'evidence/training.json':ROOT/'local/recon/generalist-0.39/multimap-ppo-v3/report.json',
      'evidence/updates.csv':ROOT/'local/recon/generalist-0.39/multimap-ppo-v3/updates.csv',
      'evidence/unseen-maps.json':candidate/'unseen-maps/report.json',
      'evidence/live.json':candidate/'live-4seconds/report.json',
      'evidence/live.csv':candidate/'live-4seconds/driving.csv',
      'evidence/live-inference-audit.json':candidate/'live-4seconds/inference-audit.json',
      'evidence/stop.json':ROOT/'local/recon/generalist-0.39/live-stop-v3/stop-audit-corrected.json',
      'evidence/stop-worker-status.txt':ROOT/'local/recon/generalist-0.39/live-stop-v3/worker.status',
      'evidence/rejected-model.json':ROOT/'local/recon/generalist-0.39/rejected-incompatible-model/report.json',
      'evidence/engine-checks.json':ROOT/'local/recon/generalist-0.39/engine-checks-final.json',
      'evidence/rollout-audit.json':ROOT/'local/recon/generalist-0.39/rollout-audit-v3/report.json',
      'evidence/resume-check.json':ROOT/'local/recon/generalist-0.39/resume-check-v1/report.json',
      'evidence/resume-configuration.json':ROOT/'local/recon/generalist-0.39/resume-check-v1/config.json',
      'evidence/benchmark.json':ROOT/'local/recon/generalist-0.39/release-benchmark/report.json',
      'evidence/body-removal-regression.json':ROOT/'local/recon/generalist-0.39/removed-body-regression.json',
      'sources/gearbox-corresponding-sources-0.37.zip':ROOT/'backups/gearbox-fast-training-corresponding-sources-0.37.zip',
    }
    for p in files.values():
        if not p.is_file():raise FileNotFoundError(p)
    subprocess.run([sys.executable,str(ROOT/'scripts/snapshot_source.py'),'--output',str(source)],check=True,cwd=ROOT)
    files[f'sources/project-sources-{VERSION}.zip']=source
    for name,p in files.items():
        target=package/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    launcher='''#!/usr/bin/env python3
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_generalist_ppo as cli
cli.LIBRARY=HERE/'lib/libtm2020_generalist.so'
cli.TRAINER=HERE/'bin/tm2020_generalist_train'
cli.RUNTIME_DLL=HERE/'bin/tm2020_generalist_runtime.dll'
cli.LOADER=HERE/'bin/tm2020_local_dll_loader.exe'
if len(sys.argv)>1 and sys.argv[1] in ('train','eval','live'):
    if '--model' not in sys.argv and '--resume' not in sys.argv:
        sys.argv+=['--model',str(HERE/'policy.tmppo')]
    if sys.argv[1]=='train':
        if '--map-list' not in sys.argv and '--map' not in sys.argv:
            sys.argv+=['--map-list',str(HERE/'training-maps.txt')]
        if '--environments' not in sys.argv:
            sys.argv+=['--environments','28']
cli.main()
'''
    (package/'run.py').write_text(launcher)
    manifest={'version':VERSION,'schema':'tm2020_generalist_delivery_v1','projectRootRequired':str(ROOT),
              'modelSha256':selection['policySha256'],'gameAssetsIncluded':False,
              'unseenMapStrengthQualified':False,'files':[]}
    for p in sorted(package.rglob('*')):
        if p.is_file():manifest['files'].append({'path':str(p.relative_to(package)),'bytes':p.stat().st_size,'sha256':sha(p)})
    (package/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with ZipFile(archive,'x',ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file():z.write(p,str(p.relative_to(ROOT/'dist')))
    with ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('Archive CRC failed')
    archive.with_suffix('.sha256').write_text(sha(archive)+'  '+archive.name+'\n')
    print(json.dumps({'package':str(package),'archive':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive)},indent=2))

if __name__=='__main__':main()
