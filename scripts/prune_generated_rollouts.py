#!/usr/bin/env python3
"""Bounded cleanup of regenerated per-update physics/rollout data in completed runs.

Never delete checkpoints, exported models, metrics, summaries, sources, original
game assets, or the newest/best/reference update's sampled rollout. Use --apply
only after inspecting dry-run results. Complete runs require report.json,
best.json, and best.checkpoint in the same parent as update-* directories.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'local'
NAMES={'physics.bin','rollout.bin','rollout.csv'}
ACTIVE={'discrete33-antiplateau-20261030','internal-continuous-resume-20261030'}
def plan():
    candidates=[]
    preserved=0
    skipped=0
    groups={}
    for file in DATA.rglob('*'):
        if not file.is_file() or file.name not in NAMES:continue
        update_dir=file.parent
        if not update_dir.name.startswith('update-'):continue
        if any(a in file.parts for a in ACTIVE):skipped+=1;continue
        run=update_dir.parent
        if not all((run/x).is_file() for x in ('report.json','best.json','best.checkpoint')):
            skipped+=1;continue
        try:
            idx=int(update_dir.name.split('update-',1)[1])
            report=json.loads((run/'report.json').read_text())
            best=json.loads((run/'best.json').read_text())
            final=int(report['updates'])
            best_idx=int(best['update'])
        except (ValueError,KeyError,TypeError,FileNotFoundError,json.JSONDecodeError):
            skipped+=1;continue
        if final<1 or not 0<=idx<=final:
            skipped+=1;continue
        # Keep clear audit sample, plus best, latest and every tenth update of a 1000-step run.
        checkpoints={0,final,best_idx,final//4,final//2,3*final//4}
        if idx in checkpoints:
            preserved+=1;continue
        candidates.append((file,file.stat().st_size))
        name=str(run.relative_to(ROOT))
        groups.setdefault(name,[0,0])
        groups[name][0]+=1;groups[name][1]+=file.stat().st_size
    return candidates,groups,preserved,skipped
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    candidates,groups,preserved,skipped=plan()
    total=sum(s for _,s in candidates)
    print(json.dumps({'mode':'APPLY' if args.apply else 'DRY_RUN',
                      'files':len(candidates),'bytes':total,'gb':round(total/1e9,3),
                      'runGroups':len(groups),'preservedSamples':preserved,
                      'skippedWithoutValidCompleteReport':skipped,
                      'largestGroups':sorted(
                         [{'run':k,'files':v[0],'gb':round(v[1]/1e9,2)} for k,v in groups.items()],
                         key=lambda v:-v['gb'])[:12]},indent=2),flush=True)
    if not args.apply:return
    manifest=ROOT/'local/cleanup'/f'rollout-pruning-20261030.jsonl'
    manifest.parent.mkdir(exist_ok=True,parents=True)
    if manifest.exists():raise RuntimeError('Manifest exists; refused to repeat')
    # Manifest before deleting, so every removed path remains auditable.
    with manifest.open('x') as f:
        f.write(json.dumps({'created':datetime.now().isoformat(),
                            'kind':'reproducible simulation cache pruning',
                            'count':len(candidates),'bytes':total})+'\n')
        for file,size in candidates:
            f.write(json.dumps({'path':str(file.relative_to(ROOT)),'bytes':size})+'\n')
        f.flush()
    removed=0;bytes_removed=0
    for file,size in candidates:
        if file.is_file() and file.name in NAMES:
            file.unlink()
            removed+=1;bytes_removed+=size
    (manifest.parent/'rollout-pruning-summary.json').write_text(json.dumps({
      'removedFiles':removed,'removedBytes':bytes_removed,'manifest':str(manifest.relative_to(ROOT)),
      'retained':'best/initial checkpoints, models, metrics, run reports and six selected update samples per run',
      'excluded':'active runs, unmatched/incomplete runs, source datasets, game assets'},indent=2)+'\n')
    print(f'DONE removed={removed} bytes={bytes_removed}',flush=True)
if __name__=='__main__':main()
