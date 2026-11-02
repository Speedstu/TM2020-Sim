"""Validate the cached whole-.text atlas or rebuild it after a source change."""
import hashlib
import json
from pathlib import Path
import sqlite3
from reverse_atlas import build
from reverse_physics import ROOT,SHA
exe=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
database=ROOT/'local/recon/game-atlas.sqlite';metadata=database.with_suffix('.json')
generator=hashlib.sha256((ROOT/'scripts/reverse_atlas.py').read_bytes()).hexdigest()
cached=json.loads(metadata.read_text()) if metadata.exists() else {}
if not database.exists() or cached.get('sha256')!=SHA or cached.get('generatorSha256')!=generator:
    build(exe,database);cached=json.loads(metadata.read_text())
with database.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
if digest!=cached['databaseSha256']:raise ValueError('Atlas artifact hash mismatch')
with sqlite3.connect(database) as connection:
    if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Atlas integrity failure')
    for table,key in [('procedures','procedures'),('edges','edges'),('xrefs','stringXrefs'),('strings','strings')]:
        if connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]!=cached[key]:raise ValueError(f'Atlas {table} count mismatch')
    if connection.execute('SELECT count(*) FROM procedures WHERE root=?',(0x851f00,)).fetchone()[0]!=1:raise ValueError('Observed force variant absent')
print('PASS WHOLE_TEXT_ATLAS integrity=true procedures',cached['procedures'],'linear_edges',cached['edges'],'complete_semantics=false')
