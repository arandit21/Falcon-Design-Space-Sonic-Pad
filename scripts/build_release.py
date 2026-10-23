from pathlib import Path
import shutil,subprocess,zipfile,json,hashlib,os,sys

BASE=Path(__file__).resolve().parents[1]
SOURCE=BASE/'src'/'native'
PACK=BASE/'src'/'windows'
OUT=BASE/'dist'
PAYLOAD=OUT/'payload'
PYTHON=Path(os.environ.get('FALCON_BUILD_PYTHON',str(Path(sys.executable).parent)))
DEPENDENCIES=Path(os.environ.get('FALCON_BUILD_DEPENDENCIES',str(BASE/'build'/'dependencies')))
CSC=Path(r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe')
OUT.mkdir(exist_ok=True);PAYLOAD.mkdir(exist_ok=True)
for name in ['run_native.py','serial_tcp_agent.js','camera_agent.js','camera_bridge.py','sonic_camera_photo.py','sonic_serial_relay.py','sonic_native.sh']:
    shutil.copy2(SOURCE/name,PAYLOAD/name)
# Preserve the working native USB implementation; only noninteractive process
# startup is added in the production copy.
p=PAYLOAD/'run_native.py';s=p.read_text(encoding='utf8')
marker="PAD = 'root@192.168.1.36'"
assert marker in s
s=s.replace(marker,marker+"\nif os.environ.get('FALCON_PERMANENT_LAUNCH') == '1':\n    SSH_OPTIONS += ['-oBatchMode=yes', '-oConnectTimeout=8']")
p.write_text(s,encoding='utf8')
for name in ['first_setup.py','base_install.py','production_entry.py','install.py','connection_settings.py','connection_agent.js','connection_dialog.qml.in','startup_support.py','falcon.ico']:shutil.copy2(PACK/name,PAYLOAD/name)
shutil.copy2(SOURCE/'connection_resource.json',PAYLOAD/'connection_resource.json')
p=PAYLOAD/'run_native.py';s=p.read_text(encoding='utf8')
s=s.replace("EXPECTED = '9ec27", "if (ROOT / 'FalconDesignSpace.exe').is_file():\n    EXE = ROOT / 'FalconDesignSpace.exe'\nEXPECTED = '9ec27")
start=s.index("    runtime = ROOT / 'runtime'");end=s.index("    print('NATIVE USB:",start)
block=s[start:end]
block=block.replace("'/XD', 'log', 'repository',", "'/XD', 'log', 'repository', str(ROOT),")
s=s[:start]+"    if ROOT.resolve() == EXE.parent.resolve():\n        runtime = EXE.parent\n        local_exe = EXE\n    else:\n"+''.join('    '+line+'\n' for line in block.splitlines())+s[end:]
s=s.replace("PAD = 'root@192.168.1.36'", "from connection_settings import read_host, resource_patch\nCONNECTION_HOST = read_host(ROOT)\nPAD = 'root@' + CONNECTION_HOST")
s=s.replace('from connection_settings import read_host, resource_patch', 'from connection_settings import read_host, resource_patch\nfrom startup_support import refresh_lease')
s=s.replace("request(control_port, {'op': 'lease', 'instance': instance})", "refresh_lease(request, control_port, instance)")
s=s.replace("    SSH_OPTIONS += ['-oBatchMode=yes', '-oConnectTimeout=8']", "    SSH_OPTIONS += ['-oBatchMode=yes', '-oConnectTimeout=8']\n    if (ROOT / '.ssh' / 'known_hosts').exists():\n        SSH_OPTIONS += ['-oHostKeyAlias=falcon-sonic-pad', '-oStrictHostKeyChecking=yes', '-oUserKnownHostsFile=\"' + (ROOT / '.ssh' / 'known_hosts').as_posix() + '\"']")
marker="        device.resume(pid)"
s=s.replace('from connection_settings import read_host, resource_patch', 'from connection_settings import read_host, resource_patch, state_dir\nSTATE_ROOT = state_dir(ROOT)')
s=s.replace("(ROOT / '.ssh' / 'known_hosts')", "(STATE_ROOT / '.ssh' / 'known_hosts')")
s=s.replace("key_dir = ROOT / '.ssh'", "key_dir = STATE_ROOT / '.ssh'")
s=s.replace("log_dir = ROOT / 'results'", "log_dir = STATE_ROOT / 'results'")
s=s.replace("runtime = ROOT / 'runtime'", "runtime = STATE_ROOT / 'runtime'")
# The elevated installer sets the existing key ACL once. A normal launch has
# read access and must not attempt to rewrite the administrator-owned ACL.
acl_line="    subprocess.run(['icacls', str(key), '/inheritance:r', '/grant:r', account + ':(R)'], check=True, stdout=subprocess.DEVNULL)"
assert s.count(acl_line)==1
s=s.replace(acl_line,"    # Existing SSH key permissions are configured by the installer.")
assert s.count(marker)==1
s=s.replace(marker,"        connection_script = session.create_script((ROOT / 'connection_agent.js').read_text(encoding='utf8'))\n        connection_script.on('message', lambda message, data: print(json.dumps(message, ensure_ascii=False), flush=True))\n        connection_script.load()\n        connection_script.exports_sync.configure(resource_patch(ROOT, CONNECTION_HOST))\n"+marker)
s=s.replace("EXE = pathlib.Path(r'C:\\Program Files\\Falcon Design Space\\FalconDesignSpace.exe')", "EXE = pathlib.Path((ROOT / 'fds_directory.txt').read_text(encoding='utf8').strip()) / 'FalconDesignSpace.exe' if (ROOT / 'fds_directory.txt').exists() else pathlib.Path(r'C:\\Program Files\\Falcon Design Space\\FalconDesignSpace.exe')")
p.write_text(s,encoding='utf8')
build=json.loads((SOURCE/'build_metadata.json').read_text(encoding='utf8'))
build.update(revision='permanent-ru-1.3.0',camera_calibration_personalized=False)
(PAYLOAD/'build.json').write_text(json.dumps(build,indent=2)+'\n',encoding='utf8')
# Calibration is specific to an individual machine. Preserve existing user profiles;
# never distribute the developer's calibration as a universal factory profile.
(PAYLOAD/'calibration.json').write_text(json.dumps({'version':'1.7.9','CameraConfig':[]}),encoding='utf8')
shutil.copytree(DEPENDENCIES,PAYLOAD/'dependencies',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copytree(BASE/'sonic-pad',PAYLOAD/'sonic-pad',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copytree(BASE/'third-party',PAYLOAD/'third-party',dirs_exist_ok=True)
shutil.copytree(BASE/'docs',PAYLOAD/'docs',dirs_exist_ok=True)
for name in ['README.md','NOTICE_RU.md']:shutil.copy2(BASE/name,PAYLOAD/name)
dest=PAYLOAD/'python';dest.mkdir(exist_ok=True)
for name in ['python.exe','pythonw.exe','python3.dll','python312.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt']:shutil.copy2(PYTHON/name,dest/name)
shutil.copytree(PYTHON/'DLLs',dest/'DLLs',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(PYTHON/'Lib',dest/'Lib',dirs_exist_ok=True,ignore=shutil.ignore_patterns('site-packages','__pycache__','*.pyc','test','tests','idlelib','turtledemo','ensurepip'))
subprocess.run([str(CSC),'/nologo','/codepage:65001','/target:winexe','/optimize+','/platform:x64','/win32icon:'+str(PACK/'falcon.ico'),'/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','/out:'+str(PAYLOAD/'FalconSonicPad.exe'),str(PACK/'Launcher.cs'),str(PACK/'AssemblyInfo.cs')],check=True)

legacy=Path(os.environ['FALCON_LEGACY_PATCH_ZIP'])
with zipfile.ZipFile(legacy) as archive:
    for name in ['FalconDesignSpace.exe','translations/ru-ru.qm','offline-data/materials.json']:
        target=PAYLOAD/'base_patch'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(name))

zip_path=OUT/'payload.zip'
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(PAYLOAD.rglob('*')):
        if p.is_file():
            name=p.relative_to(PAYLOAD).as_posix()
            assert not any(part in {'.ssh','results','runtime','backups'} for part in p.relative_to(PAYLOAD).parts)
            z.write(p,name)
subprocess.run([str(CSC),'/nologo','/codepage:65001','/target:winexe','/optimize+','/platform:x64','/win32icon:'+str(PACK/'falcon.ico'),'/win32manifest:'+str(PACK/'setup.manifest'),'/resource:'+str(PACK/'falcon.ico')+',falcon.ico','/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','/reference:System.IO.Compression.dll','/reference:System.IO.Compression.FileSystem.dll','/resource:'+str(zip_path)+',payload.zip','/out:'+str(OUT/'FalconSonicPad_Setup.exe'),str(PACK/'Setup.cs'),str(PACK/'AssemblyInfo.cs')],check=True)
manifest={'version':'1.3.0','setup_sha256':hashlib.sha256((OUT/'FalconSonicPad_Setup.exe').read_bytes()).hexdigest(),'camera_resolution':[2592,1944],'includes_personal_camera_calibration':False,'original_exe_changed':True,'includes_legacy_base_patch':True,'fresh_install_supported':True,'contains_private_keys':False,'bundled_python':'3.12'}
(OUT/'release.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
print('BUILT',OUT/'FalconSonicPad_Setup.exe',flush=True)
