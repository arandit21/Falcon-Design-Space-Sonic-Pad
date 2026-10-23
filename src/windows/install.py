"""Install Russian settings, the saved camera profile and a single shortcut."""
import base64
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent


def read_json(path, fallback):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else fallback


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # A backup is made before settings are touched. Writing the named file also
    # works when Windows grants access to that file without directory rename rights.
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def apply_profile(existing, supplied):
    existing.setdefault('CameraConfig', [])
    existing.setdefault('version', supplied.get('version', '1.7.9'))
    for machine in supplied['CameraConfig']:
        for machine_id, incoming in machine.items():
            target = next((m[machine_id] for m in existing['CameraConfig'] if machine_id in m), None)
            if target is None:
                existing['CameraConfig'].append({machine_id: incoming})
                continue
            for camera in incoming:
                for name, profile in camera.items():
                    current = next((c for c in target if name in c), None)
                    # Keep a profile the user has already saved for this camera.
                    if current is None:
                        target.append({name: profile})
    return existing


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def powershell(source):
    encoded = base64.b64encode(source.encode('utf-16le')).decode('ascii')
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded], check=True, creationflags=subprocess.CREATE_NO_WINDOW)


def shortcuts(root, remove=False):
    target = root / 'FalconSonicPad.exe'
    desktop_name = 'Falcon — Sonic Pad.lnk'
    start_name = 'Falcon — восстановление настроек.lnk'
    pair_name = 'Falcon — настройка Sonic Pad.lnk'
    source = "$ErrorActionPreference='Stop';$w=New-Object -ComObject WScript.Shell;"
    source += '$p=Join-Path ([Environment]::GetFolderPath("Desktop")) ' + ps_quote(desktop_name) + ';'
    source += '$r=Join-Path ([Environment]::GetFolderPath("Programs")) ' + ps_quote(start_name) + ';'
    source += '$b=Join-Path ([Environment]::GetFolderPath("Programs")) ' + ps_quote(pair_name) + ';'
    if remove:
        source += 'if(Test-Path -LiteralPath $p){$s=$w.CreateShortcut($p);if($s.TargetPath -eq ' + ps_quote(target) + '){Remove-Item -LiteralPath $p}};'
        source += 'if(Test-Path -LiteralPath $r){$s=$w.CreateShortcut($r);if($s.TargetPath -eq ' + ps_quote(root / 'Восстановление.exe') + '){Remove-Item -LiteralPath $r}}'
        source += ';if(Test-Path -LiteralPath $b){$s=$w.CreateShortcut($b);if($s.TargetPath -eq ' + ps_quote(target) + '){Remove-Item -LiteralPath $b}}'
    else:
        source += '$s=$w.CreateShortcut($p);$s.TargetPath=' + ps_quote(target) + ';$s.WorkingDirectory=' + ps_quote(root) + ';$s.IconLocation=' + ps_quote(str(root / 'falcon.ico') + ',0') + ';$s.Description=' + ps_quote('Falcon A1 через Sonic Pad — камера и калибровка') + ';$s.Save();'
        source += '$s=$w.CreateShortcut($r);$s.TargetPath=' + ps_quote(root / 'Восстановление.exe') + ';$s.Arguments="/rollback";$s.WorkingDirectory=' + ps_quote(root) + ';$s.Save()'
        source += ';$s=$w.CreateShortcut($b);$s.TargetPath=' + ps_quote(target) + ';$s.Arguments="/pairing";$s.WorkingDirectory=' + ps_quote(root) + ';$s.IconLocation=' + ps_quote(str(root/'falcon.ico')+',0') + ';$s.Save()'
    powershell(source)


