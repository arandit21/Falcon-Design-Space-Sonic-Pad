"""Build the unified UI + Fluidd package from supplied inputs, without device settings."""
from pathlib import Path
import os,json,hashlib,shutil,tarfile,gzip,io
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'sonic-pad-russian'
INPUTS=Path(os.environ.get('SONIC_RU_BUILD_INPUTS',str(ROOT/'inputs')))
OUT=ROOT/'dist/sonic_pad_russian'
NAME='Sonic_Pad_Russian_54.20_1.1.0'
DEST=OUT/NAME
DEST.mkdir(parents=True,exist_ok=True)

def sha(data):return hashlib.sha256(data).hexdigest()
def read(part,path):return (INPUTS/part/path).read_bytes()
expected=json.loads((SOURCE/'expected-live-hashes.json').read_text())
locale='usr/share/fluidd-pad/js/locale-ru-js.8485e6cf.js'
main='usr/share/fluidd-pad/js/app.45351586.js'
privacy='usr/share/fluidd-pad/js/chunk-057f496b.f0c607e8.js'
payload={}
text=read('ui',main).decode('utf8');needle='{name:"English",code:"en",icon:e("e770")},'
assert text.count(needle)==1
payload[main]=text.replace(needle,needle+'{name:"Русский",code:"ru",icon:e("513d")},').encode('utf8')
text=read('ui',privacy).decode('utf8');needle='"pt"===e?I:h';assert text.count(needle)==1
payload[privacy]=text.replace(needle,'"pt"===e?I:"ru"===e?g:h').encode('utf8')
text=read('ui',locale).decode('utf8');start=text.index('var t=')+6;end=text.rindex(';o[')
dictionary=json.loads((SOURCE/'ru.json').read_text(encoding='utf8'))
payload[locale]=(text[:start]+json.dumps(dictionary,ensure_ascii=False,separators=(',',':'))+text[end:]).encode('utf8')
for path in expected:
 if '/css/' in path:payload[path]=read('ui',path)
for path,data in payload.items():assert sha(data)==expected[path],path
for path in ['usr/share/fluidd/index.html','usr/share/fluidd/sw.js','usr/share/fluidd/assets/index-cbfa4fba.js','usr/share/fluidd/assets/ru-8fa4abd5.js']:
 payload[path]=read('web/live',path)
live_web=json.loads((SOURCE/'expected-fluidd-live-hashes.json').read_text())
for path,digest in live_web.items():assert sha(payload[path])==digest,path
files=[]
legacy={'usr/share/fluidd/index.html':['3d453ca3cf27c7a7e333bf13a515f423cd5aa57c215857e7e30ea2cec81aceeb'],'usr/share/fluidd/sw.js':['f576fbb132d22f35036164c0ce913280b6465ecf54c2ec8f6e0d64cb6d271a7f']}
for path,data in sorted(payload.items()):
 item={'path':path,'sha256':sha(data)}
 item['accepted_before']=None if '/css/' in path else [sha(read('ui' if 'fluidd-pad/' in path else 'web/stock',path))]+legacy.get(path,[])
 if '/fluidd/' in path and (INPUTS/'web/files'/path).exists():item['accepted_before'].append(sha(read('web/files',path)))
 files.append(item);target=DEST/'payload'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
guards=[]
for path in ['usr/share/fluidd-pad/index.html','usr/share/web/pad/main.qml']:
 guards.append({'path':path,'accepted_sha256':[sha(read('ui',path))]})
# The Russian Fluidd dictionary is now installed, not merely checked.
manifest={'package':'sonic-pad-russian-54.20-1.1.0','target':'Sonic Pad V1.0.6.54.20','screen_base':'fluidd-pad V1.3.3 (2023/10/10)','web_base':'V1.0.18_fluidd / upstream 1.24.0','files':files,'guards':guards,'settings_included':False,'translation_strings':1474,'privacy_agreement_language':'English fallback for ru'}
(DEST/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
for name in ['install.py','install.sh']:
 (DEST/name).write_bytes((SOURCE/name).read_text(encoding='utf-8-sig').replace('\r\n','\n').encode('utf8'))
if (ROOT/'docs/SONIC_PAD_RUSSIAN_SUITE.md').exists():shutil.copy2(ROOT/'docs/SONIC_PAD_RUSSIAN_SUITE.md',DEST/'README_RU.md')
checks=''.join(sha(p.read_bytes())+'  '+p.relative_to(DEST).as_posix()+'\n' for p in sorted(DEST.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.txt')
(DEST/'SHA256SUMS.txt').write_text(checks,encoding='utf8')
archive=OUT/(NAME+'.tar.gz')
with archive.open('wb') as output,gzip.GzipFile(filename='',fileobj=output,mode='wb',mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w') as tar:
 for p in sorted(DEST.rglob('*')):
  if p.is_file():
   data=p.read_bytes();info=tarfile.TarInfo(NAME+'/'+p.relative_to(DEST).as_posix());info.size=len(data);info.mode=0o755 if p.name=='install.sh' else 0o644;info.uid=info.gid=0;info.mtime=0;tar.addfile(info,io.BytesIO(data))
print('BUILT',archive,'files',len(files),'bytes',archive.stat().st_size)
