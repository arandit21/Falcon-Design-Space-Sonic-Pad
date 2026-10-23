#!/usr/bin/env python3
"""Unified Sonic Pad 54.20 localization installer. Python 3.7+, no machine commands."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import time

HERE=Path(__file__).resolve().parent
PACKAGE='sonic-pad-russian-54.20-1.0.0'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def destination(root,relative):
    value=PurePosixPath(relative)
    if value.is_absolute() or '..' in value.parts or not value.parts:
        raise RuntimeError('Недопустимый путь в манифесте: '+relative)
    if not (relative.startswith('usr/share/fluidd-pad/') or relative.startswith('usr/share/fluidd/')):
        raise RuntimeError('Путь не относится к ресурсам интерфейса: '+relative)
    return Path(root).joinpath(*value.parts)

def load_manifest(package):
    manifest=json.loads((package/'manifest.json').read_text(encoding='utf8'))
    if manifest.get('package')!=PACKAGE:raise RuntimeError('Неподдерживаемый пакет.')
    if len(manifest['files'])!=13 or len({x['path'] for x in manifest['files']})!=13:
        raise RuntimeError('В пакете должен быть точный набор из 13 файлов.')
    for item in manifest['files']:
        source=destination(package/'payload',item['path'])
        if not source.is_file() or source.is_symlink() or digest(source)!=item['sha256']:
            raise RuntimeError('Повреждён файл пакета: '+item['path'])
    return manifest

def check(package,root):
    manifest=load_manifest(package)
    for guard in manifest['guards']:
        relative=guard['path'];path=Path(root).joinpath(*PurePosixPath(relative).parts)
        if not path.is_file() or path.is_symlink() or digest(path) not in guard['accepted_sha256']:
            raise RuntimeError('Несовместимая сборка интерфейса: '+relative)
    for item in manifest['files']:
        path=destination(root,item['path'])
        if not path.is_file() or path.is_symlink():raise RuntimeError('Отсутствует обычный файл: '+item['path'])
        accepted=item.get('accepted_before')
        if accepted is not None and digest(path) not in set(accepted+[item['sha256']]):
            raise RuntimeError('Неизвестное содержимое файла: '+item['path'])
    print('CHECK PASSED: совместимая сборка и целостность 13 файлов подтверждены.')
    return manifest

def verify(package,root):
    manifest=load_manifest(package)
    bad=[item['path'] for item in manifest['files'] if not destination(root,item['path']).is_file() or digest(destination(root,item['path']))!=item['sha256']]
    if bad:raise RuntimeError('Не совпадают установленные файлы: '+', '.join(bad))
    print('VERIFIED: экран Sonic Pad, переносы и Fluidd соответствуют общему пакету.')

def snapshot(root,folder,manifest):
    folder.mkdir(parents=True,exist_ok=False)
    records=[]
    for item in manifest['files']:
        source=destination(root,item['path']);target=destination(folder,item['path']);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(str(source),str(target))
        records.append({'path':item['path'],'sha256':digest(target),'mode':stat.S_IMODE(source.stat().st_mode)})
    (folder/'snapshot.json').write_text(json.dumps({'package':PACKAGE,'files':records},ensure_ascii=False,indent=2),encoding='utf8')

def snapshot_records(folder,manifest):
    saved=json.loads((folder/'snapshot.json').read_text(encoding='utf8'))
    if saved.get('package')!=PACKAGE or {x['path'] for x in saved['files']}!={x['path'] for x in manifest['files']}:
        raise RuntimeError('Несовместимая резервная копия.')
    for item in saved['files']:
        source=destination(folder,item['path'])
        if not source.is_file() or source.is_symlink() or digest(source)!=item['sha256']:
            raise RuntimeError('Повреждена резервная копия: '+item['path'])
    return saved['files']

def atomic_copy(source,target,mode):
    temporary=target.with_name('.'+target.name+'.sonic-ru-'+str(os.getpid())+'.tmp')
    created=False
    try:
        with source.open('rb') as src,temporary.open('xb') as dst:
            created=True
            shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
        os.chmod(str(temporary),mode);os.replace(str(temporary),str(target))
    finally:
        if created and temporary.exists():temporary.unlink()

def restore_snapshot(root,folder,manifest):
    records=snapshot_records(folder,manifest)
    for item in records:atomic_copy(destination(folder,item['path']),destination(root,item['path']),item['mode'])
    for item in records:
        if digest(destination(root,item['path']))!=item['sha256']:raise RuntimeError('Проверка восстановления не прошла: '+item['path'])


def install(package,root,state):
    manifest=check(package,root)
    if all(digest(destination(root,item['path']))==item['sha256'] for item in manifest['files']):
        print('ALREADY INSTALLED: повторная запись не требуется.');return
    state.mkdir(parents=True,exist_ok=True)
    original=state/'original'
    if original.exists():snapshot_records(original,manifest)
    else:snapshot(root,original,manifest)
    transaction=state/('before-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid())+'-'+str(time.time_ns()))
    snapshot(root,transaction,manifest)
    try:
        for item in manifest['files']:
            target=destination(root,item['path']);atomic_copy(destination(package/'payload',item['path']),target,stat.S_IMODE(target.stat().st_mode))
        verify(package,root)
    except Exception:
        restore_snapshot(root,transaction,manifest)
        print('Установка не завершена: восстановлено состояние перед этой попыткой.',file=sys.stderr)
        raise
    print('INSTALLED: комплексная русификация Sonic Pad 54.20 установлена.')
    print('Исходные файлы сохранены: '+str(original))
    print('Выберите Русский в настройках экрана и Fluidd. Перезапуск выполняйте после завершения заданий.')

def restore(package,root,state):
    manifest=check(package,root)
    restore_snapshot(root,state/'original',manifest)
    print('RESTORED: возвращены файлы до первой установки общего пакета.')

def main():
    parser=argparse.ArgumentParser(description='Русификация Sonic Pad 54.20: экран, переносы, Fluidd')
    parser.add_argument('action',choices=['check','install','verify','restore'],nargs='?',default='check')
    args=parser.parse_args()
    if not hasattr(os,'geteuid') or os.geteuid()!=0:raise RuntimeError('Запускайте от root на Sonic Pad, не на Windows.')
    if sys.version_info<(3,7):raise RuntimeError('Требуется Python 3.7 или новее.')
    root=Path('/');state=Path('/mnt/UDISK/sonic-pad-russian-54.20-backup')
    if args.action=='check':check(HERE,root)
    elif args.action=='verify':verify(HERE,root)
    else:
        import fcntl
        with open('/tmp/sonic-pad-russian-54.20.lock','a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('Другая установка/восстановление уже выполняется.')
            if args.action=='install':install(HERE,root,state)
            else:restore(HERE,root,state)

if __name__=='__main__':
    try:main()
    except Exception as error:print('ОШИБКА: '+str(error),file=sys.stderr);sys.exit(1)
