#!/usr/bin/env python3
"""Launch the installed, unmodified client in an isolated network namespace.

Uses a private copy of the existing Wine prefix and cached launcher login.
Does not change Steam's network settings or the original game prefix. Login
requirements are left to the official launcher; this never bypasses them.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
from run_fast_ppo import ROOT, steam_packs


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    game=steam_packs().parent
    steam=game.parents[2]
    original=steam/'steamapps/compatdata/2225070/pfx'
    prefix=out/'pfx'
    subprocess.run(['cp','-a','--reflink=auto',str(original),str(prefix)],check=True)
    # Work with the installed game's current Proton selection, recorded here.
    wine=steam/'steamapps/common/Proton 10.0/files/bin/wine'
    if not wine.is_file():raise RuntimeError('Installed Proton 10.0 not found')
    env={'WINEPREFIX':str(prefix),'WINEDEBUG':'-all','WINEDLLOVERRIDES':'winemenubuilder.exe=d',
         'SteamAppId':'2225070','SteamGameId':'2225070','WINEFSYNC':'1',
         'PATH':str(wine.parent)+':/usr/bin:/bin'}
    for k in ('DISPLAY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'):
        if k in os.environ:env[k]=os.environ[k]
    # Flatpak supplies its own Xauthority and GPU library paths.
    command=['flatpak','run','--unshare=network','--filesystem='+str(ROOT),
             '--command=env','com.valvesoftware.Steam',*[k+'='+v for k,v in env.items()],
             str(wine),str(game/'Trackmania.exe')]
    report={'command':command,'originalPrefixUnchanged':True,'privatePrefix':str(prefix),
            'networkIsolationRequested':True,'networkIsolationVerified':False,
            'gameStarted':False,'runtimeAttached':False}
    (out/'launch.json').write_text(json.dumps(report,indent=2)+'\n')
    with (out/'client.log').open('w') as log:
        child=subprocess.Popen(command,cwd=game,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    report['launcherPid']=child.pid
    (out/'launch.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'launcherPid':child.pid,'output':str(out)}),flush=True)


if __name__=='__main__':main()
