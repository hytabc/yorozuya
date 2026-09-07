import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import assert from 'node:assert/strict'
import test from 'node:test'

const source = readFileSync(new URL('../src/composables/lifeSave.js', import.meta.url), 'utf8')
  .replace(/^import .*$/gm, '').replace('export function', 'function') + '\nglobalThis.factory = useLifeSave;'

function setup(put = async () => ({data:{revision:1,updatedAt:'now'}})) {
  let mounted, leave, unmount, token = 'owner-A', configuration
  const calls = []
  const context = vm.createContext({
    ref: value => ({value}), setTimeout, clearTimeout,
    onMounted: fn => { mounted=fn }, onBeforeUnmount: fn => { unmount=fn },
    onBeforeRouteLeave: fn => { leave=fn },
    localStorage: {getItem:()=>token},
    window: {addEventListener(){},removeEventListener(){},confirm:()=>false},
    axios:{create: config => {configuration=config; return {
      get: async()=>({data:{revision:0,state:null,updatedAt:null}}),
      put: async (url, payload)=>{calls.push(payload);return put(payload)},
    }}},
  })
  vm.runInContext(source, context)
  const result = context.factory(()=>({day:7}), ()=>{})
  return {result, calls, config:()=>configuration, switchOwner:()=>{token='owner-B'}, mount:()=>mounted(), unmount:()=>unmount(), leave:()=>leave()}
}

test('captures owner token and refuses new-account dispatch', async()=>{
  const s=setup()
  await s.result.load()
  assert.equal(s.config().headers.Authorization,'Bearer owner-A')
  s.result.changed()
  s.switchOwner()
  assert.equal(await s.result.flush(),false)
  assert.equal(s.calls.length,0)
  assert.equal(s.result.ready.value,false)
  s.unmount()
})

test('serial drain preserves edits arriving during in-flight save', async()=>{
  let release
  const s=setup(async payload=>{
    if (payload.revision===0) await new Promise(resolve=>{release=resolve})
    return {data:{revision:payload.revision+1,updatedAt:'now'}}
  })
  await s.result.load()
  s.result.changed()
  const saving=s.result.flush()
  s.result.changed()
  release()
  assert.equal(await saving,true)
  assert.deepEqual(s.calls.map(c=>c.revision),[0,1])
  assert.equal(s.result.dirty.value,false)
  s.unmount()
})

test('conflict retains dirty state without overwriting', async()=>{
  const s=setup(async()=>{throw {response:{status:409}}})
  await s.result.load()
  s.result.changed()
  assert.equal(await s.result.flush(),false)
  assert.equal(s.result.conflict.value,true)
  assert.equal(s.result.dirty.value,true)
  assert.equal(await s.result.flush(),false)
  assert.equal(s.calls.length,1)
  s.unmount()
})
