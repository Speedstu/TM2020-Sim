#!/usr/bin/env python3
"""Per-map Top100 medians and slightly lower steering-activity preferences."""
import argparse
import json
from pathlib import Path
import numpy as np
from train_hardcode_recorded_inputs import BASE,ROOT,human_rhythm
from prepare_fall_campaign import save_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    rows=[]
    for index in range(1,26):
        folder=BASE/f'top100-cohort/{index:02d}'
        if not folder.exists():continue
        profile=human_rhythm(index)
        counts=[];reversals=[];ranks=[]
        for rank in profile['sourceRanks']:
            path=folder/f'leaderboard-rank{rank:03d}/timeline.npz'
            if not path.exists():continue
            with np.load(path) as d:controls=d['controls']
            steer=np.rint(controls[:,2]*127).astype(int);delta=np.diff(steer)
            at=np.flatnonzero(delta!=0)
            rev=sum(b-a<=10 and delta[a]*delta[b]<0 for a,b in zip(at[:-1],at[1:]))
            counts.append(int(len(at)));reversals.append(int(rev));ranks.append(rank)
        meta=json.loads((ROOT/f'local/training/fall-campaign-0.52/{index:02d}/map.json').read_text())
        doc={'map':index,'name':meta['name'],'source':'original decoded leaderboard Top100 ghosts',
            'usableGhosts':len(ranks),'decodedRanks':ranks,'profile':profile,
            'steeringChangesPerRunP10P25P50P75P90':np.percentile(counts,[10,25,50,75,90]).tolist(),
            'rapidReversalsPerRunP10P25P50P75P90':np.percentile(reversals,[10,25,50,75,90]).tolist(),
            'rawSteeringChangeCounts':counts,'rawRapidReversalCounts':reversals,
            'humanOriginIndependentlyVerified':False,'map01CandidateModified':False}
        save_json(a.output/f'{index:02d}.json',doc);rows.append({k:doc[k] for k in ('map','usableGhosts','steeringChangesPerRunP10P25P50P75P90')})
    save_json(a.output/'summary.json',{'maps':rows,'styleTarget':'slightly below median, performance and robustness first','inputHz':100})
    print(json.dumps(rows,indent=2))

if __name__=='__main__':main()
