#!/usr/bin/env python3
"""Audit original inputs and visual observations, retaining source provenance."""
import argparse,csv,hashlib,json,subprocess,time
from pathlib import Path
import numpy as np
from prepare_fall_campaign import ROOT,fetch,save_json,save

OUT=ROOT/'local/training/human-rework-0.70'
META=ROOT/'cache/training-metadata-target/release/tm2020-training-metadata'


def segment_labels(times,samples):
    st=np.array([s['ms'] for s in samples]);ix=np.clip(np.searchsorted(st,times,side='right')-1,0,len(st)-1)
    ground=np.array([s['vehicle']['ground_contact'] for s in samples]);landings=st[np.flatnonzero(ground & ~np.r_[ground[0],ground[:-1]])]
    labels=[]
    for t,k in zip(times,ix):
        v=samples[k]['vehicle']
        labels.append('air' if not v['ground_contact'] else 'post_landing_300ms' if np.any((t>=landings)&(t<landings+300)) else
            'drift_proxy' if abs(v['side_speed'])>5 else 'curve_proxy' if abs(v['steer'])>.15 else 'straight_proxy')
    return np.asarray(labels),ix


def segment_metrics(a,t,labels):
    reports={}
    for name in ['all',*sorted(set(labels))]:
        mask=np.ones(len(a),dtype=bool) if name=='all' else labels==name
        adj=mask[1:]&mask[:-1]&(np.diff(t)==10);d=np.diff(np.rint(a[:,2]*127));changes=adj&(d!=0)
        change_indices=np.flatnonzero(changes);rev=0;jitter=0
        for u,v in zip(change_indices,change_indices[1:]):
            if t[v]-t[u]<=100 and mask[u:v+2].all() and d[u]*d[v]<0:
                rev+=1;jitter+=int(max(abs(d[u]),abs(d[v]))<=2)
        holds=[];start=None
        for i in range(len(a)):
            if mask[i] and (start is None):start=i
            if start is not None and (not mask[i] or i==len(a)-1 or (i>start and a[i,2]!=a[i-1,2])):
                holds.append(max(1,i-start)*10);start=i if mask[i] else None
        def run_lengths(signal,active_value):
            values=[];begin=None
            for i in range(len(signal)):
                if not mask[i] or signal[i]!=active_value:
                    if begin is not None:values.append((i-begin)*10);begin=None
                elif begin is None:begin=i
                elif signal[i]!=signal[i-1]:values.append((i-begin)*10);begin=i
            if begin is not None:values.append((len(signal)-begin)*10)
            return values
        gas_holds=run_lengths(a[:,0],1);gas_releases=run_lengths(a[:,0],0)
        brake_holds=run_lengths(a[:,1],1);brake_releases=run_lengths(a[:,1],0)
        duration=mask.sum()*.01
        reports[name]={'ticks':int(mask.sum()),'seconds':duration,'steeringChangesPerSecond':int(changes.sum())/max(duration,.01),
            'rawSteeringStepP50P95P99':np.percentile(np.abs(d[adj]),[50,95,99]).tolist() if adj.any() else [],
            'steeringVariationPerSecond':float(np.abs(d[adj]).sum()/127/max(duration,.01)),
            'reversalsWithin100ms':rev,'smallReversalsWithin100ms':jitter,
            'holdMsP10P50P90':np.percentile(holds,[10,50,90]).tolist() if holds else [],
            'holdMsP50P90':np.percentile(holds,[50,90]).tolist() if holds else [],
            'gasPressMsP10P50P90':np.percentile(gas_holds,[10,50,90]).tolist() if gas_holds else [],
            'gasReleaseMsP10P50P90':np.percentile(gas_releases,[10,50,90]).tolist() if gas_releases else [],
            'brakePressMsP10P50P90':np.percentile(brake_holds,[10,50,90]).tolist() if brake_holds else [],
            'brakeReleaseMsP10P50P90':np.percentile(brake_releases,[10,50,90]).tolist() if brake_releases else [],
            'gasTransitionsPerSecond':int(np.count_nonzero(np.diff(a[:,0])[adj]))/max(duration,.01),
            'brakeTransitionsPerSecond':int(np.count_nonzero(np.diff(a[:,1])[adj]))/max(duration,.01),
            'longSteeringHoldsAbove100ms':int(np.count_nonzero(np.asarray(holds)>100)),
            'steeringMicroTapsAtMost20ms':int(np.count_nonzero(np.asarray(holds)<=20)),
            'gasDuty':float(a[mask,0].mean()) if mask.any() else None,'brakeDuty':float(a[mask,1].mean()) if mask.any() else None,
            'gasChanges':int(np.count_nonzero(np.diff(a[:,0])[adj])),
            'brakeChanges':int(np.count_nonzero(np.diff(a[:,1])[adj]))}
    return reports


