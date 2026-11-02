"""Small XTest helper, restricted to the foreground Trackmania window."""
import argparse
import ctypes as C
import json
import subprocess
import time
from pathlib import Path

def is_trackmania_window(window):
    if window.get('title')!='Trackmania' or not isinstance(window.get('pid'),int):return False
    try:
        executable=(Path('/proc')/str(window['pid'])/'cmdline').read_bytes().split(b'\0')[0]
        return executable.decode(errors='replace').replace('\\','/').rsplit('/',1)[-1].lower()=='trackmania.exe'
    except OSError:return False

def focus_trackmania():
    from proton_sdk import running_game
    pid,_=running_game()
    windows=json.loads(subprocess.check_output(['hyprctl','clients','-j']))
    matches=[w for w in windows if w.get('pid')==pid and is_trackmania_window(w)]
    if len(matches)!=1:raise RuntimeError('Expected one verified Trackmania window')
    address=matches[0]['address']
    subprocess.run(['hyprctl','dispatch','focuswindow','address:'+address],check=True,stdout=subprocess.DEVNULL)
    time.sleep(.2)
    active=json.loads(subprocess.check_output(['hyprctl','activewindow','-j']))
    if active.get('address')!=address or not is_trackmania_window(active):raise RuntimeError('Game focus refused')
    return active

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--click',type=int,nargs=2);group.add_argument('--key',choices=['Escape','Return','BackSpace','Delete','R'])
    args=parser.parse_args()
    window=json.loads(subprocess.check_output(['hyprctl','activewindow','-j'],text=True))
    if not is_trackmania_window(window):raise RuntimeError('Verified Trackmania process is not foreground')
    if args.key:
        # Compositor-delivered keyboard events also reach Wine raw-input paths.
        # This helper accepts only menu/reset keys, never driving controls.
        result=subprocess.run(['hyprctl','dispatch','sendshortcut',','+args.key+',address:'+window['address']],
                              check=True,capture_output=True,text=True)
        if result.stdout.strip()!='ok':raise RuntimeError('Compositor refused the menu shortcut')
        return
    x=C.CDLL('libX11.so.6');xt=C.CDLL('libXtst.so.6');x.XOpenDisplay.restype=C.c_void_p
    display=x.XOpenDisplay(None)
    if not display:raise RuntimeError('No XWayland display')
    x.XFlush.argtypes=[C.c_void_p];x.XCloseDisplay.argtypes=[C.c_void_p]
    try:
        if args.click:
            px,py=args.click
            if not 0<=px<window['size'][0] or not 0<=py<window['size'][1]:raise ValueError('Click outside game')
            xt.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
            # Hyprland uses logical coordinates; XWayland may use scaled pixels.
            subprocess.run(['hyprctl','dispatch','movecursor',f"{px+window['at'][0]} {py+window['at'][1]}"],
                           check=True,stdout=subprocess.DEVNULL)
            x.XFlush(display);time.sleep(.15)
            xt.XTestFakeButtonEvent(display,1,1,0);x.XFlush(display);time.sleep(.05)
            xt.XTestFakeButtonEvent(display,1,0,0)
        else:
            x.XStringToKeysym.argtypes=[C.c_char_p];x.XStringToKeysym.restype=C.c_ulong
            x.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong];x.XKeysymToKeycode.restype=C.c_uint
            xt.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
            key=x.XKeysymToKeycode(display,x.XStringToKeysym(args.key.encode()))
            xt.XTestFakeKeyEvent(display,key,1,0);x.XFlush(display);time.sleep(.05)
            xt.XTestFakeKeyEvent(display,key,0,0)
        x.XFlush(display)
    finally:x.XCloseDisplay(display)

if __name__=='__main__':main()
