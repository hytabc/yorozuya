import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { anchorPosition, blankRoom, clone, createHistory, editVoxels, normalizedVoxels, placementError, recoloredData, validateVoxelData } from '../src/house/engine.js'
import { createSaveController } from '../src/house/saveController.js'
import { draftOperation } from '../src/house/drafts.js'
const data = {gridSize:16,mount:'floor',palette:[{key:'wood',label:'木材',color:'#b58b63',editable:true},{key:'screen',label:'屏幕',color:'#263b43',editable:false}],voxels:[[0,0,0,0],[1,0,0,0]]}
const placement=(id,x,y,z=0)=>({id,versionId:'v1',position:{x,y,z},rotation:0,paletteOverrides:{}})

test('精确体素碰撞、紧贴、堆叠及旋转边界',()=>{
  const r=blankRoom(),assets={v1:{data}};r.placements=[placement('a',0,0),placement('b',2,0),placement('c',0,0,1)]
  assert.equal(placementError(r,assets),'')
  r.placements.push(placement('d',1,0));assert.match(placementError(r,assets),/重叠/)
  r.placements=[placement('a',255,0)];assert.match(placementError(r,assets),/边界/)
  r.placements[0].rotation=90;assert.equal(placementError(r,assets),'')
  assert.deepEqual(normalizedVoxels(data,270),[[0,1,0,0],[0,0,0,0]])
})
test('镜像绘制可添加、改色和删除，无重复体素',()=>{
  let copy=editVoxels(data,[2,3,4],'add',1,[0,1,2]);assert.equal(copy.voxels.length,10)
  copy=editVoxels(copy,[2,3,4],'paint',0,[0,1,2]);assert.equal(copy.voxels.filter((p)=>p[3]===1).length,0)
  copy=editVoxels(copy,[2,3,4],'delete',0,[0,1,2]);assert.deepEqual(copy.voxels,data.voxels)
  assert.deepEqual(data.voxels,[[0,0,0,0],[1,0,0,0]])
})
test('墙、顶、地面锚点和房间尺寸',()=>{
  assert.deepEqual(anchorPosition(data,{x:128,y:128,z:0}),{x:127,y:128,z:0})
  assert.equal(anchorPosition({...data,mount:'wall'},{x:100,y:80,z:0}).y,255)
  assert.equal(anchorPosition({...data,mount:'ceiling'},{x:100,y:80,z:0}).z,127)
  assert.deepEqual(anchorPosition(data,{x:999,y:-100,z:999}),{x:254,y:0,z:127})
})
test('单实例改色保留固定部位，模板不改变；撤销重做独立快照',()=>{
  const original=clone(data),copy=recoloredData(data,{wood:'#a6bbc5',screen:'#ff0000'})
  assert.equal(copy.palette[0].color,'#a6bbc5');assert.equal(copy.palette[1].color,'#263b43');assert.deepEqual(data,original)
  const history=createHistory();history.push(data);assert.deepEqual(history.undo(copy),data);assert.deepEqual(history.redo(data),copy)
})
test('JSON 导入验证64网格、非法坐标、重复项、色板索引和布尔坐标',()=>{
  assert.doesNotThrow(()=>validateVoxelData({...data,gridSize:64,voxels:[[63,63,63,0]]}))
  for(const voxels of [[[16,0,0,0]],[[0,0,0,0],[0,0,0,1]],[[0,0,0,99]],[[true,0,0,0]]])assert.throws(()=>validateVoxelData({...data,voxels}))
  assert.throws(()=>validateVoxelData({...data,palette:[{...data.palette[0],color:'red'}]}))
})
test('大型体素撤销历史遵守内存预算，同时保留最近一步',()=>{
  const history=createHistory(30,80)
  history.push({name:'old',text:'x'.repeat(40)})
  history.push({name:'recent',text:'y'.repeat(40)})
  assert.equal(history.undo({name:'current'}).name,'recent')
  assert.equal(history.undo({name:'recent'}),null)
  assert.equal(history.redo({name:'recent'}).name,'current')
})
test('云端保存串行处理编辑期间的新变化',async()=>{
  let state=1,calls=[],resolveFirst,local=[],status
  const s=createSaveController({ownerValid:()=>true,snapshot:()=>state,writeCloud:async(p)=>{calls.push(p);if(calls.length===1)await new Promise(r=>resolveFirst=r);return {revision:p.revision+1}},writeLocal:async(d)=>local.push(d),removeLocal:async()=>{local=[]},onStatus:(v)=>status=v,delay:10000})
  s.reset(3);s.changed();const saving=s.flush();state=2;s.changed();resolveFirst();assert.equal(await saving,true)
  assert.deepEqual(calls,[{revision:3,state:1},{revision:4,state:2}]);assert.equal(s.dirty,false);assert.equal(status.saving,false);assert.equal(local.length,0);s.dispose()
})
test('409 保留草稿且停止自动覆盖',async()=>{
  let count=0,local
  const s=createSaveController({ownerValid:()=>true,snapshot:()=>({name:'draft'}),writeCloud:async()=>{count++;throw {response:{status:409}}},writeLocal:async(d)=>{local=d},removeLocal:async()=>assert.fail('不能删除冲突草稿'),onStatus:()=>{},delay:10000})
  s.reset(2);s.changed();assert.equal(await s.flush(),false);assert.equal(s.conflict,true);assert.equal(local.state.name,'draft');assert.equal(await s.flush(),false);assert.equal(count,1);s.dispose()
})
test('账号变更禁止旧页面写入云端或本地',async()=>{
  let valid=true,count=0
  const s=createSaveController({ownerValid:()=>valid,snapshot:()=>1,writeCloud:async()=>{count++;return {revision:1}},writeLocal:async()=>{},removeLocal:async()=>{},onStatus:()=>{},delay:10000})
  s.changed();valid=false;assert.equal(await s.flush(),false);assert.equal(count,0);s.dispose()
})
test('IndexedDB 草稿以账号和工坊类型隔离',async()=>{
  const values=new Map()
  globalThis.indexedDB={open(){const request={};setTimeout(()=>{request.result={transaction(){const tx={};const op=(run)=>{const q={};setTimeout(()=>{q.result=run();q.onsuccess?.();tx.oncomplete?.()},0);return q};tx.objectStore=()=>({put:(v,k)=>op(()=>values.set(k,v)),get:(k)=>op(()=>values.get(k)),delete:(k)=>op(()=>values.delete(k))});return tx}};request.onsuccess()},0);return request}}
  await draftOperation(1,'room','put',{name:'one'});await draftOperation(2,'room','put',{name:'two'});await draftOperation(1,'workshop','put',{name:'furniture'})
  assert.equal((await draftOperation(1,'room','get')).name,'one');assert.equal((await draftOperation(2,'room','get')).name,'two');assert.equal((await draftOperation(1,'workshop','get')).name,'furniture')
  await draftOperation(1,'room','delete');assert.equal(await draftOperation(1,'room','get'),undefined);assert.equal((await draftOperation(2,'room','get')).name,'two')
})
test('两层代理只为房屋数据和纹理放宽请求上限',()=>{
  for(const path of ['../nginx.conf','../../deploy/nginx/edge.conf.template']){
    const conf=fs.readFileSync(new URL(path,import.meta.url),'utf8')
    assert.match(conf,/location ~ \^\/api\/house\/furniture\/\[\^\/\]\+\$ \{\s*client_max_body_size 8m;/)
    assert.match(conf,/location = \/api\/house\/textures \{\s*client_max_body_size 11m;/)
    assert.match(conf,/proxy_request_buffering off/);assert.match(conf,/X-Real-IP/)
  }
})
