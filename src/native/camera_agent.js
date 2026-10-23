(function(){
'use strict';
// A remote photo source for the application's existing Qt camera interface.
const core=Process.getModuleByName('Qt5Core.dll'), media=Process.getModuleByName('Qt5Multimedia.dll'), gui=Process.getModuleByName('Qt5Gui.dll');
const keep=[], cameras=new Map(), captures=new Map(), requests=new Map();
let enabled=false,nextId=1;
const alias='SonicPad_Falcon_Camera';
function fn(m,n,r,a){return new NativeFunction(m.getExportByName(n),r,a);}
function hook(n,r,a,body){const addr=media.getExportByName(n),original=new NativeFunction(addr,r,a);const cb=new NativeCallback((...v)=>{try{const x=body(original,...v);return r==='bool'?(x?1:0):x;}catch(e){send({event:'camera_hook_error',name:n,error:String(e.stack)});return r==='void'?undefined:(r==='pointer'?ptr(0):0);}},r,a);keep.push(cb);Interceptor.replace(addr,cb);}
function qstr(p){const d=p.readPointer(),n=d.add(4).readS32();return d.add(d.add(16).readS64().toNumber()).readUtf16String(n);}
const qs=fn(core,'??0QString@@QEAA@PEBD@Z','pointer',['pointer','pointer']);
const qsd=fn(core,'??1QString@@QEAA@XZ','void',['pointer']);
const ba=fn(core,'??0QByteArray@@QEAA@PEBDH@Z','pointer',['pointer','pointer','int']);
const bad=fn(core,'??1QByteArray@@QEAA@XZ','void',['pointer']);
const infoCtor=fn(media,'??0QCameraInfo@@QEAA@AEBVQByteArray@@@Z','pointer',['pointer','pointer']);
const malloc=fn(Process.getModuleByName('ucrtbase.dll'),'malloc','pointer',['uint64']);
const detach=fn(core,'?detach@QListData@@QEAAPEAUData@1@H@Z','pointer',['pointer','int']);
const append=fn(core,'?append@QListData@@QEAAPEAPEAXXZ','pointer',['pointer']);
function remoteInfo(info){try{return qstr(info.readPointer().add(8))===alias;}catch(e){return false;}}
function listInit(out){out.writePointer(core.getExportByName('?shared_null@QListData@@2UData@1@B'));detach(out,1);}
hook('?availableCameras@QCameraInfo@@SA?AV?$QList@VQCameraInfo@@@@W4Position@QCamera@@@Z','pointer',['pointer','int'],(orig,out,pos)=>{
 orig(out,pos);if(!enabled || pos!==0)return out;
 const bytes=Memory.alloc(8);ba(bytes,Memory.allocUtf8String(''),0);
 const info=malloc(16);infoCtor(info,bytes);bad(bytes);
 // Qt 5.15 QCameraInfoPrivate layout, verified against this DLL's constructor.
 const data=info.readPointer();qsd(data.add(8));qs(data.add(8),Memory.allocUtf8String(alias));qsd(data.add(16));qs(data.add(16),Memory.allocUtf8String('Creality Falcon Camera (Sonic Pad)'));data.writeU8(0);
 if(out.readPointer().add(12).readS32()===out.readPointer().add(8).readS32())listInit(out);append(out).writePointer(info);send({event:'remote_camera_enumerated'});return out;
});
hook('??0QCamera@@QEAA@AEBVQCameraInfo@@PEAVQObject@@@Z','pointer',['pointer','pointer','pointer'],(orig,obj,info,parent)=>{const remote=enabled&&remoteInfo(info);const result=orig(obj,info,parent);if(remote)cameras.set(obj.toString(),{state:0,status:1});return result;});
hook('??1QCamera@@UEAA@XZ','void',['pointer'],(orig,obj)=>{cameras.delete(obj.toString());orig(obj);});
const invoke=fn(core,'?invokeMethod@QMetaObject@@SA_NPEAVQObject@@PEBDW4ConnectionType@Qt@@VQGenericReturnArgument@@VQGenericArgument@@444444444@Z','bool',['pointer','pointer','int',...Array(11).fill('pointer')]);
const empty=Memory.alloc(16);empty.writeByteArray(new Uint8Array(16));
function signal(obj,name,args){const held=[];const ga=args.map(([type,data])=>{const a=Memory.alloc(16),t=Memory.allocUtf8String(type);a.writePointer(data);a.add(8).writePointer(t);held.push(a,t,data);return a;});const n=Memory.allocUtf8String(name);held.push(n);if(!invoke(obj,n,2,empty,...ga,...Array(10-ga.length).fill(empty)))throw Error('Qt rejected '+name);}
function number(n){const p=Memory.alloc(4);p.writeS32(n);return p;}
for(const [method,state,status] of [['load',1,4],['start',2,8],['unload',0,1]])hook('?'+method+'@QCamera@@QEAAXXZ','void',['pointer'],(orig,obj)=>{const c=cameras.get(obj.toString());if(!c)return orig(obj);c.state=state;c.status=status;signal(obj,'stateChanged',[['QCamera::State',number(state)]]);signal(obj,'statusChanged',[['QCamera::Status',number(status)]]);});
for(const [name,ret,value] of [['availability','?AW4AvailabilityStatus@QMultimedia@@',0],['error','?AW4Error@1@',0],['state','?AW4State@1@',null],['status','?AW4Status@1@',null]]){
 const sym='?'+name+'@QCamera@@'+(name==='availability'?'UEBA':'QEBA')+ret+'XZ';
 hook(sym,'int',['pointer'],(orig,obj)=>{const c=cameras.get(obj.toString());return c?(value===null?c[name]:value):orig(obj);});
}
hook('?supportedViewfinderResolutions@QCamera@@QEBA?AV?$QList@VQSize@@@@AEBVQCameraViewfinderSettings@@@Z','pointer',['pointer','pointer','pointer'],(orig,obj,out,settings)=>{if(!cameras.has(obj.toString()))return orig(obj,out,settings);listInit(out);const node=append(out);node.writeS32(2592);node.add(4).writeS32(1944);return out;});
const settingsCtor=fn(media,'??0QCameraViewfinderSettings@@QEAA@XZ','pointer',['pointer']);
const settingsResolution=fn(media,'?setResolution@QCameraViewfinderSettings@@QEAAXAEBVQSize@@@Z','void',['pointer','pointer']);
hook('?viewfinderSettings@QCamera@@QEBA?AVQCameraViewfinderSettings@@XZ','pointer',['pointer','pointer'],(orig,obj,out)=>{if(!cameras.has(obj.toString()))return orig(obj,out);settingsCtor(out);const size=Memory.alloc(8);size.writeS32(2592);size.add(4).writeS32(1944);settingsResolution(out,size);return out;});
hook('?setViewfinderSettings@QCamera@@QEAAXAEBVQCameraViewfinderSettings@@@Z','void',['pointer','pointer'],(orig,obj,settings)=>{if(!cameras.has(obj.toString()))orig(obj,settings);});
hook('?setCaptureMode@QCamera@@QEAAXV?$QFlags@W4CaptureMode@QCamera@@@@@Z','void',['pointer','int'],(orig,obj,mode)=>{if(!cameras.has(obj.toString()))orig(obj,mode);});
hook('??0QCameraImageCapture@@QEAA@PEAVQMediaObject@@PEAVQObject@@@Z','pointer',['pointer','pointer','pointer'],(orig,obj,camera,parent)=>{const result=orig(obj,camera,parent);if(cameras.has(camera.toString()))captures.set(obj.toString(),camera);return result;});
hook('??1QCameraImageCapture@@UEAA@XZ','void',['pointer'],(orig,obj)=>{captures.delete(obj.toString());for(const [id,p] of requests)if(p.obj.equals(obj))requests.delete(id);orig(obj);});
for(const name of ['isAvailable','isReadyForCapture'])hook('?'+name+'@QCameraImageCapture@@QEBA_NXZ','bool',['pointer'],(orig,obj)=>captures.has(obj.toString())?true:orig(obj));
hook('?availability@QCameraImageCapture@@QEBA?AW4AvailabilityStatus@QMultimedia@@XZ','int',['pointer'],(orig,obj)=>captures.has(obj.toString())?0:orig(obj));
hook('?capture@QCameraImageCapture@@QEAAHAEBVQString@@@Z','int',['pointer','pointer'],(orig,obj,path)=>{if(!captures.has(obj.toString()))return orig(obj,path);const id=nextId++;requests.set(id,{obj:obj,path:qstr(path)});send({event:'remote_camera_photo_requested',id:id});return id;});
const imageCtor=fn(gui,'??0QImage@@QEAA@XZ','pointer',['pointer']);
const imageDtor=fn(gui,'??1QImage@@UEAA@XZ','void',['pointer']);
const imageLoad=fn(gui,'?loadFromData@QImage@@QEAA_NPEBEHPEBD@Z','bool',['pointer','pointer','int','pointer']);
const imageSave=fn(gui,'?save@QImage@@QEBA_NAEBVQString@@PEBDH@Z','bool',['pointer','pointer','pointer','int']);
const imageWidth=fn(gui,'?width@QImage@@QEBAHXZ','int',['pointer']);
const imageHeight=fn(gui,'?height@QImage@@QEBAHXZ','int',['pointer']);
function photoError(obj,id,error){const text=Memory.alloc(8);qs(text,Memory.allocUtf8String(String(error)));try{signal(obj,'error',[['int',number(id)],['QCameraImageCapture::Error',number(1)],['QString',text]]);}finally{qsd(text);}send({event:'remote_camera_photo_failed',id:id,error:String(error)});return false;}
rpc.exports={
 cameraConfigure(value){enabled=!!value;Interceptor.flush();return enabled;},
 cameraFrame(id,hex,error){
  const request=requests.get(id);if(!request)return false;
  const obj=request.obj;requests.delete(id);if(!captures.has(obj.toString()))return false;
  if(error)return photoError(obj,id,error);
  const image=Memory.alloc(64);imageCtor(image);let path=null;
  try{
   if(!hex || hex.length%2 || hex.length>24000000 || !/^[0-9a-f]+$/i.test(hex))throw Error('Invalid photo bytes');
   const raw=Memory.alloc(hex.length/2);raw.writeByteArray(hex.match(/../g).map(x=>parseInt(x,16)));
   if(!imageLoad(image,raw,hex.length/2,Memory.allocUtf8String('JPG')))throw Error('Invalid JPEG from remote camera');
   const w=imageWidth(image),h=imageHeight(image);
   if(request.path){path=Memory.alloc(8);qs(path,Memory.allocUtf8String(request.path));if(!imageSave(image,path,Memory.allocUtf8String('JPG'),-1))throw Error('Cannot save camera photo to '+request.path);}
   signal(obj,'imageCaptured',[['int',number(id)],['QImage',image]]);
   if(path)signal(obj,'imageSaved',[['int',number(id)],['QString',path]]);
   send({event:'remote_camera_photo_delivered',id:id,width:w,height:h});return {width:w,height:h};
  }catch(e){return photoError(obj,id,e);}
  finally{if(path)qsd(path);imageDtor(image);}
 }
};
send({event:'remote_camera_hooks_installed'});
})();
