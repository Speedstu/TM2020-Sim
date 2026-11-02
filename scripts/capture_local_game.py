#!/usr/bin/env python3
"""Capture only the foreground Trackmania window after focus has settled."""
import argparse
import json
from pathlib import Path
import subprocess
import time


def capture(path,focus=False):
    def read():return json.loads(subprocess.check_output(['hyprctl','activewindow','-j']))
    clients=json.loads(subprocess.check_output(['hyprctl','clients','-j']))
    matches=[c for c in clients if c.get('class')=='steam_app_2225070' and c.get('title')=='Trackmania']
    if len(matches)!=1:raise RuntimeError('Expected exactly one game window')
    game=matches[0]
    if focus:
        subprocess.run(['hyprctl','dispatch','focuswindow','address:'+game['address']],check=True,stdout=subprocess.DEVNULL)
        x,y=game['at'];w,h=game['size']
        subprocess.run(['hyprctl','dispatch','movecursor',f'{x+w//2} {y+h//2}'],check=True,stdout=subprocess.DEVNULL)
        time.sleep(.8)
    before=read()
    if any(before.get(k)!=game.get(k) for k in ('address','pid','class','title','at','size')):
        raise RuntimeError('Game is not the stable foreground window')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    x,y=before['at'];w,h=before['size']
    subprocess.run(['grim','-g',f'{x},{y} {w}x{h}',str(path)],check=True)
    after=read()
    if any(after.get(k)!=before.get(k) for k in ('address','pid','class','title','at','size')):
        path.unlink(missing_ok=True);raise RuntimeError('Window changed during capture; image discarded')
    return path


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--focus',action='store_true')
    a=p.parse_args();capture(a.output,a.focus)
