(function(){
'use strict';
// Native transport candidate: only loopback sockets protected by SSH forwarding.
const core=Process.getModuleByName('Qt5Core.dll');
const serial=Process.getModuleByName('Qt5SerialPort.dll');
const ws=Process.getModuleByName('WS2_32.dll');
const objects=new Map(), keep=[];
let config=null;
let timerTicks=0,maxAvailable=0,traceCount=0;
let wireCount=0;
function wire(direction,buffer,size){
 if(size<=0 || wireCount++>=4000)return;
 const bytes=new Uint8Array(buffer.readByteArray(Math.min(size,1024)));
 send({event:'serial_wire',direction:direction,size:size,hex:Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('')});
}
function trace(event){if(traceCount++<250)send({event:'serial_trace',...event});}
const NIL=ptr(0);
function fun(mod,name,ret,args){return new NativeFunction(mod.getExportByName(name),ret,args);}
function replace(name,ret,args,fn){
 const address=serial.getExportByName(name), original=new NativeFunction(address,ret,args);
 const cb=new NativeCallback((...v)=>{
  try{
   const observe=name.indexOf('?open@')===0 || name.indexOf('?close@')===0 || name.indexOf('?clear@')===0 || name.indexOf('?writeData@')===0 || name.indexOf('?readData@')===0;
   const state=objects.get(v[0].toString());
   if(observe)trace({phase:'enter',method:name,obj:v[0].toString(),remote:!!state,socket:!!(state&&state.sock),length:v.length>2?String(v[2]):undefined});
   const value=fn(original,...v);
   if(observe)trace({phase:'return',method:name,obj:v[0].toString(),result:String(value)});
   return ret==='bool'?(value?1:0):value;
  }catch(e){send({event:'hook_error',name:name,stack:String(e.stack)});return ret==='void'?undefined:(ret==='bool'?0:-1);}
 },ret,args);keep.push(cb);Interceptor.replace(address,cb);
}
function qstr(p){const d=p.readPointer();const n=d.add(4).readS32();return d.add(d.add(16).readS64().toNumber()).readUtf16String(n);}
const socket=fun(ws,'socket','pointer',['int','int','int']);
const connect=fun(ws,'connect','int',['pointer','pointer','int']);
const close=fun(ws,'closesocket','int',['pointer']);
const ioctl=fun(ws,'ioctlsocket','int',['pointer','int','pointer']);
let lastSocketError=0;
function socketFunction(name){
 const call=new SystemFunction(ws.getExportByName(name),'int',['pointer','pointer','int','int']);
 return (...args)=>{const result=call(...args);lastSocketError=result.lastError;return result.value;};
}
const recv=socketFunction('recv');
const sendBytes=socketFunction('send');
const select=fun(ws,'select','int',['int','pointer','pointer','pointer','pointer']);
const error=()=>lastSocketError;
const getOption=fun(ws,'getsockopt','int',['pointer','int','int','pointer','pointer']);
const inet=fun(ws,'inet_addr','uint',['pointer']);
const startup=fun(ws,'WSAStartup','int',['uint','pointer']);
const wsa=Memory.alloc(512);if(startup(0x202,wsa)!==0)throw Error('WSAStartup failed');
const baseOpen=fun(core,'?open@QIODevice@@UEAA_NV?$QFlags@W4OpenModeFlag@QIODevice@@@@@Z','bool',['pointer','int']);
const baseClose=fun(core,'?close@QIODevice@@UEAAXXZ','void',['pointer']);
const baseAvailable=fun(core,'?bytesAvailable@QIODevice@@UEBA_JXZ','int64',['pointer']);
const invoke=fun(core,'?invokeMethod@QMetaObject@@SA_NPEAVQObject@@PEBDW4ConnectionType@Qt@@VQGenericReturnArgument@@VQGenericArgument@@444444444@Z','bool',['pointer','pointer','int',...Array(11).fill('pointer')]);
const emptyArg=Memory.alloc(16);emptyArg.writeByteArray(new Uint8Array(16));
function emitQueued(obj,name,n,typeName='qint64'){
 const arg=Memory.alloc(16);arg.writeByteArray(new Uint8Array(16));
 // Keep the pointed-to storage alive until Qt copies the queued arguments.
 const held=[arg,Memory.allocUtf8String(name)];
 if(n!==undefined){
  const data=Memory.alloc(8),type=Memory.allocUtf8String(typeName);
  if(typeName==='qint64')data.writeS64(n);else data.writeS32(n);arg.writePointer(data);arg.add(8).writePointer(type);held.push(data,type);
 }
 const ok=invoke(obj,held[1],2,emptyArg,arg,...Array(9).fill(emptyArg));
 if(!ok)throw Error('Qt rejected queued signal '+name);
 return ok;
}
function wait(sock,writing,ms){
 const set=Memory.alloc(16);set.writeU32(1);set.add(8).writePointer(sock);
 const timeout=Memory.alloc(8);timeout.writeS32(Math.floor(ms/1000));timeout.add(4).writeS32((ms%1000)*1000);
 const result=select(0,writing?NIL:set,writing?set:NIL,NIL,timeout);
 
 return result>0;
}
function control(request){
 if(!config.controlPort)return true; // Isolated echo fixture has no controls.
 const sock=socket(2,1,6);
 if(sock.equals(ptr('0xffffffffffffffff')))throw Error('Control socket failed');
 try{
  const nb=Memory.alloc(4);nb.writeU32(1);ioctl(sock,0x8004667e|0,nb);
  const addr=Memory.alloc(16);addr.writeByteArray(new Uint8Array(16));addr.writeU16(2);
  addr.add(2).writeU8(config.controlPort>>8);addr.add(3).writeU8(config.controlPort&255);
  addr.add(4).writeU32(inet(Memory.allocUtf8String('127.0.0.1')));
  if(connect(sock,addr,16)!==0 && !wait(sock,true,2000))throw Error('Control connection timed out');
  const text=JSON.stringify(request)+'\n',buffer=Memory.allocUtf8String(text);
  let offset=0;
  while(offset<text.length){if(!wait(sock,true,2000))throw Error('Control write timed out');const n=sendBytes(sock,buffer.add(offset),text.length-offset,0);if(n<=0)throw Error('Control write failed');offset+=n;}
  const output=Memory.alloc(8192);let size=0;
  while(size<8191){
   if(!wait(sock,false,2000))throw Error('Control reply timed out');
   const n=recv(sock,output.add(size),8191-size,0);if(n<=0)throw Error('Control connection closed');size+=n;
   const response=output.readUtf8String(size);
   if(response.indexOf('\n')>=0){const result=JSON.parse(response);if(!result.ok)throw Error(result.error||'Serial control refused');return result;}
  }
  throw Error('Control reply too large');
 }finally{close(sock);}
}
function available(state){
 if(!state.sock)return 0;
 const n=Memory.alloc(4);n.writeU32(0);
 if(ioctl(state.sock,0x4004667f,n)!==0){state.error=9;return 0;}
 return n.readU32();
}
function shutdown(state){if(state.sock){close(state.sock);state.sock=null;}state.tx=[];state.pending=0;state.written=0;state.waited=0;}
function flushPending(state){
 let total=0;
 while(state.sock && state.tx.length){
  const item=state.tx[0],bytes=new Uint8Array(item.data,item.offset),buffer=Memory.alloc(bytes.length);buffer.writeByteArray(bytes);
  const n=sendBytes(state.sock,buffer,bytes.length,0);
  if(n<0 && error()===10035)break;
  if(n<=0){state.error=9;shutdown(state);return -1;}
  total+=n;item.offset+=n;state.pending-=n;if(item.offset===item.data.byteLength)state.tx.shift();
 }
 if(total>0){state.written+=total;emitQueued(state.obj,'bytesWritten',total);}
 return total;
}
Interceptor.attach(serial.getExportByName('??1QSerialPort@@UEAA@XZ'),{onEnter(args){const key=args[0].toString(),state=objects.get(key);if(state){shutdown(state);objects.delete(key);}}});
Interceptor.attach(serial.getExportByName('?setPortName@QSerialPort@@QEAAXAEBVQString@@@Z'),{
 onEnter(args){
  const key=args[0].toString(),old=objects.get(key),name=qstr(args[1]);
  trace({phase:'name',obj:key,name:name});
  if(old && name==='SonicPad_A1')return;
  if(old){shutdown(old);objects.delete(key);}
  if(name==='SonicPad_A1')objects.set(key,{obj:ptr(key),sock:null,error:0,lastSignal:0,tx:[],pending:0,written:0,waited:0});
 }
});
replace('?open@QSerialPort@@UEAA_NV?$QFlags@W4OpenModeFlag@QIODevice@@@@@Z','bool',['pointer','int'],(original,obj,mode)=>{
 const state=objects.get(obj.toString());if(!state)return original(obj,mode);
 if(!config){state.error=3;return false;}
 shutdown(state);state.sock=socket(2,1,6);
 if(state.sock.equals(ptr('0xffffffffffffffff'))){state.sock=null;state.error=9;return false;}
 const nonblocking=Memory.alloc(4);nonblocking.writeU32(1);ioctl(state.sock,0x8004667e|0,nonblocking);
 const addr=Memory.alloc(16);addr.writeByteArray(new Uint8Array(16));addr.writeU16(2);
 addr.add(2).writeU8(config.port>>8);addr.add(3).writeU8(config.port&255);addr.add(4).writeU32(inet(Memory.allocUtf8String(config.host)));
 const rc=connect(state.sock,addr,16);
 const option=Memory.alloc(4),len=Memory.alloc(4);len.writeS32(4);
 if((rc!==0 && !wait(state.sock,true,2000)) || getOption(state.sock,0xffff,0x1007,option,len)!==0 || option.readS32()!==0){shutdown(state);state.error=9;return false;}
 if(config.controlPort){
  try{
   let header='';const one=Memory.alloc(1);
   while(header.length<8192){if(!wait(state.sock,false,2000))throw Error('Serial open acknowledgement timed out');if(recv(state.sock,one,1,0)!==1)throw Error('Serial open refused');const c=one.readU8();if(c===10)break;header+=String.fromCharCode(c);}
   const response=JSON.parse(header);if(!response.ok)throw Error(response.error||'Serial open failed');
  }catch(e){send({event:'serial_open_error',reason:String(e)});shutdown(state);state.error=9;return false;}
 }
 state.error=0;const opened=baseOpen(obj,mode);send({event:'native_serial_open',opened:!!opened});return opened;
});
replace('?close@QSerialPort@@UEAAXXZ','void',['pointer'],(original,obj)=>{
 const state=objects.get(obj.toString());if(!state)return original(obj);shutdown(state);baseClose(obj);
});
replace('?readData@QSerialPort@@MEAA_JPEAD_J@Z','int64',['pointer','pointer','int64'],(original,obj,buf,n)=>{
 const state=objects.get(obj.toString());if(!state)return original(obj,buf,n);
 if(!state.sock)return -1;
 if(n.toNumber()===0)return 0;
 const got=recv(state.sock,buf,Math.min(n.toNumber(),1048576),0);
 if(got<0 && error()===10035)return 0;
 if(got<=0){state.error=9;shutdown(state);return -1;}wire("rx",buf,got);return got;
});
replace('?writeData@QSerialPort@@MEAA_JPEBD_J@Z','int64',['pointer','pointer','int64'],(original,obj,buf,n)=>{
 const state=objects.get(obj.toString());if(!state)return original(obj,buf,n);
 if(!state.sock)return -1;
 const size=n.toNumber();if(size===0)return 0;if(size<0 || size>16777216-state.pending){state.error=7;return -1;}
 wire("tx",buf,size);state.tx.push({data:buf.readByteArray(size),offset:0});state.pending+=size;
 return size;
});
replace('?bytesAvailable@QSerialPort@@UEBA_JXZ','int64',['pointer'],(original,obj)=>{
 const state=objects.get(obj.toString());return state?baseAvailable(obj).add(available(state)):original(obj);
});
const baseCanReadLine=fun(core,'?canReadLine@QIODevice@@UEBA_NXZ','bool',['pointer']);
replace('?canReadLine@QSerialPort@@UEBA_NXZ','bool',['pointer'],(original,obj)=>{
 const state=objects.get(obj.toString());if(!state)return original(obj);
 if(baseCanReadLine(obj))return true;
 const count=available(state);if(!state.sock || count===0)return false;
 const buffer=Memory.alloc(Math.min(count,1048576));
 const got=recv(state.sock,buffer,Math.min(count,1048576),2);
 if(got<=0)return false;
 const bytes=new Uint8Array(buffer.readByteArray(got));
 return bytes.indexOf(10)>=0;
});
replace('?bytesToWrite@QSerialPort@@UEBA_JXZ','int64',['pointer'],(original,obj)=>objects.has(obj.toString())?objects.get(obj.toString()).pending:original(obj));
replace('?waitForReadyRead@QSerialPort@@UEAA_NH@Z','bool',['pointer','int'],(original,obj,ms)=>{
 const state=objects.get(obj.toString());if(!state)return original(obj,ms);return !!state.sock && (available(state)>0 || wait(state.sock,false,Math.max(0,ms)));
});
replace('?waitForBytesWritten@QSerialPort@@UEAA_NH@Z','bool',['pointer','int'],(original,obj,ms)=>{
 const state=objects.get(obj.toString());if(!state)return original(obj,ms);
 if(!state.sock)return false;
 if(state.written>state.waited){state.waited=state.written;return true;}
 if(!state.pending || !wait(state.sock,true,Math.max(0,ms)))return false;
 const sent=flushPending(state);if(sent>0){state.waited=state.written;return true;}return false;
});
replace('?error@QSerialPort@@QEBA?AW4SerialPortError@1@XZ','int',['pointer'],(original,obj)=>objects.has(obj.toString())?objects.get(obj.toString()).error:original(obj));
replace('?clearError@QSerialPort@@QEAAXXZ','void',['pointer'],(original,obj)=>{const state=objects.get(obj.toString());if(state)state.error=0;else original(obj);});
replace('?flush@QSerialPort@@QEAA_NXZ','bool',['pointer'],(original,obj)=>objects.has(obj.toString())?flushPending(objects.get(obj.toString()))>=0:original(obj));
for(const [name,types] of [
 ['?setBaudRate@QSerialPort@@QEAA_NHV?$QFlags@W4Direction@QSerialPort@@@@@Z',['pointer','int','int']],
 ['?setDataBits@QSerialPort@@QEAA_NW4DataBits@1@@Z',['pointer','int']],
 ['?setParity@QSerialPort@@QEAA_NW4Parity@1@@Z',['pointer','int']],
 ['?setStopBits@QSerialPort@@QEAA_NW4StopBits@1@@Z',['pointer','int']],
 ['?setFlowControl@QSerialPort@@QEAA_NW4FlowControl@1@@Z',['pointer','int']]]){
 replace(name,'bool',types,(original,obj,...args)=>{
  const state=objects.get(obj.toString());if(!state)return original(obj,...args);
  const expected=name.indexOf('BaudRate')>=0?115200:name.indexOf('DataBits')>=0?8:name.indexOf('StopBits')>=0?1:0;
  if(args[0]!==expected){state.error=10;return false;}
  return state.sock?true:original(obj,...args);
 });
}

for(const [name,op] of [
 ['?setDataTerminalReady@QSerialPort@@QEAA_N_N@Z','dtr'],
 ['?setRequestToSend@QSerialPort@@QEAA_N_N@Z','rts']]){
 replace(name,'bool',['pointer','bool'],(original,obj,value)=>{
  const state=objects.get(obj.toString());if(!state)return original(obj,value);
  try{control({op:op,value:!!value});return true;}catch(e){state.error=9;send({event:'serial_control_error',operation:op,reason:String(e)});return false;}
 });
}
const readAll=fun(core,'?readAll@QIODevice@@QEAA?AVQByteArray@@XZ','pointer',['pointer','pointer']);
const destroyBytes=fun(core,'??1QByteArray@@QEAA@XZ','void',['pointer']);
replace('?clear@QSerialPort@@QEAA_NV?$QFlags@W4Direction@QSerialPort@@@@@Z','bool',['pointer','int'],(original,obj,direction)=>{
 const state=objects.get(obj.toString());if(!state)return original(obj,direction);
 try{
  if(direction&2){state.tx=[];state.pending=0;state.written=0;state.waited=0;}
  if(direction&1){const bytes=Memory.alloc(8);readAll(obj,bytes);destroyBytes(bytes);}
  control({op:'clear',direction:direction});return true;
 }catch(e){state.error=9;send({event:'serial_control_error',operation:'clear',reason:String(e)});return false;}
});

// Descriptor fields come from the physical USB metadata obtained through SSH.
const makeQString=fun(core,'??0QString@@QEAA@PEBD@Z','pointer',['pointer','pointer']);
const destroyQString=fun(core,'??1QString@@QEAA@XZ','void',['pointer']);
const infoFromPrivate=fun(serial,'??0QSerialPortInfo@@AEAA@AEBVQSerialPortInfoPrivate@@@Z','pointer',['pointer','pointer']);
const nativeMalloc=fun(Process.getModuleByName('ucrtbase.dll'),'malloc','pointer',['uint64']);
const listDetach=fun(core,'?detach@QListData@@QEAAPEAUData@1@H@Z','pointer',['pointer','int']);
const listAppend=fun(core,'?append@QListData@@QEAAPEAPEAXXZ','pointer',['pointer']);
replace('?availablePorts@QSerialPortInfo@@SA?AV?$QList@VQSerialPortInfo@@@@XZ','pointer',['pointer'],(original,out)=>{
 if(config && config.metadata){out.writePointer(core.getExportByName('?shared_null@QListData@@2UData@1@B'));listDetach(out,1);}else original(out);
 if(!config || !(config.fixtureDescriptor || config.metadata))return out;
 const d=Memory.alloc(48);d.writeByteArray(new Uint8Array(48));
 const m=config.metadata||{};
 const strings=['SonicPad_A1','SonicPad_A1',m.product_text||'Offline fixture',m.manufacturer_text||'Fixture only',m.serial_text||'OFFLINE'];
 try{
  for(let i=0;i<5;i++)makeQString(d.add(i*8),Memory.allocUtf8String(strings[i]));
  d.add(40).writeU16(0x303a);d.add(42).writeU16(0x4001);d.add(44).writeU8(1);d.add(45).writeU8(1);
  const node=listAppend(out);const info=nativeMalloc(8);infoFromPrivate(info,d);node.writePointer(info);
 }finally{for(let i=0;i<5;i++)destroyQString(d.add(i*8));}
 return out;
});

setInterval(()=>{
 timerTicks++;
 try{
 for(const state of objects.values()){
  if(state.pending)flushPending(state);
  const n=available(state);maxAvailable=Math.max(maxAvailable,n);
  if(state.sock && n===0 && wait(state.sock,false,0)){const peek=Memory.alloc(1);if(recv(state.sock,peek,1,2)===0){state.error=9;shutdown(state);emitQueued(state.obj,'errorOccurred',9,'QSerialPort::SerialPortError');}}
  if(state.sock && n>0 && Date.now()-state.lastSignal>30){state.lastSignal=Date.now();emitQueued(state.obj,'readyRead');}
 }
 }catch(e){send({event:'timer_error',stack:String(e.stack)});}
},10);
rpc.exports={configure(c){if(c.host!=='127.0.0.1')throw Error('SSH loopback transport required');if(c.metadata && (c.metadata.vendor!==0x303a || c.metadata.product!==0x4001))throw Error('Unsupported USB identity');config=c;return true;},stats(){return {remoteObjects:objects.size,timerTicks:timerTicks,maxAvailable:maxAvailable};}};
send({event:'serial_tcp_hooks_installed',scope:'localhost_transport'});

})();
