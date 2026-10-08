import test from 'node:test'
import assert from 'node:assert/strict'
import { saveAuth, getTokenSync } from '../src/authStorage.js'
import { ownedClient } from '../src/house/client.js'

function storage() {
  const values=new Map(),keys=new Map()
  globalThis.localStorage={getItem:(k)=>values.get(k)||null,setItem:(k,v)=>values.set(k,String(v)),removeItem:(k)=>values.delete(k)}
  globalThis.window=new EventTarget()
  globalThis.indexedDB={open(){const request={};queueMicrotask(()=>{
    request.result={objectStoreNames:{contains:()=>true},transaction(){
      const tx={};const operation=(run)=>{const r={};queueMicrotask(()=>{r.result=run();r.onsuccess?.();tx.oncomplete?.()});return r}
      tx.objectStore=()=>({get:(k)=>operation(()=>keys.get(k)),put:(v,k)=>operation(()=>keys.set(k,v))});return tx
    }};request.onsuccess()
  });return request}}
  return values
}

test('固定 ownerToken，不同标签页换账号后请求不能到达适配器',async()=>{
  storage();await saveAuth({token:'owner-token',user:{id:1}})
  const editor=ownedClient();let writes=0
  editor.client.defaults.adapter=async(config)=>{writes++;return {status:200,data:{},headers:{},config}}
  const other=await import('../src/authStorage.js?case=other-house-tab')
  await other.saveAuth({token:'different-account-token',user:{id:2}})
  assert.equal(getTokenSync(),'owner-token')
  await assert.rejects(editor.client.put('/house/room',{revision:1,state:{}}),/登录身份已变更/)
  assert.equal(writes,0);assert.equal(editor.ownerValid(),false);editor.dispose()
})

test('相同账号的加密缓存刷新不阻止保存，Bearer 仍固定原令牌',async()=>{
  // Reuse the IDB key; neither tab can export the CryptoKey.
  await saveAuth({token:'same-owner-token',user:{id:1}})
  const editor=ownedClient();let authorization
  editor.client.defaults.adapter=async(config)=>{authorization=config.headers.Authorization;return {status:200,data:{},headers:{},config}}
  const other=await import('../src/authStorage.js?case=same-house-tab')
  await other.saveAuth({token:'same-owner-token',user:{id:1,nickname:'新昵称'}})
  await editor.client.put('/house/room',{revision:1,state:{}})
  assert.equal(authorization,'Bearer same-owner-token');assert.equal(editor.ownerValid(),true);editor.dispose()
})
