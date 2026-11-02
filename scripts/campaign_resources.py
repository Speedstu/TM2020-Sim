"""Conservative admission of map searches against available host RAM."""
from pathlib import Path


def live_client_running(proc_root=Path('/proc')):
    for proc in Path(proc_root).iterdir():
        if not proc.name.isdigit():continue
        try:
            with (proc/'cmdline').open('rb') as stream:first=stream.read(4096).split(b'\0',1)[0]
            if first.replace(b'\\',b'/').rsplit(b'/',1)[-1].lower()==b'trackmania.exe':return True
        except OSError:pass
    return False


def available_memory_mb():
    fields=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    return int(fields['MemAvailable'].split()[0])/1024


def process_rss_mb(pid):
    try:
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith('VmRSS:'):return int(line.split()[1])/1024
    except (FileNotFoundError,ProcessLookupError):pass
    return 0.


def can_admit(available_mb,reserve_mb,reservation_mb,running_rss_mb):
    # A starting worker has not allocated its world/clones yet. Reserve that
    # upcoming memory as well, rather than launching several on the same RAM.
    pending=sum(max(0.,reservation_mb-rss) for rss in running_rss_mb)
    return available_mb-reserve_mb-pending>=reservation_mb
