"""Hourly local training supervision, measured tuning, and verified map progression."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

from train_continuous import atomic_copy,atomic_json,atomic_link,read_json,score,publish_best,prune_evidence
from run_fast_ppo import ROOT,steam_packs
from validate_generalist_policy import metadata,validate

USER_AGENT='TM2020LocalTrainingMonitor/0.44 (hourly personal research)'
UNIT='tm2020-fall01-ppo.service'
VARIANTS=[(1e-5,.02),(5e-6,.015),(3e-5,.05),(1e-5,.06),(5e-5,.025),(2e-6,.01)]


def utc():return dt.datetime.now(dt.timezone.utc)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def seconds_since(value):return max(0.,(utc()-dt.datetime.fromisoformat(value)).total_seconds())


def run(command,log=None,timeout=900):
    """Let controllers shut their own workers down before escalating a timeout."""
    stream=Path(log).open('a') if log else subprocess.DEVNULL
    child=subprocess.Popen(list(map(str,command)),cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        try:code=child.wait(timeout=timeout)
        except (subprocess.TimeoutExpired,KeyboardInterrupt):
            child.terminate()
            try:child.wait(timeout=30)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            raise
        if code:raise RuntimeError(f'Command exited {code}: {command[0]}; see {log}')
    finally:
        if hasattr(stream,'close'):stream.close()


def systemctl(*args,check=True):
    return subprocess.run(['systemctl','--user',*args],capture_output=True,text=True,check=check,timeout=180)


def active_service():return systemctl('is-active',UNIT,check=False).stdout.strip()=='active'


def http(url,limit=20_000_000):
    request=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/json,application/octet-stream'})
    with urllib.request.urlopen(request,timeout=30) as response:
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError('Download exceeds bounded size')
    return data


def top_ten(uid,cache):
    if not uid or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for c in uid):raise ValueError('Invalid map UID')
    url=f'https://trackmania.io/api/leaderboard/map/{uid}?length=10&offset=0'
    raw=json.loads(http(url,2_000_000));tops=raw.get('tops',[])
    positions=[r.get('position') for r in tops]
    if positions!=list(range(1,11)):raise ValueError('Top ten ranks are incomplete')
    times=[r.get('time') for r in tops]
    if any(type(t)!=int or not 1000<=t<=600_000 for t in times) or times!=sorted(times):raise ValueError('Invalid leaderboard times')
    result={'mapUid':uid,'thresholdMs':times[-1],'fetchedUtc':utc().isoformat(),'sourceUrl':url,'scope':'world_personal_best',
            'tops':[{'position':r['position'],'time':r['time'],'ghostUrl':r.get('url')} for r in tops]}
    atomic_json(cache,result);return result


def gate(board,validation,model_hash,map_uid,now=None):
    """A simulated time, stale threshold or another model can never advance a map."""
    now=now or utc()
    try:
        age=(now-dt.datetime.fromisoformat(board['fetchedUtc'])).total_seconds()
        return (board['scope']=='world_personal_best' and board['mapUid']==map_uid and 0<=age<=7200
            and validation['status']=='OFFICIAL_TIME_VERIFIED' and validation['originalGamePhysicsExecuted'] is True
            and validation['modelSha256']==model_hash and validation['mapUid']==map_uid
            and validation['thresholdAchieved'] is True and 0<validation['finishMs']<board['thresholdMs'])
    except (KeyError,TypeError,ValueError):return False


def policy_matches_checkpoint(model,checkpoint):
    if len(model)<40 or len(checkpoint)<136 or model[:8]!=b'TMPPO001' or checkpoint[:8]!=b'TMTRAIN1':return False
    if model[8:32]!=checkpoint[8:32]:return False
    _,nx,na,h,ns,_=struct.unpack_from('<6I',model,8)
    count=h*(nx+1)+na*(h+1)+h*(nx+2)+1+na
    return len(model)==32+ns+count*8+8 and model[32:-8]==checkpoint[128:128+ns+count*8]


def snapshot_best(session,folder):
    """best.json is published last; retry if copying overlaps a promotion."""
    folder.mkdir(parents=True,exist_ok=False)
    for _ in range(30):
        before=read_json(session/'best.json')
        if before is not None:
            atomic_copy(session/'best.tmppo',folder/'best.tmppo');sha=atomic_copy(session/'best.checkpoint',folder/'best.checkpoint')
            after=read_json(session/'best.json')
            if before==after and sha==before['checkpointSha256'] and policy_matches_checkpoint((folder/'best.tmppo').read_bytes(),(folder/'best.checkpoint').read_bytes()):
                atomic_json(folder/'best.json',before);return before
        time.sleep(.05)
    raise RuntimeError('Could not snapshot a consistent champion')


def evaluate(model,track,library,output,seed,trials=20,horizon=4000):
    na=struct.unpack_from('<I',Path(model).read_bytes(),16)[0]
    run([ROOT/'native/build-linux/tm2020_generalist_train','--mode','eval','--library',library,'--map',track,
         '--packs',steam_packs(),'--route','/dev/null','--output',output,'--model',model,'--actions',na,
         '--planner',0,'--trials',trials,'--seed',seed,'--horizon',horizon],str(output)+'.log',timeout=180)
    return read_json(Path(output)/'report.json')['candidate']


def prepare_candidate(best,latest,output,learning_rate,std):
    from gpu_ppo import Helpers,Checkpoint
    import numpy as np
    helper=Helpers();cp=Checkpoint.load(best,helper);recent=Checkpoint.load(latest,helper)
    if (cp.nx,cp.na,cp.hidden,cp.schema)!=(recent.nx,recent.na,recent.hidden,recent.schema):raise ValueError('Candidate architecture differs')
    head=slice(cp.actor_count,cp.actor_count+cp.critic_count);cp.parameters[head]=recent.parameters[head]
    cp.shuffle=recent.shuffle;cp.sampler=recent.sampler
    cp.config=(learning_rate,*cp.config[1:]);cp.parameters[-1]=__import__('math').log(std)
    cp.first=np.zeros_like(cp.first);cp.second=np.zeros_like(cp.second);cp.step=0
    cp.save(output,helper)


def tune(config,active,session,folder,monitor_state,updates):
    """One bounded candidate per hourly plateau check, with a second validation suite."""
    track=Path(active['map']);library=Path(config['library']);horizon=active.get('horizon',4000)
    was_running=active_service();stopped=False
    result={'attempted':False,'promoted':False}
    if not was_running or (session/'STOP').exists():return result
    folder.mkdir()
    try:
        systemctl('stop',UNIT);stopped=True
        with (session/'supervisor.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            current=read_json(session/'state.json');champion=snapshot_best(session,folder/'reference')
            index=monitor_state.get('tuneAttempts',0);lr,std=VARIANTS[index%len(VARIANTS)]
            monitor_state['tuneAttempts']=index+1
            initial=folder/'initial.checkpoint'
            prepare_candidate(folder/'reference/best.checkpoint',current['latestCheckpoint'],initial,lr,std)
            job=folder/'trial'
            run([sys.executable,ROOT/'scripts/run_gpu_training.py','--directory',job,'--resume',initial,'--library',library,
                 '--map',track,'--updates',updates,'--rollout',1024,'--eval-every',5,'--eval-trials',20,
                 '--disturbance-probability',.5,'--horizon',horizon,'--seed',active['seed']],folder/'trial.log',timeout=1200)
            selected=read_json(job/'run/best.json');candidate=selected['evaluation'];result.update(attempted=True,learningRate=lr,steeringStd=std,updates=updates,selection=candidate)
            if score(candidate)>score(champion['evaluation']):
                seed=active['seed']+700000
                baseline=evaluate(folder/'reference/best.tmppo',track,library,folder/'confirmation-reference',seed,horizon=horizon)
                confirmation=evaluate(job/'run/best.tmppo',track,library,folder/'confirmation-candidate',seed,horizon=horizon)
                result.update(confirmationReference=baseline,confirmationCandidate=confirmation)
                if score(confirmation)>=score(baseline):
                    result['promoted']=publish_best(session,candidate,job/'run/best.tmppo',job/'run/best.checkpoint',
                        {'type':'hourly_tuning','report':str(folder/'report.json'),'trialUpdate':selected['update']})
            # Advance the RNG streams used in this experiment without mixing
            # its weights into the ongoing policy when the candidate loses.
            from gpu_ppo import Helpers,Checkpoint
            helper=Helpers();latest=Checkpoint.load(current['latestCheckpoint'],helper)
            final=Checkpoint.load(job/f'run/update-{updates-1}/training.checkpoint',helper)
            latest.shuffle=final.shuffle;latest.sampler=final.sampler
            temp=folder/'rng-continuation.checkpoint';latest.save(temp,helper)
            destination=session/'snapshots/monitor-rng.checkpoint';sha=atomic_copy(temp,destination)
            current.update(latestCheckpoint=str(destination),latestCheckpointSha256=sha,hourlyTuningReport=str(folder/'report.json'))
            atomic_json(session/'state.json',current);atomic_link(session/'latest.checkpoint',destination)
            prune_evidence(job,updates-1,1)
    finally:
        atomic_json(folder/'report.json',result)
        if stopped and was_running and not (session/'STOP').exists():systemctl('start',UNIT)
    return result


def ensure_map(item):
    path=Path(item['map'])
    if not path.exists():
        download_gbx(item['fileUrl'],path,'map',item['mapUid'])
    if metadata('map',path)['mapUid']!=item['mapUid']:raise ValueError('Map UID differs from campaign')
    return path


def download_gbx(url,path,kind,uid):
    data=http(url)
    if not data.startswith(b'GBX'):raise ValueError('Download is not GBX')
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.monitor-download') as temporary:
        temporary.write(data);temporary.flush()
        if metadata(kind,temporary.name)['mapUid']!=uid:raise ValueError('Downloaded GBX UID differs')
        # Atomic publication without replacing an existing file. A partial or
        # unparseable download never becomes the cache entry used next hour.
        os.link(temporary.name,path)


def source_replay(config,item,board):
    if item.get('sourceReplay'):
        path=Path(item['sourceReplay'])
    else:
        path=Path(config['directory'])/'sources'/f"{item['mapUid']}.Ghost.Gbx"
        if not path.exists():
            url=board['tops'][0]['ghostUrl']
            if not isinstance(url,str) or not url.startswith('/api/download/ghost/'):raise ValueError('Missing source ghost URL')
            download_gbx('https://trackmania.io'+url,path,'replay',item['mapUid'])
    if metadata('replay',path)['mapUid']!=item['mapUid']:raise ValueError('Source replay UID differs')
    return path


def render_unit(config,active,initial):
    args=['/usr/bin/python3','-u',ROOT/'scripts/train_continuous.py','--directory',active['session'],
          '--resume',initial/'initial.checkpoint','--baseline-model',initial/'initial.tmppo','--baseline-checkpoint',initial/'initial.checkpoint',
          '--map',active['map'],'--library',config['library'],'--restart-from-best','--rollout','1024','--eval-every','5',
          '--cycle-updates','40','--eval-trials','20','--disturbance-probability','.5','--horizon',active['horizon'],
          '--prior-updates','0','--prior-transitions','0','--seed',active['seed']]
    if any(any(c in str(a) for c in ('"','%','\n')) for a in args):raise ValueError('Unsafe systemd argument')
    command=' '.join('"'+str(a)+'"' for a in args)
    return f'''[Unit]
Description=Trackmania hourly-supervised CUDA PPO
[Service]
Type=simple
WorkingDirectory={ROOT}
ExecStart={command}
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=30
KillMode=mixed
TimeoutStopSec=180
Nice=5
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=default.target
'''


def advance(config,active,session,snapshot,validation,board,folder):
    index=active['index'];target_index=index+1
    archive=folder/'mastered';archive.mkdir()
    for name in ('best.tmppo','best.checkpoint','best.json'):atomic_copy(snapshot/name,archive/name)
    if not gate(board,validation,digest(archive/'best.tmppo'),active['mapUid']):raise ValueError('Promotion evidence does not match current champion')
    atomic_json(archive/'qualification.json',{'leaderboard':board,'officialValidation':validation})
    if target_index>=len(config['maps']):
        systemctl('stop',UNIT);return {**active,'campaignComplete':True}
    item=config['maps'][target_index];track=ensure_map(item)
    target={**item,'index':target_index,'session':str(ROOT/f'local/training/fall2026-{target_index+1:02d}-automatic'),
            'seed':971042+target_index*1000,'horizon':min(12000,max(4000,(item['authorScore']+4)//5))}
    if Path(target['session']).exists():raise ValueError('Next session already exists; refusing to overwrite it')
    # Load and run the map before touching the active service.
    evaluate(archive/'best.tmppo',track,config['library'],folder/'next-map-preflight',target['seed'],trials=1,horizon=target['horizon'])
    initial=folder/'next-initial'
    na=struct.unpack_from('<I',(archive/'best.tmppo').read_bytes(),16)[0]
    run([sys.executable,ROOT/'scripts/prepare_time_policy.py','--source',archive/'best.checkpoint','--output',initial,
         '--actions',na,'--learning-rate',3e-5,'--gae-lambda',1,'--steering-std',.03],folder/'prepare.log')
    unit=Path.home()/'.config/systemd/user'/UNIT;previous=unit.read_bytes();(folder/'previous.service').write_bytes(previous)
    was_running=active_service()
    try:
        systemctl('stop',UNIT);unit.write_text(render_unit(config,target,initial))
        run(['systemd-analyze','--user','verify',unit],folder/'verify-unit.log',timeout=30)
        systemctl('daemon-reload');systemctl('start',UNIT)
        deadline=time.monotonic()+150
        while time.monotonic()<deadline:
            state=read_json(Path(target['session'])/'state.json',{})
            if active_service() and state.get('totalTransitions',0)>0:return target
            time.sleep(1.)
        raise RuntimeError('Next map did not start producing transitions')
    except BaseException:
        systemctl('stop',UNIT,check=False);unit.write_bytes(previous);systemctl('daemon-reload')
        if was_running and not (session/'STOP').exists():systemctl('start',UNIT)
        raise


def monitor(config,force_tune=False,tune_updates=None):
    root=Path(config['directory']);root.mkdir(parents=True,exist_ok=True)
    owner=root/'owner.json'
    if not owner.exists():atomic_json(owner,{'schema':'tm2020_hourly_monitor_v1','project':str(ROOT)})
    if read_json(owner)!={'schema':'tm2020_hourly_monitor_v1','project':str(ROOT)}:raise ValueError('Monitor directory belongs to another project')
    with (root/'monitor.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (root/'STOP').exists():return
        active=read_json(root/'active.json',config['initialActive']);session=Path(active['session'])
        if not (root/'active.json').exists():atomic_json(root/'active.json',active)
        monitor_state=read_json(root/'state.json',{})
        stamp=utc().strftime('%Y%m%dT%H%M%S%fZ');folder=root/'runs'/stamp;folder.mkdir(parents=True)
        report={'createdUtc':utc().isoformat(),'mapUid':active['mapUid'],'map':active['name'],'session':str(session),'actions':[]}
        try:
            if active.get('campaignComplete'):
                report['status']='CAMPAIGN_COMPLETE';return
            if (session/'STOP').exists():report['status']='TRAINING_STOP_MARKER';return
            training=read_json(session/'state.json',{});running=active_service()
            enabled=systemctl('is-enabled',UNIT,check=False).returncode==0
            report.update(trainingServiceEnabled=enabled,trainingServiceActive=running)
            if (not running or seconds_since(training.get('updatedUtc',utc().isoformat()))>600):
                if enabled:
                    systemctl('restart' if running else 'start',UNIT);report['actions'].append('restarted_unhealthy_training')
                    report['trainingServiceActive']=active_service()
            if not enabled and not running:
                report['status']='TRAINING_DISABLED';return
            item=config['maps'][active['index']]
            if metadata('map',active['map'])['mapUid']!=active['mapUid']:raise ValueError('Active map identity differs')
            best=snapshot_best(session,folder/'champion');report['champion']=best
            report['training']=read_json(session/'state.json',{})
            report['freeDiskBytes']=shutil.disk_usage(ROOT).free
            try:
                board=top_ten(active['mapUid'],root/'leaderboard-latest.json');report['leaderboard']=board
            except Exception as error:
                board=None;report['leaderboardError']=str(error)
            if board is not None and best['evaluation']['bestFinishMs']<board['thresholdMs']:
                source=source_replay(config,item,board)
                validation=validate(folder/'champion/best.tmppo',active['map'],source,config['library'],folder/'official-validation',board['thresholdMs'])
                report['officialValidation']=validation
                if gate(board,validation,digest(folder/'champion/best.tmppo'),active['mapUid']):
                    # Archive the frozen, qualified snapshot, never a later
                    # champion paired with this actor's earlier evidence.
                    target=advance(config,active,session,folder/'champion',validation,board,folder)
                    atomic_json(root/'active.json',target);report['actions'].append('advanced_to_next_map')
                    report.update(status='CAMPAIGN_COMPLETE' if target.get('campaignComplete') else 'ADVANCED',nextMap=target['name']);return
            plateau=seconds_since(best['updatedUtc'])>=config.get('plateauSeconds',3600)
            if (force_tune or plateau) and report['freeDiskBytes']>10*1024**3:
                report['tuning']=tune(config,active,session,folder/'tuning',monitor_state,tune_updates or config.get('tuneUpdates',40))
                if report['tuning']['promoted']:report['championAfterTuning']=read_json(session/'best.json')
                monitor_state['lastTuneUtc']=utc().isoformat()
            report['status']='MONITORING' if board is not None else 'MONITORING_THRESHOLD_UNAVAILABLE'
        except Exception as error:
            report.update(status='CHECK_FAILED',error=f'{type(error).__name__}: {error}')
        finally:
            monitor_state.update(lastCheckUtc=utc().isoformat(),lastReport=str(folder/'report.json'))
            atomic_json(root/'state.json',monitor_state);atomic_json(folder/'report.json',report);atomic_json(root/'latest.json',report)
            with (root/'history.jsonl').open('a') as out:out.write(json.dumps(report)+'\n');out.flush();os.fsync(out.fileno())
            status=report.get('status','CHECKING');best=report.get('championAfterTuning',report.get('champion',{})).get('evaluation',{})
            board=report.get('leaderboard',{})
            (root/'status.md').write_text(f"# Trackmania — suivi horaire\n\nÉtat : {status}\n\nMap : {active['name']}\n\nDernier contrôle : {report['createdUtc']}\n\nValidation simulation : {best.get('finishes','?')}/{best.get('trials','?')}, moyenne {best.get('meanFinishMs','?')} ms.\n\nSeuil top 10 mondial : {board.get('thresholdMs','indisponible')} ms.\n\nRapport : {folder/'report.json'}\n")
            # Only prune sessions carrying this monitor's own report marker.
            runs=sorted((root/'runs').iterdir())
            disposable=[p for p in runs if re.fullmatch(r'\d{8}T\d{12}Z',p.name) and (p/'report.json').is_file() and not (p/'mastered').exists()
                        and not read_json(p/'report.json',{}).get('tuning',{}).get('promoted',False)]
            for old in disposable[:-48]:
                if old.is_symlink():raise ValueError('Refusing a symlink in monitor retention')
                shutil.rmtree(old)
            print(json.dumps({'status':report.get('status'),'report':str(folder/'report.json'),'actions':report['actions']}),flush=True)
        return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--force-tune',action='store_true');p.add_argument('--tune-updates',type=int)
    a=p.parse_args()
    if a.tune_updates is not None and not 1<=a.tune_updates<=200:p.error('tune-updates must be 1..200')
    def stop(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    result=monitor(read_json(a.config),a.force_tune,a.tune_updates)
    if result and result.get('status')=='CHECK_FAILED':sys.exit(1)
