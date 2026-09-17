import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import assert from 'node:assert/strict'
import test from 'node:test'

for (const [path, factory] of [['composables/lifeSave.js', 'useLifeSave'], ['frost/frostSave.js', 'useFrostSave']]) {
  const source = readFileSync(new URL('../src/' + path, import.meta.url), 'utf8')
    .replace(/^import .*$/gm, '').replace('export function', 'function') + '\nglobalThis.factory = ' + factory + ';'

  function setup(put = async () => ({ data: { revision: 1, updatedAt: 'now' } })) {
    let mounted, leave, unmount, token = 'owner-A', beforeReadToken, interceptor, lastRequest
    const calls = []
    async function dispatch() {
      lastRequest = await interceptor({ headers: {} })
    }
    const context = vm.createContext({
      ref: value => ({ value }), setTimeout, clearTimeout,
      onMounted: fn => { mounted = fn }, onBeforeUnmount: fn => { unmount = fn },
      onBeforeRouteLeave: fn => { leave = fn },
      getTokenSync: () => token,
      getToken: async () => { await beforeReadToken?.(); return token },
      window: { addEventListener() {}, removeEventListener() {}, confirm: () => false },
      axios: { create: () => ({
        interceptors: { request: { use(fn) { interceptor = fn } } },
        get: async () => { await dispatch(); return { data: { revision: 0, state: null, updatedAt: null } } },
        put: async (url, payload) => { await dispatch(); calls.push(payload); return put(payload) },
      }) },
    })
    vm.runInContext(source, context)
    const result = context.factory(() => ({ day: 7 }), () => {})
    return {
      result, calls, config: () => lastRequest,
      switchOwner: () => { token = 'owner-B' },
      onTokenRead: fn => { beforeReadToken = fn },
      mount: () => mounted(), unmount: () => unmount(), leave: () => leave(),
    }
  }

  test(factory + ': captures owner and refuses new-account dispatch', async () => {
    const s = setup()
    await s.result.load()
    assert.equal(s.config().headers.Authorization, 'Bearer owner-A')
    s.result.changed()
    s.switchOwner()
    assert.equal(await s.result.flush(), false)
    assert.equal(s.calls.length, 0)
    assert.equal(s.result.ready.value, false)
    s.unmount()
  })

  test(factory + ': blocks account switch during asynchronous token lookup', async () => {
    const s = setup()
    await s.result.load()
    s.result.changed()
    s.onTokenRead(() => s.switchOwner())
    assert.equal(await s.result.flush(), false)
    assert.equal(s.calls.length, 0)
    assert.equal(s.result.ready.value, false)
    s.unmount()
  })

  test(factory + ': serial drain preserves edits arriving during in-flight save', async () => {
    let release, started
    const inFlight = new Promise(resolve => { started = resolve })
    const s = setup(async payload => {
      if (payload.revision === 0) {
        started()
        await new Promise(resolve => { release = resolve })
      }
      return { data: { revision: payload.revision + 1, updatedAt: 'now' } }
    })
    await s.result.load()
    s.result.changed()
    const saving = s.result.flush()
    await inFlight
    s.result.changed()
    release()
    assert.equal(await saving, true)
    assert.deepEqual(s.calls.map(c => c.revision), [0, 1])
    assert.equal(s.result.dirty.value, false)
    s.unmount()
  })

  test(factory + ': conflict retains dirty state without overwriting', async () => {
    const s = setup(async () => { throw { response: { status: 409 } } })
    await s.result.load()
    s.result.changed()
    assert.equal(await s.result.flush(), false)
    assert.equal(s.result.conflict.value, true)
    assert.equal(s.result.dirty.value, true)
    assert.equal(await s.result.flush(), false)
    assert.equal(s.calls.length, 1)
    s.unmount()
  })
}
