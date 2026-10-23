"""Apply the supplied legacy patch with reversible application-file backups."""
from pathlib import Path
import hashlib
import json
import shutil


def apply(root, target):
    root, target = Path(root), Path(target)
    supplied = root / 'base_patch'
    files = ['FalconDesignSpace.exe', 'translations/ru-ru.qm', 'offline-data/materials.json']
    expected = '9ec27ec0c06814ba261706552df0a473b8dbb239bbdde2e37b8f6ab303b53f99'
    if hashlib.sha256((supplied/files[0]).read_bytes()).hexdigest() != expected:
        raise RuntimeError('Повреждён базовый патч FDS.')
    backup = root/'backups'/'application'
    backup.mkdir(parents=True, exist_ok=True)
    manifest = backup/'manifest.json'
    if not manifest.exists():
        records = []
        for name in files:
            path = target/name
            if path.exists():
                saved=backup/name;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,saved)
            records.append({'name':name,'existed':path.exists()})
        manifest.write_text(json.dumps({'target':str(target),'files':records}),encoding='utf8')
    try:
        for name in files:
            path=target/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(supplied/name,path)
    except Exception:
        restore(root)
        raise


def restore(root):
    backup=Path(root)/'backups'/'application';manifest=backup/'manifest.json'
    if not manifest.exists():return
    saved=json.loads(manifest.read_text(encoding='utf8'));target=Path(saved['target'])
    for record in saved['files']:
        path=target/record['name']
        if record['existed']:shutil.copy2(backup/record['name'],path)
        elif path.exists():path.unlink()
