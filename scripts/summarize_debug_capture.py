"""Audit owned-process phase capture only; retained real-game attempt failed."""
import hashlib
import json
from reverse_physics import ROOT,SHA


def main():
    cache=(ROOT/'native/build/CMakeCache.txt').read_text()
    if 'TM2020_ENABLE_EXPERIMENTAL_GAME_DEBUG_CAPTURE:BOOL=OFF' not in cache:
        raise ValueError('Unqualified live debugger must be disabled for this release qualification')
    normal=ROOT/'native/build/debugger-owned.jsonl';aborted=ROOT/'native/build/debugger-owned-abort.jsonl'
    rows=[json.loads(line) for line in normal.read_text().splitlines()]
    pairs=[r for r in rows if 'pair' in r]
    if len(pairs)!=20 or any(not r['owned_fixture'] for r in rows):raise ValueError('Owned phase fixture identity/count mismatch')
    for r in pairs:
        if abs((r['forces'][0]-r['forces_before'][0])-r['dt'])>3e-8 or r['forces'][1]-r['forces_before'][1]!=1:
            raise ValueError('Owned before/after force mismatch')
        if r['rigid']!=r['rigid_before']:raise ValueError('Owned rigid fixture unexpectedly changed')
    failure_rows=[json.loads(line) for line in aborted.read_text().splitlines()]
    if not failure_rows or any('pair' in r or not r['owned_fixture'] for r in failure_rows):raise ValueError('Deliberate abort fixture trace invalid')
    log=(ROOT/'native/build/Testing/Temporary/LastTest.log').read_text()
    if 'deliberate_abort=1' not in log or 'restore_failures=0' not in log:raise ValueError('Debugger abort cleanup test evidence missing')
    failed=[]
    for p in sorted((ROOT/'local/recon').glob('force-phase-7620-*.log')):
        text=p.read_text(encoding='utf-8-sig');failed.append({'path':str(p.relative_to(ROOT)),'text':text.strip(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    report={'schema':'tm2020_debugger_capture_qualification_v1','sha256':SHA,'ownedEntryReturnPairs':20,
        'ownedBeforeAfterVerified':True,'ownedDeliberateAbortCleanupValidated':True,'ownedChildNormalExitCheckedByNativeFixture':True,
        'liveGamePhaseCaptureValidated':False,'liveGameInternalTickValidated':False,'defaultLiveDebuggerEnabled':False,
        'retainedFailedLiveAttempts':failed,'priorGameProcessExitObserved':True,
        'exitCauseEstablished':False,'subsequentGameRelaunchObserved':True,
        'limits':['Owned fixture is not game physics','Former first-argument force-array assumption rejected',
            'Real-game accumulator at manager+0xa0 remains an unqualified capture path','Do not enable live debugger capture as a production data source']}
    (ROOT/'local/recon/debug-capture-qualification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS OWNED_DEBUGGER_AUDIT pairs=20 abort_cleanup=true live_game_capture=false')


if __name__=='__main__':main()
