"""Independently qualify the physical ID/name table in the pinned game image."""
import hashlib
import json
from pathlib import Path
import re
import struct
from pe_unwind import PeCode
from reverse_physics import ROOT,SHA


def main():
    exe=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
    if hashlib.sha256(exe.read_bytes()).hexdigest()!=SHA:raise ValueError('Unknown material name build')
    c=PeCode(exe);base=c.pe.OPTIONAL_HEADER.ImageBase;names=[]
    for index in range(80):
        pointer=struct.unpack('<Q',c.pe.get_data(0x1f66bf0+index*8,8))[0]
        if not base<=pointer<base+c.pe.OPTIONAL_HEADER.SizeOfImage:raise ValueError('Invalid surface-name pointer')
        name=c.pe.get_string_at_rva(pointer-base).decode('ascii')
        if not re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,63}',name):raise ValueError('Unexpected surface identifier')
        names.append(name)
    header=ROOT/'native/include/tm2020/surface_materials.hpp'
    text=header.read_text();enum=re.findall(r'^    ([A-Za-z_0-9]+)=([0-9]+),$',text,re.M)
    strings=re.findall(r'^    "([A-Za-z_0-9]+)",$',text,re.M)
    if enum!=[(name,str(index)) for index,name in enumerate(names)] or strings!=names:raise ValueError('SDK surface names differ from executable')
    if names[0]!='Concrete' or names[16]!='Asphalt' or names[77]!='Plastic':raise ValueError('Surface index anchors changed')
    (ROOT/'local/recon/surface-material-names.json').write_text(json.dumps({'schema':'tm2020_physical_surface_names_v1','sha256':SHA,
        'pointerTableRva':'0x1f66bf0','count':80,'names':names,'sdkHeaderSha256':hashlib.sha256(header.read_bytes()).hexdigest(),
        'physicalIdsEqualPortableReplayDatasetIds':False,'conversionRule':'exact name lookup in export_native_dataset.py MATERIALS; absent names map to 255'},indent=2)+'\n')
    print('PASS PHYSICAL_SURFACE_NAMES entries=80 sdk_enum_exact=true distinct_from_portable_dataset=true')


if __name__=='__main__':main()