def analyze(path,kind,index,out):
    decoded=json.loads(subprocess.check_output([str(META),'analysis',str(path)],text=True));assert len(decoded['ghosts'])==1
    g=decoded['ghosts'][0];timeline={}
    for group in g['groups']:
        if group['truncated_at'] is not None:raise ValueError('Truncated original inputs')
        for k,c in enumerate(group['ticks']):
            t=group['start_offset_ms']+10*k
            if 0<=t<g['declaredMs']:timeline[t]=[int(c['gas']),int(c['brake']),max(-1,c['steer']/127)]
    t=np.array(sorted(timeline));a=np.array([timeline[k] for k in t],dtype=np.float32)
    if not len(t) or t[0]!=0 or not (np.diff(t)==10).all():raise ValueError('Input clock is not a complete contiguous 100Hz stream')
    sample_by_time={s['ms']:s for s in g['visualSamples']};samples=[sample_by_time[k] for k in sorted(sample_by_time) if 0<=k<g['declaredMs']]
    if not samples:raise ValueError('No visual samples')
    labels,ix=segment_labels(t,samples);visual=np.array([[s['vehicle'][k] for k in ('gas','brake','steer')] for s in samples])
    split=[x for x in g['checkpointMs'] if x is not None]
    result={'source':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'mapIndex':index,
        'mapUid':decoded['mapUid'],'kind':kind,'humanOriginIndependentlyVerified':False,'declaredMs':g['declaredMs'],
        'validationSeed':g['validationSeed'],'respawns':g['respawns'],'inputHz':100,
        'visualIntervalsMs':sorted(set(np.diff([s['ms'] for s in samples]).tolist())),
        'inputCoverageMs':[int(t[0]),int(t[-1])],'rawPedalsAreBinary':bool(np.isin(a[:,:2],[0,1]).all()),
        'checkpointCumulativeMs':split,'checkpointSplitsMs':np.diff([0,*split]).tolist(),
        'rawVsVisualMeanAbsoluteError':np.abs(a-visual[ix]).mean(axis=0).tolist(),
        'rawVsVisualNotPhysicalWheelAngle':True,'segments':segment_metrics(a,t,labels),
        'recoveryAfterArtificialPerturbationObservableInReplay':False}
    out.mkdir(parents=True,exist_ok=True);save_json(out/'analysis.json',result);save_json(out/'decoded-original.json',decoded)
    np.savez_compressed(out/'timeline.npz',ms=t,controls=a,segment=labels,visual_ms=np.array([s['ms'] for s in samples]),
        visual_controls=visual,position=np.array([s['vehicle']['position'] for s in samples]),speed=np.array([s['vehicle']['speed'] for s in samples]))
    return result


def figures(out,results):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,2,figsize=(13,10),constrained_layout=True)
    for row,i in enumerate((1,3,6)):
        files=[r for r in results if r['mapIndex']==i];ax=axes[row,0];sp=axes[row,1]
        for r in files:
            q=np.load(Path(r['directory'])/'timeline.npz');label=r['kind'];alpha=.8 if 'rank1' in label else .45
            if label=='leaderboard-rank1':ax.plot(q['ms']/1000,q['controls'][:,2],label='Original raw steer, reference',alpha=.85)
            if label=='bot-client':
                ax.plot(q['ms']/1000,q['controls'][:,2],label='Original replay inputs, bot',alpha=.6)
            p=q['position'];sp.plot(p[:,0],p[:,2],label=label,alpha=alpha)
        if i in (3,6):
            run='live03-original' if i==3 else 'live06-registers';rows=list(csv.DictReader((ROOT/f'local/recon/internal-0.65/{run}/control/physics.csv').open()))
            rows=[r for r in rows if int(r['wrote'])];start=rows[0]['race_start_ms'];rows=[r for r in rows if r['race_start_ms']==start and int(r['tick_ms'])-int(start)<files[0]['declaredMs']]
            ax.plot([(int(r['tick_ms'])-int(start))/1000 for r in rows],[float(r['steer']) for r in rows],label='Actual physical bot command',alpha=.6)
        ax.set(title=f'Fall {i:02d}: raw inputs and commands',xlabel='Race time (s)',ylabel='Normalized steering');ax.legend(fontsize=7)
        sp.set(title=f'Fall {i:02d}: recorded visual trajectories',xlabel='World X (m)',ylabel='World Z (m)');sp.axis('equal');sp.legend(fontsize=7)
    fig.savefig(out/'before-comparison.png',dpi=160);fig.savefig(out/'before-comparison.svg');plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=OUT/'corpus');p.add_argument('--download-extra',action='store_true');a=p.parse_args();out=a.output.resolve();results=[]
    for i in range(1,26):
        base=ROOT/f'local/training/fall-campaign-0.52/{i:02d}';sources=[('leaderboard-rank1',base/'reference.Ghost.Gbx')]
        if a.download_extra and i in (1,3,6):
            board=json.loads((base/'leaderboard.json').read_text())
            for entry in board['tops'][1:3]:
                path=out/f'{i:02d}/source-rank{entry["position"]}.Ghost.Gbx'
                if not path.exists():save(path,fetch('https://trackmania.io'+entry['url']));time.sleep(3)
                sources.append((f'leaderboard-rank{entry["position"]}',path))
        if i in (3,6):sources.append(('bot-client',OUT/f'preserved/client-{i:02d}.Replay.Gbx'))
        for kind,path in sources:
            d=out/f'{i:02d}/{kind}';r=analyze(path,kind,i,d);r['directory']=str(d);results.append(r)
            save_json(out/'inventory.json',{'sources':results,'excludedTasCorpus':'local/replays/tmtas-*.Replay.Gbx','humanCertificationNotAssumed':True})
            print(json.dumps({'map':i,'kind':kind,'ms':r['declaredMs'],'inputHz':r['inputHz']}),flush=True)
    figures(out,results)


if __name__=='__main__':main()
