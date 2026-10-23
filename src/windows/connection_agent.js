(function(){
'use strict';
const core=Process.getModuleByName('Qt5Core.dll');
let patch=null,applied=false,expectedTree=null;
const held=[];
function copyReadable(target,source,size){
 const end=source.add(size);let at=source;
 while(at.compare(end)<0){
  const range=Process.findRangeByAddress(at);
  if(range && range.protection[0]==='r'){
   let limit=range.base.add(range.size);if(limit.compare(end)>0)limit=end;
   const count=limit.sub(at).toInt32();target.add(at.sub(source).toInt32()).writeByteArray(at.readByteArray(count));at=limit;
  }else at=at.and(ptr('0xfffffffffffff000')).add(4096);
 }
}
const address=core.getExportByName('?qRegisterResourceData@@YA_NHPEBE00@Z');
Interceptor.attach(address,{
 onEnter(args){
  if(!patch || !args[1].equals(expectedTree))return;
  const tree=Memory.alloc(patch.tree_size);tree.writeByteArray(args[1].readByteArray(patch.tree_size));
  const data=Memory.alloc(patch.data_size+patch.payload.length/2);
  copyReadable(data,args[3],patch.data_size);
  data.add(patch.data_size).writeByteArray(patch.payload.match(/../g).map(x=>parseInt(x,16)));
  const offset=tree.add(patch.node*22+10);offset.writeByteArray([(patch.data_size>>>24)&255,(patch.data_size>>>16)&255,(patch.data_size>>>8)&255,patch.data_size&255]);
  tree.add(patch.node*22+14).writeByteArray(patch.timestamp);
  args[1]=tree;args[3]=data;held.push(tree,data);applied=true;
  send({event:'sonic_connection_page_installed'});
 }
});
rpc.exports={configure(p){patch=p;expectedTree=p.tree_address?ptr(p.tree_address):Process.getModuleByName('FalconDesignSpace.exe').base.add(p.tree_rva);Interceptor.flush();return true;},stats(){return {applied:applied};}};
})();
