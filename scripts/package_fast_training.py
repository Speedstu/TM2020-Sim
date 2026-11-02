"""Freeze the qualified Linux bot, its evidence and matching source identities."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from run_fast_ppo import ROOT, LIBRARY, TRAINER


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main(a):
    destination=a.output.resolve()
    destination.mkdir(parents=True,exist_ok=False)
    def copy(source,relative):
        source=Path(source)
        target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
    candidate=ROOT/'local/recon/fast-0.37/release-candidate'
    official=json.loads((candidate/'official-final/report.json').read_text())
    if digest(LIBRARY)!=official['librarySha256'] or digest(candidate/'policy.tmppo')!=official['modelSha256']:
        raise ValueError('Binaries/model differ from original-physics qualification')
    final=ROOT/'local/recon/fast-0.37/candidate-planner-update0/final-unseen-30/report.json'
    measured=json.loads(final.read_text())
    if measured['candidate']['finishes']!=30 or measured['candidate']['trials']!=30:
        raise ValueError('Final held-out qualification did not finish all thirty races')
    copy(LIBRARY,'lib/libtm2020_fast.so')
    copy(TRAINER,'bin/tm2020_fast_train')
    copy(ROOT/'native/build-linux/libtm2020_policy.so','lib/libtm2020_policy.so')
    copy(candidate/'policy.tmppo','models/route-planner-ppo.tmppo')
    copy(candidate/'config.json','models/route-planner-ppo.config.json')
    copy(ROOT/'local/recon/fast-0.37/candidate-network-v2/policy.tmppo','models/route-network-ppo.tmppo')
    copy(ROOT/'integrations/fast-training/fast_training.h','include/fast_training.h')
    for name in ['LICENSE','NOTICE.md']:
        copy(ROOT/'integrations/fast-training'/name,name)
    copy(ROOT/'docs/PHYSICS_0_37_FAST_PPO.md','RECHERCHE.md')
    for source,name in [
        (candidate/'official-final/report.json','original-physics.json'),
        (final,'heldout-30.json'),
        (ROOT/'local/recon/fast-0.37/candidate-planner-update0/heldout-physical-10/report.json','heldout-10.json'),
        (ROOT/'local/recon/fast-0.37/candidate-network-v2/heldout-30/report.json','network-heldout-30.json'),
        (ROOT/'local/recon/fast-0.37/ppo-planner-v4/audit-0-final/report.json','physics-ppo-audit.json'),
        (ROOT/'local/recon/fast-0.37/ppo-planner-v4/audit-0-final/behavior.json','behavior-audit.json'),
        (ROOT/'local/recon/fast-0.37/environment-checks-final/report.json','environment-checks.json'),
        (ROOT/'local/recon/fast-0.37/optimized-equivalence.json','planner-equivalence.json'),
        (ROOT/'local/recon/fast-0.37/benchmark-vector16/report.json','throughput-without-planning.json'),
        (ROOT/'cache/gearbox-linux-0.37/portability.json','portability.json'),
    ]:copy(source,'evidence/'+name)
    for source in ['tm-fast-ctest-final.log','tm-fast-ppo-optimized.log']:
        copy(Path('/tmp')/source,'evidence/'+source)
    (destination/'run.py').write_text('''"""Run this frozen cohort from its original extracted project."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_fast_ppo as runner
runner.LIBRARY=HERE/'lib/libtm2020_fast.so'
runner.TRAINER=HERE/'bin/tm2020_fast_train'
if len(sys.argv)>1 and sys.argv[1]=='build':
    raise SystemExit('Build using scripts/run_fast_ppo.py build; this folder freezes the tested binaries.')
runner.main()
''')
    (destination/'LANCER.md').write_text('''# Bot Linux headless — cohorte figée 0.37

Ce dossier reste dans le projet extrait : les scripts et cartes sont dans la
racine du transfert, les Packs dans votre installation Steam. Aucun asset du
jeu n'est distribué ici. Le bot avec anticipation utilise la route connue
d'Autumn 01. PPO corrige un planificateur physique, avec 30/30 arrivées et
21,954 s de moyenne sur les dernières perturbations non utilisées en sélection.

Depuis la racine du projet :

```sh
python3 dist/fast-training-linux-0.37/run.py eval --trials 10 --model dist/fast-training-linux-0.37/models/route-planner-ppo.tmppo --output local/mon-test
python3 dist/fast-training-linux-0.37/run.py train --updates 8 --model dist/fast-training-linux-0.37/models/route-planner-ppo.tmppo --output local/mon-nouvel-entrainement
python3 dist/fast-training-linux-0.37/run.py bench --output local/mon-debit
```

Chaque sortie doit être nouvelle. Le benchmark mesure les ticks sans recherche
anticipée ; celle-ci est plus lente puisqu'elle simule 17 avenirs par décision.
Le modèle `route-network-ppo.tmppo` s'évalue avec `--controller geometric` :
son taux de réussite mesuré est 26/30, inférieur au modèle avec anticipation.
Ce paquet ne revendique pas le reverse complet du jeu ni une maîtrise de toutes
les cartes. Les preuves et les limites précises figurent dans RECHERCHE.md.

Les sources du projet sont dans `integrations/fast-training`, `native` et
`scripts`. Une archive de sources du moteur amont et du port est conservée dans
`backups/gearbox-fast-training-corresponding-sources-0.37.zip`, en complément de
`backups/trackmania2020-re-source-0.37.0.zip`. Licence : GPL-3.0-or-later.
'''.replace('fast-training-linux-0.37/', destination.name+'/').replace('source-0.37.0.zip','source-0.37-final.zip'))
    manifest=dict(schema='tm2020_frozen_fast_training_package_v1',
                  qualifiedMap='Autumn 2026-01',upstreamRevision='e0583ee55168e950a65a645778e591bd26b6a0f2',
                  officialFinishMs=official['finishMs'],heldOutEvaluation=measured,
                  fullGameReverseEngineeringComplete=False,
                  files={p.relative_to(destination).as_posix():digest(p) for p in sorted(destination.rglob('*')) if p.is_file()})
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('FROZEN_FAST_TRAINING_PACKAGE',destination,len(manifest['files']),'files')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'dist/fast-training-linux-0.37.1')
    main(p.parse_args())
