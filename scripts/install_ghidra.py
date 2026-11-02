"""Install pinned official Ghidra/JDK archives into this project's tools only."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
PACKAGES=[
    {'name':'Ghidra','version':'12.1.4','filename':'ghidra_12.1.4_PUBLIC_20260921.zip',
     'url':'https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/ghidra_12.1.4_PUBLIC_20260921.zip',
     'sha256':'ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db'},
    {'name':'Temurin JDK','version':'21.0.12.1+1','filename':'OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip',
     'url':'https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip',
     'sha256':'f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e'},
]


def install(package):
    cache=ROOT/'cache/re-tools';cache.mkdir(parents=True,exist_ok=True)
    archive=cache/package['filename'];destination=ROOT/'tools';destination.mkdir(exist_ok=True)
    if not archive.exists():
        temporary=archive.with_suffix('.partial')
        request=urllib.request.Request(package['url'],headers={'User-Agent':'TrackmaniaPhysicsResearch'})
        with urllib.request.urlopen(request,timeout=120) as response,temporary.open('wb') as output:
            shutil.copyfileobj(response,output,length=4*1024*1024)
        with temporary.open('rb') as data:digest=hashlib.file_digest(data,'sha256').hexdigest()
        if digest!=package['sha256']:raise ValueError('Downloaded archive hash mismatch')
        temporary.replace(archive)
    with archive.open('rb') as data:digest=hashlib.file_digest(data,'sha256').hexdigest()
    if digest!=package['sha256']:raise ValueError('Cached archive hash mismatch')
    with ZipFile(archive) as z:
        roots={p.split('/')[0] for p in z.namelist() if p}
        if len(roots)!=1:raise ValueError('Expected one official archive root')
        for entry in z.namelist():
            target=(destination/entry).resolve()
            if not target.is_relative_to(destination.resolve()):raise ValueError('Archive path left project tools')
        root=destination/next(iter(roots));marker=root/'.tm2020-verified-archive-sha256'
        if not marker.exists() or marker.read_text().strip()!=digest:
            if root.exists():raise FileExistsError('Refusing to overlay an existing unverified installation')
            z.extractall(destination);marker.write_text(digest+'\n')
    result={**package,'archiveBytes':archive.stat().st_size,'root':str(root.resolve())}
    print('VERIFIED',package['name'],package['version'],'root',result['root'],flush=True)
    return result


if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=2) as pool:packages=list(pool.map(install,PACKAGES))
    (ROOT/'tools/ghidra-install.json').write_text(json.dumps({'schema':'tm2020_local_ghidra_tools_v1','packages':packages},indent=2)+'\n')
    print('PASS GHIDRA_TOOLS official_archives_verified=true project_local=true',flush=True)
