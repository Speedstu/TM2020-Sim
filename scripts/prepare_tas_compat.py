"""Create a separate, pinned TAS checkout compatible with this WSL CPU/Rust."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
REV = '036a65ba6aaef87b4579b8ee5a770729341dc572'
PATCH = ROOT / 'integrations/tas-compat-0.35/compat.patch'
TRACE_PATCH = ROOT / 'integrations/tas-compat-0.35/validator-trace.patch'

def git(*args, cwd=None):
    result = subprocess.run(['git', *map(str, args)], cwd=cwd,
        capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--upstream', type=Path, default=ROOT / 'cache/trackmania-tas-upstream-036a65b')
    p.add_argument('--output', type=Path, default=ROOT / 'cache/trackmania-tas-compat-0.35')
    a = p.parse_args()
    upstream = a.upstream.resolve(strict=True)
    output = a.output.resolve()
    if output.exists():
        raise ValueError('Compatibility checkout already exists; never overwrite it')
    if git('rev-parse', 'HEAD', cwd=upstream) != REV or git('status', '--porcelain', cwd=upstream):
        raise ValueError('TAS upstream is not the expected clean revision')
    git('apply', '--check', PATCH, cwd=upstream)
    git('apply', '--check', TRACE_PATCH, cwd=upstream)
    git('clone', '--local', '--no-checkout', upstream, output, cwd=ROOT)
    git('checkout', '--detach', REV, cwd=output)
    git('apply', PATCH, cwd=output)
    git('apply', TRACE_PATCH, cwd=output)
    changed = set(git('diff', '--name-only', cwd=output).splitlines())
    if changed != {'tools/.cargo/config.toml', 'tools/search/forkshim/src/lib.rs', 'tools/fk/fk/src/cmd/trace.rs'}:
        raise RuntimeError('Unexpected TAS compatibility patch footprint')
    print('PASS TAS_COMPAT', output, REV)

if __name__ == '__main__':
    main()
