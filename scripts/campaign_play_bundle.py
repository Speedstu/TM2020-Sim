"""Freeze only qualified map-specific candidates for explicit local client tests."""
import hashlib
import json
from pathlib import Path
import numpy as np
from hybrid_tracking import load_asset
from prepare_fall_campaign import save_json,save


def freeze_candidate(result,metadata,directory,spawn_reference):
    report=result['nominal64'];threshold=metadata['top10TargetMs']
    if not report.get('count') or report.get('finishes')!=report['count'] or report.get('worstMs') is None or report['worstMs']>threshold:
        raise ValueError('Candidate has not reached the Top-10 time threshold in nominal simulation')
    source=Path(result['model']);data=source.read_bytes();digest=hashlib.sha256(data).hexdigest()
    if digest!=result['modelSha256']:raise ValueError('Model differs from qualified hash')
    path=Path(metadata['map'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=metadata['mapSha256']:raise ValueError('Map differs from qualified hash')
    ref,_,_=load_asset(source,map_path=path,uid=metadata['mapUid'])
    original=np.fromfile(spawn_reference,dtype='<f4').reshape(-1,25)
    spawn=original[0,9:12].tolist()
    directory=Path(directory);directory.mkdir(exist_ok=True,parents=True)
    model=directory/f'candidate-{digest[:20]}.tmhyb';save(model,data)
    entry={'index':metadata['index'],'mapUid':metadata['mapUid'],'name':metadata['name'],
        'map':str(path.resolve()),'mapSha256':metadata['mapSha256'],'model':str(model.resolve()),
        'modelSha256':digest,'spawn':spawn,'referenceFrames':len(ref),'nominalMs':report['worstMs'],
        'top10ThresholdMs':threshold,'nominalCount':report['count'],
        'nominalDistinctConditions':report.get('effectiveDistinctNominalConditions'),
        'perturbed':result.get('perturbed64'),'actualClientFinishVerified':False,'referenceAssisted':True}
    save_json(directory/'candidate.json',entry)
    return entry


def check_entry(entry):
    for key,sha in [('map','mapSha256'),('model','modelSha256')]:
        if hashlib.sha256(Path(entry[key]).read_bytes()).hexdigest()!=entry[sha]:raise ValueError(f'Prepared {key} changed')
    load_asset(entry['model'],map_path=entry['map'],uid=entry['mapUid'])


def check_qualification(report,entry,pid,start_ticks):
    if not report.get('physicalConsumerQualified') or not report.get('workerReturnedNormally'):
        raise ValueError('Current physical consumer was not qualified')
    if report.get('hostPid')!=pid or report.get('offlineProof',{}).get('processStartTicks')!=start_ticks:
        raise ValueError('Qualification belongs to another client process')
    if report.get('mapUid')!=entry['mapUid'] or report.get('mapSha256')!=entry['mapSha256']:
        raise ValueError('Qualification belongs to another map')
    if list(report.get('spawn',[]))!=list(entry['spawn']):raise ValueError('Qualification spawn differs')
    binding=report.get('binding') or {}
    if not all(isinstance(binding.get(k),int) and binding[k]>0 for k in ('manager','vehicle','body')):
        raise ValueError('Missing exact physical binding')


def build(source,output):
    source=Path(source);output=Path(output);output.mkdir(exist_ok=True,parents=True)
    entries=[]
    for path in sorted(source.glob('??/pursuit.json')):
        state=json.loads(path.read_text());result=state.get('selected')
        if not result:continue
        metadata=state['goal'];q=result['nominal64'];worst=q.get('worstMs')
        if worst is None or q.get('finishes')!=q.get('count') or worst>metadata['top10TargetMs']:continue
        entries.append(freeze_candidate(result,metadata,output/f"{metadata['index']:02d}",path.parent/'reference.f32'))
    manifest={'schema':'tm2020_local_campaign_candidates_v1','maps':entries,
        'source':str(source.resolve()),'modelUpdatesDuringPlay':False,'gameFinishVerified':False}
    save_json(output/'manifest.json',manifest)
    return manifest


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();m=build(a.source,a.output)
    print(json.dumps([{'map':v['index'],'simMs':v['nominalMs'],'top10Ms':v['top10ThresholdMs']} for v in m['maps']]))
