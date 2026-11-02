"""Recover reflection member type edges from bounded descriptor constructors.

An edge is a registered class ID, not a claim about pointer/inline storage or
ownership. The raw descriptor mode is intentionally not interpreted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_IMM

ROOT = Path(__file__).resolve().parents[1]
BUILD = '3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda'


def analyze(executable, reflection):
    with executable.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != BUILD or reflection['exeSha256'] != BUILD:
        raise ValueError('Unknown build; descriptor anchors require a new analysis')
    pe = pefile.PE(str(executable), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
    bounds = {e.struct.BeginAddress: e.struct.EndAddress for e in pe.DIRECTORY_ENTRY_EXCEPTION}
    dis = Cs(CS_ARCH_X86, CS_MODE_64); dis.detail = True

    def instructions(rva):
        end = bounds.get(rva)
        if end is None or not 0 < end-rva <= 8192:
            return []
        return list(dis.disasm(pe.get_data(rva, end-rva), rva))

    def type_getter(rva):
        # Leaf getters lack unwind entries; recognize only this complete,
        # tiny current-build shape, including the return.
        raw = pe.get_data(rva, 10)
        if len(raw) == 10 and raw[:2] == b'\xc7\x01' and raw[6:] == b'\x48\x8b\xc1\xc3':
            return struct.unpack_from('<I', raw, 2)[0]
        return None

    def evidence(ins):
        return {'rva': hex(ins.address), 'bytes': ins.bytes.hex(), 'assembly': ins.mnemonic+' '+ins.op_str}

    classes = {}
    for cls in reflection['classes']:
        for text in cls.get('precedingCalls', []):
            rva = int(text, 16); class_id = type_getter(rva)
            if class_id is not None:
                classes.setdefault(class_id, []).append({'name': cls['name'], 'getterRva': hex(rva)})

    edges = []
    for cls in reflection['classes']:
        for member in cls['properties']:
            text = member.get('descriptorHelperRva')
            if not text:
                continue
            visited = set(); found = []; modes = []; chain = []

            def visit(rva, depth=0):
                if rva in visited or depth > 2:
                    return
                visited.add(rva)
                for ins in instructions(rva):
                    if ins.mnemonic != 'call' or len(ins.operands) != 1 or ins.operands[0].type != X86_OP_IMM:
                        continue
                    target = ins.operands[0].imm
                    class_id = type_getter(target)
                    if class_id is not None:
                        found.append((class_id, target, evidence(ins)))
                    elif pe.get_data(target, 6) == b'\xb8\x01\x00\x00\x00\xc3':
                        modes.append({'rawConstant': 1, 'getterRva': hex(target), 'call': evidence(ins)})
                    else:
                        chain.append(evidence(ins)); visit(target, depth+1)

            visit(int(text, 16))
            unique = {x[0] for x in found}
            if len(unique) != 1:
                continue
            class_id, getter, call = found[0]
            edges.append({'owner': cls['name'], 'member': member['name'], 'offset': member['offset'],
                          'descriptorHelperRva': text, 'registeredTypeId': hex(class_id),
                          'matchingRegisteredClasses': classes.get(class_id, []), 'typeGetterRva': hex(getter),
                          'typeGetterInstructions': [evidence(i) for i in dis.disasm(pe.get_data(getter, 10), getter)],
                          'typeGetterCall': call, 'constructorCalls': chain, 'descriptorModes': modes,
                          'storageRepresentationVerified': False, 'playerOwnershipVerified': False})
    pe.close()
    return {'schema': 'tm2020_reflected_member_types_v1', 'exeSha256': digest, 'edges': edges,
            'edgeCount': len(edges), 'classIdsMatched': len(classes),
            'note': 'Descriptor class IDs are static registration evidence. Raw mode 1 is not interpreted as a pointer. Neither inline layout, indirection, lifetime nor authoritative physics ownership follows from a type edge.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, default=Path('D:/SteamLibrary/steamapps/common/Trackmania/Trackmania.exe'))
    parser.add_argument('--output', type=Path, default=ROOT/'local/recon/reflected-member-types.json')
    args = parser.parse_args()
    reflection = json.loads((ROOT/'local/recon/reflection-current-build.json').read_text())
    result = analyze(args.exe, reflection)
    state = [e for e in result['edges'] if e['owner'] == 'CSceneVehicleVis' and e['member'] == 'AsyncState']
    if len(state) != 1 or state[0]['registeredTypeId'] != '0xa00c000' or not any(c['name'] == 'CSceneVehicleVisState' for c in state[0]['matchingRegisteredClasses']):
        raise ValueError('AsyncState type edge regression')
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print('REFLECTED_MEMBER_TYPES edges', result['edgeCount'], 'class_ids', result['classIdsMatched'],
          'AsyncState=CSceneVehicleVisState', 'storage_and_owner_unverified=true')
