"""Verify exact constructed vehicle interval and static time-argument flow."""
import hashlib
import json
from pathlib import Path
from pe_unwind import PeCode
from reverse_physics import ROOT,SHA


def main():
    exe=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
    if hashlib.sha256(exe.read_bytes()).hexdigest()!=SHA:raise ValueError('Unknown build')
    c=PeCode(exe);roots=[0x12e9ea0,0x7bd0e0,0x803920,0x8025a0,0x8427d0]
    ins={i.address:i for r in roots for i in c.instructions(r)}
    expected={
        0x12e9ee0:('mov','r15d, edx'),
        0x12e9f28:('mov','dword ptr [rbp + 0x160], r15d'),
        0x12e9f2f:('mov','dword ptr [rbp + 0x164], 0xa'),
        0x12e9f39:('mov','dword ptr [rbp + 0x168], 0x3c23d70b'),
        0x12eb035:('movsd','xmm0, qword ptr [rbp + 0x160]'),
        0x12eb053:('call','0x7bd0e0'),
        0x7bd11a:('movsd','xmm0, qword ptr [rbx]'),
        0x7bd123:('mov','eax, dword ptr [rbx + 8]'),
        0x7bd133:('call','0x803920'),
        0x803d6f:('mov','r8, r12'),0x803d72:('call','0x8025a0'),
        0x80260d:('mov','eax, dword ptr [r14]'),
        0x802636:('movss','xmm9, dword ptr [r14 + 8]'),
        0x80263c:('imul','rsi, rax, 0xf4240'),
        0x80293d:('movaps','xmm2, xmm9'),0x802945:('call','0x7f81c0'),
        0x803ced:('movsd','xmm0, qword ptr [r14 + 0x25c]'),
        0x803cdc:('mov','eax, dword ptr [r14 + 0x264]'),
        0x802993:('lea','rax, [r12 + 0x100]'),0x8029df:('call','0x7f89d0'),
        0x84281e:('movaps','xmm10, xmm3'),0x84289e:('mov','ebx, dword ptr [rbp + 0xb0]'),
        0x8428a8:('mov','dword ptr [rsp + 0x44], ebx'),0x8428ac:('movss','dword ptr [rsp + 0x48], xmm10')}
    for address,assembly in expected.items():
        if address not in ins or (ins[address].mnemonic,ins[address].op_str)!=assembly:raise ValueError('Timing argument flow differs at '+hex(address))
    report={'schema':'tm2020_static_step_timing_evidence_v1','sha256':SHA,
        'vehicleStepIntegerMilliseconds':10,'vehicleIntervalBinary32Bits':'0x3c23d70b',
        'vehicleIntervalDecimal':0.010000000707805157,'literalPointZeroOneBinary32Bits':'0x3c23d70a',
        'callbackIntervalUsesFourthFloatArgument':True,'callbackTimestampUsesFifthIntegerArgument':True,
        'parallelWideTimestampMultiplier':1000000,'persistentDynaGravityOffset':604,
        'internalStackViewGravityOffset':256,'stackViewAndPersistentManagerLayoutsDiffer':True,
        'instructions':[{'rva':hex(a),'bytes':bytes(ins[a].bytes).hex(),'assembly':ins[a].mnemonic+' '+ins[a].op_str} for a in sorted(expected)],
        'liveInternalPhysicsClockAddressVerified':False,'completeMainStepQualified':False}
    (ROOT/'local/recon/step-timing-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS STATIC_STEP_TIMING interval_bits=0x3c23d70b integer_ms=10 gravity_persistent_offset=0x25c live_clock_unverified=true')


if __name__=='__main__':main()
