#!/usr/bin/env python3
"""TrackStat — selectable, read-only curses dashboard for all Trackmania PPO runs.

Controls: S select run; Up/Down / Enter; A active run; Q or Ctrl+C closes.
No signals are sent to the selected training processes.
"""
from __future__ import annotations
import argparse
import curses
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import discover_runs,resolve_run,load_stats,fmt_time,fmt_num

STOP=False

def stop(*args):
    global STOP
    STOP=True


def cpu_temp():
    for f in Path('/sys/class/hwmon').glob('hwmon*/name'):
        try:
            if f.read_text().strip()=='k10temp':
                return float((f.parent/'temp1_input').read_text().strip())/1000
        except OSError:
            pass
    return None


def gpu():
    try:
        result=subprocess.run(
            ['/usr/bin/nvidia-smi','--query-gpu=utilization.gpu,temperature.gpu,memory.used',
             '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=2)
        a=result.stdout.strip().split(',')
        return [int(float(x.strip())) for x in a[:3]] if len(a)>=3 else None
    except (ValueError,OSError,subprocess.TimeoutExpired):
        return None


def _delta(ms):
    if ms is None:
        return '—'
    try:
        v=int(ms)
        return f'{v:+d} ms' if v else '±0 ms'
    except (TypeError,ValueError):
        return '—'


def rows(run=None,include_hardware=True):
    s=load_stats(run)
    g=gpu() if include_hardware else None
    t=cpu_temp() if include_hardware else None
    if s.get('kind','').startswith('pursuit'):
        root=s.get('kind')=='pursuit-group'
        maps=', '.join(f"{int(n):02}" for n in (s.get('activeMapIndices') or []) if n is not None)
        display=[
            ('SESSION',s['run']),
            ('STATUS',str(s['state']).upper()),
            ('METHOD','STAGED HYBRID · TOP 1 TARGET'),
            ('CURRENT MAPS',maps or '—'),
            ('MAPS ATTEMPTED',f"{s.get('mapsDone',0)} / {s.get('mapsTotal',0)}"),
            ('MAPS QUEUED',str(s.get('mapsQueued','—')) if s.get('mapsQueued') is not None else '—'),
            ('SIM TOP 10',f"{s.get('mapsTop10',0)} / {s.get('mapsTotal',0)}"),
            ('SIM TOP 1',f"{s.get('mapsTop1',0)} / {s.get('mapsTotal',0)}"),
            ('SIM GOALS HIT',f"{s.get('mapsPassed',0)} / {s.get('mapsTotal',0)}"),
            ('PARALLEL MAPS',f"{s.get('activeMapCount',0)} / {s.get('parallelLimit') or '—'}"),
            ('WORKERS / MAP',str(s.get('workersPerMap') or '—')),
            ('TOTAL PHYSICS SPS',fmt_num(s.get('nativeSpsAggregate')) if root else '—'),
            ('MAP FOCUS',str(s.get('mapName','—'))),
            ('STAGE',str(s.get('stage','—'))),
            ('GENERATION',f"{s.get('generation') if s.get('generation') is not None else '—'} / {s.get('generationMax') or '—'}"),
            ('PLATEAU COUNTER',str(s.get('staleGenerations') if s.get('staleGenerations') is not None else '—')),
            ('MAP PHYSICS SPS',fmt_num(s.get('nativeStepsPerSecond'))),
            ('GENERATION SPS',fmt_num(s.get('generationStepsPerSecond'))),
            ('TICKS / GENERATION',fmt_num(s.get('simulatedTicks'))),
            ('CANDIDATE EVAL/S',f"{s['evalsPerSec']:.1f}" if s.get('evalsPerSec') is not None else '—'),
            ('BEST SIM LAP',fmt_time(s.get('bestMs'))),
            ('WORLD BEST',fmt_time(s.get('worldBestMs'))),
            ('TOP 1 GOAL',fmt_time(s.get('targetMs'))),
            ('GAP TO GOAL',_delta(s.get('deltaMs'))),
            ('FINISHES',f"{s.get('finishes') if s.get('finishes') is not None else '—'} / {s.get('trials') or '—'}"),
            ('ON TARGET',f"{s.get('targetFinishes') if s.get('targetFinishes') is not None else '—'} / {s.get('trials') or '—'}"),
        ]
        for item in s.get('activeDetails') or []:
            display.append((f"MAP {int(item['mapIndex'] or 0):02} ACTIVE",
                            f"gen {item.get('generation','—')} · "
                            f"{fmt_num(item.get('nativeStepsPerSecond'))} SPS · "
                            f"{fmt_time(item.get('bestMs'))}"))
        for name,key in [('NOMINAL HOLDOUT','nominal'),('PERTURBED HOLDOUT','perturbed')]:
            report=s.get(key) or {}
            if report:
                display.append((name,
                    f"{report.get('finishes','—')}/{report.get('count','—')} finishes · "
                    f"{report.get('targetFinishes','—')} on target"))
        if s.get('stopReason'):
            display.append(('STOP REASON',str(s['stopReason'])))
        display.append(('GAME VERIFIED','NO · simulator only'))
    elif s.get('kind','').startswith('campaign'):
        maps_total=s.get('mapsTotal') or 0
        candidates=s.get('population') or 16
        cases=s.get('developmentCases') or 4
        gen=s.get('generation')
        display=[
            ('SESSION',s['run']),
            ('STATE',str(s['state']).upper()),
            ('TRAINING','HYBRID · GENERATION SEARCH'),
            ('MAP',s.get('mapName','—')),
            ('GENERATION',f'{gen if gen is not None else "—"} / {s.get("generationMax") or "—"}'),
            ('NO IMPROVEMENT',f'{s.get("staleGenerations") or 0} generations'),
            ('POPULATION',f'{candidates} candidates × {cases} trials'),
            ('SIM EVAL/S',f'{s["evalsPerSec"]:.1f}' if s.get('evalsPerSec') is not None else '—'),
            ('GEN EVAL TIME',f'{s["genSeconds"]:.2f}s' if s.get('genSeconds') is not None else '—'),
            ('BEST SIM LAP',fmt_time(s.get('bestMs'))),
            ('MEAN SIM LAP',fmt_time(s.get('meanMs'))),
            ('TARGET',fmt_time(s.get('targetMs'))),
            ('GAP TO TARGET',_delta(s.get('deltaMs'))),
            ('FINISHES',f'{s.get("finishes") if s.get("finishes") is not None else "—"} / {s.get("trials") or "—"}'),
            ('TARGET HITS',f'{s.get("targetFinishes") if s.get("targetFinishes") is not None else "—"} / {s.get("trials") or "—"}'),
        ]
        if maps_total:
            display += [
                ('CAMPAIGN DONE',f'{s.get("mapsDone",0)} / {maps_total} maps'),
                ('SIM GOALS HIT',f'{s.get("mapsPassed",0)} / {maps_total} maps'),
                ('ROBUST GOALS',f'{s.get("mapsRobust",0)} / {maps_total} maps'),
            ]
        for name,key in [('NOMINAL HOLDOUT','nominal'),('PERTURBED HOLDOUT','perturbed')]:
            report=s.get(key) or {}
            if report:
                display.append((name,
                    f'{report.get("finishes","—")}/{report.get("count","—")} finish · '
                    f'{report.get("targetFinishes","—")} on target'))
        if s.get('stopReason'):
            display.append(('STOP REASON',s['stopReason']))
        display += [('RACE EVIDENCE','REFERENCE-ASSISTED SIMULATION'),
                    ('GAME VERIFIED','NO · not a live-game record')]
    else:
        display=[
            ('RUN',s['run']),
            ('STATE',str(s['state']).upper()),
            ('TRAINING','PPO'),
            ('UPDATES',fmt_num(s.get('update'))),
            ('TRANSITIONS',fmt_num(s.get('transitions'))),
            ('LIVE SPS' if s.get('live') else 'LAST SPS',fmt_num(s.get('sps'))),
            ('BEST SIM LAP',fmt_time(s.get('bestMs'))),
            ('MEAN SIM LAP',fmt_time(s.get('meanMs'))),
            ('FINISHES',f'{s.get("finishes") if s.get("finishes") is not None else "—"} / {s.get("trials") or "—"}'),
            ('PHASE',str(s.get('phase','—'))),
            ('GAME VERIFIED','YES' if s.get('realGame') else 'NO · simulator'),
        ]
    if include_hardware:
        display.extend([
            ('CURRENT CPU',f'{t:.1f} °C' if t is not None else '—'),
            ('CURRENT GPU',f'{g[0]}% · {g[1]} °C · {g[2]} MiB' if g else '—')
        ])
    display += [('LAST REPORT',str(s.get('lastUpdate','—')))]
    return display


def _put(win,y,x,message,style=0):
    h,w=win.getmaxyx()
    if 0<=y<h and 0<=x<w:
        try:
            win.addnstr(y,x,str(message),max(0,w-x-1),style)
        except (curses.error,UnicodeEncodeError):
            pass


def _key(stdscr):
    """Read normal curses keys plus CSI/SS3 arrows from terminal emulators."""
    c=stdscr.getch()
    if c!=27:
        return c
    # When curses does not recognize ESC [ B / ESC O B as KEY_DOWN,
    # distinguish the escape prefix from a standalone Escape key.
    stdscr.timeout(60)
    try:
        prefix=stdscr.getch()
        if prefix in (ord('['),ord('O')):
            direction=stdscr.getch()
            if direction==ord('A'):return curses.KEY_UP
            if direction==ord('B'):return curses.KEY_DOWN
            if direction==ord('C'):return curses.KEY_RIGHT
            if direction==ord('D'):return curses.KEY_LEFT
        return 27
    finally:
        stdscr.timeout(100)


def picker(stdscr,selected=None):
    """Full-screen searchable run picker; no writes to learner files."""
    query=''
    selected_idx=0
    runs=discover_runs()
    if selected:
        for i,r in enumerate(runs):
            if r['id']==selected:
                selected_idx=i
                break
    stdscr.timeout(100)
    last_refresh=time.monotonic()
    while not STOP:
        if time.monotonic()-last_refresh>3:
            current=runs[selected_idx]['id'] if runs and selected_idx<len(runs) else None
            runs=discover_runs()
            if current:
                selected_idx=next((i for i,r in enumerate(runs) if r['id']==current),selected_idx)
            last_refresh=time.monotonic()
        filtered=[r for r in runs if query.casefold() in r['id'].casefold()]
        selected_idx=max(0,min(selected_idx,len(filtered)-1))
        stdscr.erase()
        h,w=stdscr.getmaxyx()
        _put(stdscr,1,3,'TRACK / SELECT RUN',curses.A_BOLD|curses.color_pair(1))
        _put(stdscr,2,3,f'RUNS: {len(runs)}  ·  FILTER: {query or "all"}',curses.A_DIM)
        _put(stdscr,3,3,'Up/Down navigate   Enter select   Type to search   Backspace erase   Esc cancel',curses.A_DIM)
        body_y=5
        max_lines=max(1,h-body_y-3)
        first=max(0,selected_idx-max_lines+1)
        if selected_idx<first:first=selected_idx
        for i in range(first,min(len(filtered),first+max_lines)):
            run=filtered[i];y=body_y+i-first
            marked=(i==selected_idx)
            label=f"{run['state']:<8} {run['id']}"
            _put(stdscr,y,4,('▶ ' if marked else '  ')+label,
                 (curses.A_REVERSE|curses.A_BOLD) if marked else
                 (curses.color_pair(2) if run['live'] else curses.A_DIM))
        if not filtered:
            _put(stdscr,body_y,5,'No matching run. Clear the filter to see all runs.',curses.color_pair(3))
        _put(stdscr,h-2,3,'Ctrl+C / Q: exit  ·  Training runs are NEVER stopped by trackstat',curses.color_pair(3))
        stdscr.refresh()
        c=_key(stdscr)
        if c==-1:continue
        if c in (27,):return None
        if c in (ord('q'),ord('Q')) and not query:return None
        if c==curses.KEY_UP or (c==ord('k') and not query):
            selected_idx=max(0,selected_idx-1)
        elif c==curses.KEY_DOWN or (c==ord('j') and not query):
            selected_idx=min(max(0,len(filtered)-1),selected_idx+1)
        elif c in (10,13,curses.KEY_ENTER):
            if filtered:return filtered[selected_idx]['id']
        elif c in (curses.KEY_BACKSPACE,127,8):
            query=query[:-1]
            selected_idx=0
        elif c in (ord('/'),):
            query=''
            selected_idx=0
        elif 32<=c<127:
            query+=chr(c)
            selected_idx=0
    return None


def screen(stdscr,initial=None,choose=False):
    try:curses.curs_set(0)
    except curses.error:pass
    stdscr.nodelay(True)
    stdscr.timeout(100)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1,curses.COLOR_CYAN,-1)
    curses.init_pair(2,curses.COLOR_GREEN,-1)
    curses.init_pair(3,curses.COLOR_YELLOW,-1)
    current=initial
    if choose:
        candidate=picker(stdscr,current)
        if candidate:current=candidate
    last=0
    values=[]
    scroll=0
    while not STOP:
        try:
            c=_key(stdscr)
            if c in (ord('q'),ord('Q'),27):break
            if c in (ord('s'),ord('S')):
                candidate=picker(stdscr,current)
                if candidate:current=candidate
                last=0
                continue
            if c in (ord('a'),ord('A')):
                current=None  # auto (always follow newly active learner)
                last=0
            if c==9:  # Tab cycles live campaign sessions, not each child map
                sessions=[r for r in discover_runs() if r['live'] and r['kind'] in ('pursuit-group','pursuit-map','campaign-group','ppo')]
                if sessions:
                    names=[r['id'] for r in sessions]
                    pos=names.index(current) if current in names else -1
                    current=names[(pos+1)%len(names)]
                last=0
            if c in (ord('r'),ord('R')):last=0
            if c in (ord('j'),curses.KEY_DOWN,curses.KEY_NPAGE):
                scroll+=8 if c==curses.KEY_NPAGE else 1
                last=0
            if c in (ord('k'),curses.KEY_UP,curses.KEY_PPAGE):
                scroll-=8 if c==curses.KEY_PPAGE else 1
                last=0
            if c in (ord('s'),ord('S'),ord('a'),ord('A'),9):
                scroll=0
            if time.monotonic()-last<.65:continue
            last=time.monotonic()
            values=rows(current)
            stdscr.erase()
            h,w=stdscr.getmaxyx()
            _put(stdscr,1,3,'TRACK / STATS',curses.A_BOLD|curses.color_pair(1))
            _put(stdscr,2,3,'STAGED RECORDS + HYBRID + PPO  /  READ ONLY',curses.A_DIM)
            _put(stdscr,3,3,'AUTO · MOST RECENT ACTIVE RUN' if current is None else
                 'PINNED · SELECTED RUN',curses.color_pair(2))
            # Compact two-column dashboard on standard 80x24/120x24 terminals.
            # Keep all critical campaign metrics visible without scrolling.
            split = w >= 90 and len(values) > max(1,h-9)
            column_items=(len(values)+1)//2 if split else len(values)
            visible=max(1,h-8)
            scroll=max(0,min(scroll,max(0,column_items-visible)))
            for i,(key,value) in enumerate(values):
                second=split and i>=column_items
                y=5+(i-column_items if second else i)-scroll
                if y<5:continue
                if y>=h-3:continue
                left=(w//2+1) if second else 4
                label_x=left
                value_x=left+18
                room=(w-2-value_x) if second or not split else (w//2-value_x-1)
                if room<=0:continue
                _put(stdscr,y,label_x,key,curses.A_DIM)
                col=curses.color_pair(2) if key in ('LIVE SPS','SIM EVAL/S','BEST SIM LAP','TARGET HITS') else 0
                value=str(value)
                if len(value)>room:
                    value=value[:max(1,room-1)]+'…'
                _put(stdscr,y,value_x,value,curses.A_BOLD|col)
            _put(stdscr,h-2,3,'S: select   TAB: cycle active   J/K: scroll   A: auto   Q / Ctrl+C: exit',curses.color_pair(3))
            stdscr.refresh()
        except KeyboardInterrupt:
            break


def main():
    p=argparse.ArgumentParser(description='Trackmania PPO live statistics with run selector')
    p.add_argument('--run','-r',type=str,help='Run name or training path, e.g. fall-campaign-world-records-0.57')
    p.add_argument('--map',type=int,metavar='N',help='Select map N in the current staged world-record campaign')
    p.add_argument('--select',action='store_true',help='Open the run picker immediately')
    p.add_argument('--list',action='store_true',help='Show all detected runs, newest active first')
    p.add_argument('--once',action='store_true',help='Print one snapshot and exit')
    p.add_argument('--json',action='store_true',help='Print one JSON snapshot and exit')
    a=p.parse_args()
    if a.list:
        for r in discover_runs():
            print(f"{r['state']:<9} {r['id']}")
        return
    if a.map is not None and a.run:
        p.error('use --map N OR --run PATH, not both')
    try:
        if a.map is not None:
            candidates=[r for r in discover_runs()
                        if r['kind']=='pursuit-map' and r['path'].name==f'{a.map:02d}']
            candidates.sort(key=lambda r:(not r['live'],-r['mtime']))
            if not candidates:
                p.error(f'map {a.map:02d} has no staged run; see --list')
            selected=candidates[0]
        else:
            selected=resolve_run(a.run)
    except ValueError as e:
        p.error(str(e))
    current=selected['id'] if (a.map is not None or a.run) and selected else None
    if a.json:
        print(json.dumps(load_stats(current),indent=2))
        return
    if a.once or not sys.stdout.isatty():
        for k,v in rows(current):
            print(f'{k:<18} {v}')
        return
    signal.signal(signal.SIGINT,stop)
    signal.signal(signal.SIGTERM,stop)
    curses.wrapper(lambda s:screen(s,current,choose=a.select))


if __name__=='__main__':
    try:
        main()
    except BrokenPipeError:
        # Clean pipes, e.g. trackstat --list | head, without a traceback.
        sys.exit(0)
