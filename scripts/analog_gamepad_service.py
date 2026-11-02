"""One persistent controller, owned by the local user; no training monitoring."""
import fcntl
import json
import os
import select
from analog_gamepad import AnalogGamepad,shared_directory


def main():
    root=shared_directory();lock=(root/'service.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    fifo=root/'control.fifo';ready=root/'ready.json';fd=None
    try:
        ready.unlink(missing_ok=True);fifo.unlink(missing_ok=True);os.mkfifo(fifo,0o600)
        fd=os.open(fifo,os.O_RDWR|os.O_NONBLOCK|os.O_CLOEXEC)
        with AnalogGamepad() as pad:
            ready.write_text(json.dumps({'pid':os.getpid(),'sysname':pad.sysname})+'\n')
            print('CONTROLLER_READY '+pad.sysname,flush=True)
            while pad.child.poll() is None:
                if select.select([fd],[],[],.25)[0]:
                    data=os.read(fd,4096)
                    pad.child.stdin.write(data.decode('ascii'));pad.child.stdin.flush()
            raise RuntimeError('Native controller stopped')
    finally:
        ready.unlink(missing_ok=True)
        if fd is not None:os.close(fd)
        fifo.unlink(missing_ok=True);lock.close()

if __name__=='__main__':main()
