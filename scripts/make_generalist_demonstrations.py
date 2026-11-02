#!/usr/bin/env python3
"""Export only train/validation maps; reserved test maps are never opened."""
import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus',type=Path,required=True);p.add_argument('--packs',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=4)
    a=p.parse_args()
    if a.output.exists():p.error('output must be new')
    a.output.mkdir(parents=True);corpus=json.loads(a.corpus.read_text());jobs=[]
    groups = {name: {m['leakageGroup'] for m in corpus['splits'][name]}
              for name in ('train', 'validation', 'test')}
    if any(groups[x] & groups[y] for x,y in
           [('train','validation'), ('train','test'), ('validation','test')]):
        raise ValueError('Corpus contains map groups shared between splits')
    for split in ('train','validation'):
        for m in corpus['splits'][split]:
            if m['demonstrations']:jobs.append((split,m))
    def export(job):
        split,m=job;name=m['mapSha256'][:16];target=a.output/(name+'.partial.csv')
        demo=m['demonstrations'][0]
        for file,expected in [(ROOT/m['map'],m['mapSha256']), (ROOT/demo['path'],demo['sha256'])]:
            if hashlib.sha256(file.read_bytes()).hexdigest()!=expected:
                raise ValueError(f'Corpus file changed: {file}')
        cmd=[str(ROOT/'cache/fast-training-final-target/release/tm2020-generalist-dataset'),
             str(ROOT/m['map']),str(a.packs.resolve()),str(ROOT/m['demonstrations'][0]['path']),str(target.resolve())]
        run=subprocess.run(cmd,text=True,capture_output=True,timeout=240)
        (a.output/(name+'.log')).write_text(run.stdout+'\n'+run.stderr)
        report={'split':split,'map':m['map'],'uid':m['mapUid'],'group':m['leakageGroup'],
                'mapSha256':m['mapSha256'],'returncode':run.returncode,'success':run.returncode==0}
        if run.returncode==0:
            target=target.rename(a.output/(name+'.csv'));report['csv']=str(target.resolve())
        print(json.dumps(report),flush=True);return report
    with ThreadPoolExecutor(max_workers=max(1,min(a.workers,8))) as pool:reports=list(pool.map(export,jobs))
    for split in ('train','validation'):
        with (a.output/(split+'.csv')).open('w') as out:
            header=None
            for r in reports:
                if r['split']!=split or not r['success']:continue
                with Path(r['csv']).open() as f:
                    line=next(f)
                    if header is None:header=line;out.write(header)
                    assert line==header
                    for line in f:out.write(line)
    (a.output/'report.json').write_text(json.dumps({'maps':reports,'testMapsOpened':False},indent=2)+'\n')

if __name__=='__main__':main()