def install(root, config_root, key_source, make_shortcuts=True, data_root=None):
    root = root.resolve()
    data_root=(data_root or root).resolve()
    data_root.mkdir(parents=True,exist_ok=True)
    if data_root!=root:
        (root/'user_data_path.txt').write_text(str(data_root),encoding='utf8')
    if not (data_root / 'connection.ini').exists():
        if (root/'connection.ini').exists():shutil.copy2(root/'connection.ini',data_root/'connection.ini')
        else:(data_root / 'connection.ini').write_text('[Connection]\nhost=192.168.1.36\n', encoding='utf8')
    key_target = data_root / '.ssh' / 'falcon_sonic_rsa'
    if (root/'.ssh'/'falcon_sonic_rsa').exists():key_source=root/'.ssh'/'falcon_sonic_rsa'
    if not key_target.exists():
        key_target.parent.mkdir(parents=True, exist_ok=True)
        if key_source.exists() and key_source.with_suffix('.pub').exists():
            shutil.copy2(key_source, key_target)
            shutil.copy2(key_source.with_suffix('.pub'), key_target.with_suffix('.pub'))
        else:
            subprocess.run(['ssh-keygen','-t','rsa','-b','3072','-m','PEM','-N','','-C','falcon-sonic-pad','-f',str(key_target)],check=True,stdout=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    if make_shortcuts:
        account = os.environ.get('USERDOMAIN', '') + '\\' + os.environ['USERNAME']
        subprocess.run(['icacls', str(key_target), '/inheritance:r', '/grant:r', account + ':(R)'], check=True, stdout=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        trusted = data_root / '.ssh' / 'known_hosts'
        if not trusted.exists() and (root/'.ssh'/'known_hosts').exists():shutil.copy2(root/'.ssh'/'known_hosts',trusted)
        if not trusted.exists():
            result = subprocess.run(['ssh-keygen', '-F', '192.168.1.36'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
            entries = []
            for line in result.stdout.decode('utf8', errors='replace').splitlines():
                fields = line.split()
                if fields and not line.startswith('#') and len(fields) >= 3:
                    entries.append('falcon-sonic-pad ' + ' '.join(fields[1:]))
            if entries:
                trusted.write_text('\n'.join(entries) + '\n', encoding='ascii')
    files = [config_root / 'falcondesignspace.conf', config_root / 'camera' / 'cameraConfig.txt']
    backup = root / 'backups' / 'before_install'
    backup.mkdir(parents=True, exist_ok=True)
    manifest = backup / 'manifest.json'
    if not manifest.exists():
        records = []
        for index, path in enumerate(files):
            saved = str(index) + '.json'
            if path.exists():
                shutil.copy2(path, backup / saved)
            records.append({'target': str(path), 'backup': saved, 'existed': path.exists()})
        write_json(manifest, {'files': records, 'created': datetime.datetime.now().isoformat()})
    settings = read_json(files[0], {})
    settings.setdefault('Basic', {})['Language'] = 9  # Existing, verified Russian UI.
    camera = apply_profile(read_json(files[1], {}), read_json(root / 'calibration.json', {}))
    try:
        write_json(files[0], settings)
        write_json(files[1], camera)
        if make_shortcuts:
            shortcuts(root)
    except Exception:
        rollback(root, make_shortcuts=False)
        raise
    write_json(root / 'installed.json', {'version': '1.3.0', 'language': 'ru', 'camera_size': [2592, 1944], 'installed': datetime.datetime.now().isoformat(), 'original_exe_changed': (root/'base_patch').is_dir()})


def rollback(root, make_shortcuts=True):
    backup = root / 'backups' / 'before_install'
    manifest = read_json(backup / 'manifest.json', {})
    if not manifest:
        raise RuntimeError('Резервная копия настроек не найдена.')
    for record in manifest['files']:
        target = pathlib.Path(record['target'])
        if record['existed']:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / record['backup'], target)
        elif target.exists():
            target.unlink()
    if make_shortcuts:
        shortcuts(root, remove=True)


if __name__ == '__main__':
    try:
        if '--rollback' in sys.argv:
            rollback(ROOT)
            from base_install import restore
            restore(ROOT)
        else:
            profile = pathlib.Path(os.environ['USERPROFILE'])
            config = pathlib.Path(os.environ.get('FALCON_CONFIG_ROOT', str(pathlib.Path(os.environ['LOCALAPPDATA']) / 'Falcon Design Space' / 'conf')))
            default_root=pathlib.Path(os.environ['LOCALAPPDATA'])/'FalconSonicPad'/'FDS'
            data_root=ROOT if ROOT.resolve()==default_root.resolve() else pathlib.Path(os.environ.get('FALCON_DATA_ROOT',str(pathlib.Path(os.environ['LOCALAPPDATA'])/'FalconSonicPad'/'Data')))
            key_source=default_root / '.ssh' / 'falcon_sonic_rsa'
            # Preserve the working per-user installation when moving to Program Files.
            if ROOT.resolve()!=default_root.resolve() and (default_root/'.ssh'/'falcon_sonic_rsa').exists():
                key_source=default_root/'.ssh'/'falcon_sonic_rsa'
                data_root.mkdir(parents=True,exist_ok=True)
                for name in ['connection.ini','.ssh/known_hosts']:
                    source=default_root/name;target=data_root/name
                    if source.exists() and not target.exists():
                        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
            from base_install import apply,restore
            target=pathlib.Path((ROOT/'fds_directory.txt').read_text(encoding='utf8').strip())
            apply(ROOT,target)
            try:install(ROOT, config, key_source,data_root=data_root)
            except Exception:
                restore(ROOT)
                raise
        print('Готово')
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
