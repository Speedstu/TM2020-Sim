#!/usr/bin/env python3
"""Read-only public campaign download. No game, account writes or old monitor."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'local/training/fall-campaign-0.52'
SOURCE = 'https://trackmania.io/api/campaign/seasonal/157584'


def fetch(url, limit=64*1024*1024):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={
                'User-Agent': 'TM2020LocalResearch/0.52 (public campaign simulator)'}), timeout=45) as r:
                data = r.read(limit+1)
            if len(data)>limit: raise ValueError('Download exceeds size limit')
            return data
        except urllib.error.HTTPError as e:
            if attempt==3: raise
            time.sleep(max(20*(attempt+1),int(e.headers.get('Retry-After','0'))))
        except Exception:
            if attempt==3: raise
            time.sleep(3+attempt)


def save(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_bytes(data);tmp.replace(path)


def save_json(path, obj):
    save(path, (json.dumps(obj,indent=2)+'\n').encode())


def prepare(entry, index, out):
    d=out/f'{index:02d}';d.mkdir(parents=True,exist_ok=True)
    path=Path(entry['map'])
    if not path.exists(): save(path,fetch(entry['fileUrl']))
    url=f"https://trackmania.io/api/leaderboard/map/{entry['mapUid']}?length=10&offset=0"
    cached=d/'leaderboard.json'
    if cached.exists() and time.time()-cached.stat().st_mtime<3600:
        board=json.loads(cached.read_text());tops=board['tops']
    else:
        time.sleep(3)
        board=json.loads(fetch(url));tops=[{k:t[k] for k in ('position','time','url')} for t in board['tops']]
    if len(tops)<10: raise ValueError(f'{index}: fewer than ten leaderboard entries')
    board={'sourceUrl':url,'fetchedUtc':datetime.now(timezone.utc).isoformat(),'tops':tops}
    save_json(d/'leaderboard.json',board)
    ghost=d/'reference.Ghost.Gbx';ghost_url='https://trackmania.io'+tops[0]['url']
    expected=(d/'reference-source.json')
    if not ghost.exists() or not expected.exists() or json.loads(expected.read_text())['url']!=ghost_url:
        save(ghost,fetch(ghost_url));save_json(expected,{'url':ghost_url,'declaredMs':tops[0]['time']})
    result={'index':index,'name':entry['name'],'mapUid':entry['mapUid'],'map':str(path),
        'mapSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'fileUrl':entry['fileUrl'],
        'referenceGhost':str(ghost),'referenceSha256':hashlib.sha256(ghost.read_bytes()).hexdigest(),
        'referenceMs':tops[0]['time'],'targetExclusive':index==1,
        'targetMs':tops[0]['time']-1 if index==1 else tops[9]['time'],
        'targetRank':1 if index==1 else 10,'leaderboard':str(d/'leaderboard.json')}
    save_json(d/'map.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=OUT);a=p.parse_args()
    config=json.loads((ROOT/'config/training-monitor/fall2026.json').read_text())
    campaign=json.loads(fetch(SOURCE))
    if campaign['name'].replace(' ','')!='Fall2026' or len(campaign['playlist'])!=25:
        raise ValueError('Unexpected campaign')
    results=[];failures=[]
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending={pool.submit(prepare,m,i,a.output):i for i,m in enumerate(config['maps'],1)}
        for f in as_completed(pending):
            i=pending[f]
            try:
                r=f.result();results.append(r);print(json.dumps({k:r[k] for k in ('index','referenceMs','targetMs')}),flush=True)
            except Exception as e:
                failures.append({'index':i,'error':str(e)});print(json.dumps(failures[-1]),flush=True)
    save_json(a.output/'campaign.json',{'schema':'tm2020_campaign_sim_v1','source':SOURCE,
        'fetchedUtc':datetime.now(timezone.utc).isoformat(),'simulatorOnly':True,
        'maps':sorted(results,key=lambda m:m['index']),'failures':failures})
    if failures: raise SystemExit(1)


if __name__=='__main__':main()
