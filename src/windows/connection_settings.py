import configparser
import ipaddress
import json
import struct
import time
import zlib
from pathlib import Path


def state_dir(root):
    marker=root/'user_data_path.txt'
    if not marker.exists():
        return root
    path=Path(marker.read_text(encoding='utf-8-sig').strip())
    if not path.is_absolute():
        raise RuntimeError('Неверный путь к настройкам Falcon')
    return path


def read_host(root):
    settings=configparser.ConfigParser(interpolation=None)
    path=state_dir(root)/'connection.ini'
    if path.exists():
        settings.read(path,encoding='utf-8-sig')
    host=settings.get('Connection','host',fallback='192.168.1.36').strip()
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        raise RuntimeError('Неверный IP-адрес Sonic Pad в connection.ini: '+host)
    return host


def resource_patch(root,host):
    meta=json.loads((root/'connection_resource.json').read_text(encoding='utf8'))
    template=(root/'connection_dialog.qml.in').read_text(encoding='utf8')
    source=template.replace('@@SETTINGS_FILE@@',json.dumps((state_dir(root)/'connection.ini').as_posix(),ensure_ascii=False)).replace('@@ACTIVE_HOST@@',json.dumps(host))
    raw=source.encode('utf8')
    compressed=struct.pack('>I',len(raw))+zlib.compress(raw)
    meta.update(node=meta['resources'][0]['node'],payload=(struct.pack('>I',len(compressed))+compressed).hex(),timestamp=list(struct.pack('>Q',int(time.time()*1000))))
    return meta
