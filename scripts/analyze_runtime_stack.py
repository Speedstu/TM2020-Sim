"""Reproduce the failed injected worker's stack mismatch from PE/instructions."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import capstone
import pefile

ROOT = Path(__file__).resolve().parents[1]
game = Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
old = ROOT / 'local/runtime/tm2020-runtime-d14b38a0aba5b071.dll'
expected = '3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda'
if hashlib.sha256(game.read_bytes()).hexdigest() != expected:
    raise ValueError('Game build is not pinned to this analysis')
game_pe, old_pe = pefile.PE(game), pefile.PE(old)
symbols = subprocess.run(['nm', '-C', str(old)], capture_output=True, text=True, check=True).stdout
symbol = next(line for line in symbols.splitlines() if '::getSha(' in line and '[clone' not in line)
address = int(symbol.split()[0], 16)
rva = address - old_pe.OPTIONAL_HEADER.ImageBase
decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
instructions = list(decoder.disasm(old_pe.get_data(rva, 72), rva))
allocation = next(int(match.group(1), 16) for i in instructions
                  if i.mnemonic == 'mov' and (match := re.fullmatch(r'eax, 0x([a-f0-9]+)', i.op_str)))
if not any(i.mnemonic == 'sub' and i.op_str == 'rsp, rax' for i in instructions):
    raise ValueError('Expected checked stack allocation prologue not present')
fault = list(decoder.disasm(game_pe.get_data(0x11da01, 2), 0x11da01))[0]
if fault.mnemonic != 'ud2':
    raise ValueError('Game fault instruction changed')
report = {
    'schema': 'tm2020_injected_worker_stack_analysis_v1', 'game_sha256': expected,
    'failed_sdk_sha256': hashlib.sha256(old.read_bytes()).hexdigest(),
    'game_default_thread_stack_reserve_bytes': game_pe.OPTIONAL_HEADER.SizeOfStackReserve,
    'failed_sha_function_rva': hex(rva), 'failed_sha_function_stack_allocation_bytes': allocation,
    'allocation_alone_exceeds_game_thread_reserve': allocation > game_pe.OPTIONAL_HEADER.SizeOfStackReserve,
    'failed_sha_prologue': [{'rva': hex(i.address), 'bytes': i.bytes.hex(),
                            'assembly': i.mnemonic + ' ' + i.op_str} for i in instructions],
    'observed_game_fault_rva': '0x11da01', 'observed_game_fault_instruction': 'ud2',
    'game_diagnostic_string': game_pe.get_data(0x1b56fe0, 100).split(b'\0')[0].decode(),
    'causal_limit': 'Original exception stack dump is unavailable. The SDK stack mismatch is statically proven; its relationship to the game fatal diagnostic is inferred.',
    'repair': 'Heap-backed SHA chunk buffer; explicit 8 MiB worker reserve; native 256 KiB worker regression test.',
}
destination = ROOT / 'local/recon/injected-stack-analysis.json'
destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print('STATIC_STACK_MISMATCH', allocation, '>', game_pe.OPTIONAL_HEADER.SizeOfStackReserve)
