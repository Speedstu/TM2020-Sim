"""Watchdog-protected Linux analog controller; policy inference remains in the DLL."""
import math
import fcntl
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

ROOT=Path(__file__).resolve().parents[1]


class AnalogGamepad:
    def __init__(self,steering_deadzone=0.,steering_bin_bias=0.):
        if not 0<=steering_deadzone<.5:raise ValueError('Invalid steering deadzone')
        if not 0<=steering_bin_bias<=1/127:raise ValueError('Invalid steering quantization bias')
        self.child=None;self.steering_deadzone=steering_deadzone;self.steering_bin_bias=steering_bin_bias
    def __enter__(self):
        self.child=subprocess.Popen([ROOT/'native/build-linux/tm2020_analog_gamepad'],stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        ready=queue.Queue()
        threading.Thread(target=lambda:ready.put(self.child.stdout.readline()),daemon=True).start()
        try:
            line=ready.get(timeout=5)
            if not line.startswith('TM2020_GAMEPAD_READY '):
                self.child.wait(timeout=2)
                raise RuntimeError('Analog gamepad did not initialize: '+self.child.stderr.read().strip())
            self.sysname=line.split()[1]
            deadline=time.monotonic()+5
            while not list((Path('/sys/devices/virtual/input')/self.sysname).glob('event*')):
                if time.monotonic()>deadline:raise TimeoutError('Analog event device did not appear')
                time.sleep(.05)
            # Allow udev, Steam and Proton to discover the new controller.
            time.sleep(1.)
            return self
        except BaseException:
            self.__exit__(None,None,None);raise
    def apply(self,controls):
        gas,brake,steer=controls
        if gas not in (0.,1.) or brake not in (0.,1.) or not math.isfinite(steer) or abs(steer)>1.:
            raise ValueError('Invalid analog controls')
        steer=compensate(steer,self.steering_deadzone,self.steering_bin_bias)
        self.child.stdin.write(f'TM2020_GAMEPAD_V1 {gas:.0f} {brake:.0f} {steer:.17g}\n');self.child.stdin.flush()
    def release(self):
        try:
            self.child.stdin.write('TM2020_GAMEPAD_RELEASE_V1\n');self.child.stdin.flush()
        except (BrokenPipeError,ValueError,OSError):pass
    def button(self,code,down):
        if not 0x130<=code<=0x13e or down not in (0,1):raise ValueError('Invalid gamepad button')
        self.child.stdin.write(f'TM2020_GAMEPAD_BUTTON_V1 {code} {down}\n');self.child.stdin.flush()
    def __exit__(self,*args):
        if self.child is None:return
        self.release()
        try:self.child.stdin.close()
        except BrokenPipeError:pass
        try:self.child.wait(timeout=2)
        except subprocess.TimeoutExpired:self.child.terminate();self.child.wait(timeout=2)
        self.child.stdout.close();self.child.stderr.close()


def shared_directory():
    path=Path('/run/user')/str(os.getuid())/'tm2020-analog-controller'
    path.mkdir(mode=0o700,exist_ok=True)
    if path.is_symlink() or path.stat().st_uid!=os.getuid() or path.stat().st_mode&0o077:
        raise RuntimeError('Controller directory must be private and owned by this user')
    return path


def compensate(steer,deadzone,bin_bias=0.):
    # Keep each requested i8 value inside its quantization bin, avoiding a
    # one-unit loss from the uinput -> XInput -> game integer conversion.
    return math.copysign(deadzone+(1.-deadzone)*min(1.,abs(steer)+bin_bias),steer) if steer else 0.


class PersistentAnalogGamepad:
    """Keep a single device connected between map selection, resets and SDK runs."""
    def __init__(self,steering_deadzone=0.,steering_bin_bias=0.):
        if not 0<=steering_deadzone<.5:raise ValueError('Invalid steering deadzone')
        if not 0<=steering_bin_bias<=1/127:raise ValueError('Invalid steering quantization bias')
        self.steering_deadzone=steering_deadzone;self.steering_bin_bias=steering_bin_bias
    def __enter__(self):
        self.fd=None;self.lock=None
        try:
            root=shared_directory();state=json.loads((root/'ready.json').read_text())
            os.kill(int(state['pid']),0)
            if not (Path('/sys/devices/virtual/input')/state['sysname']).is_dir():raise RuntimeError('Persistent controller is absent')
            self.lock=(root/'client.lock').open('a');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.fd=os.open(root/'control.fifo',os.O_WRONLY|os.O_NONBLOCK|os.O_CLOEXEC|os.O_NOFOLLOW)
            self.sysname=state['sysname'];self.release();return self
        except BaseException:
            self.__exit__(None,None,None);raise
    def send(self,command):
        data=command.encode('ascii')
        if os.write(self.fd,data)!=len(data):raise RuntimeError('Incomplete controller command')
    def apply(self,controls):
        gas,brake,steer=controls
        if gas not in (0.,1.) or brake not in (0.,1.) or not math.isfinite(steer) or abs(steer)>1.:raise ValueError('Invalid analog controls')
        steer=compensate(steer,self.steering_deadzone,self.steering_bin_bias)
        self.send(f'TM2020_GAMEPAD_V1 {gas:.0f} {brake:.0f} {steer:.17g}\n')
    def button(self,code,down):
        if not 0x130<=code<=0x13e or down not in (0,1):raise ValueError('Invalid gamepad button')
        self.send(f'TM2020_GAMEPAD_BUTTON_V1 {code} {down}\n')
    def release(self):
        if self.fd is not None:self.send('TM2020_GAMEPAD_RELEASE_V1\n')
    def __exit__(self,*args):
        if self.fd is not None:
            try:self.release()
            except (OSError,ValueError):pass
            os.close(self.fd);self.fd=None
        if self.lock is not None:self.lock.close();self.lock=None
