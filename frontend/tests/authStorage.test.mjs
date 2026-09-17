// 登录凭证本地存储的回归：任何路径下都不能留下旧版明文键（wsw_token / wsw_user 等）。
//
// 关键场景是「非安全上下文」（纯 HTTP 非 localhost）：此时 isPersistent() 为 false，
// 只会把凭证留在内存。早期实现把 removeLegacy() 放在提前 return 之后，
// 结果从旧版明文缓存迁移过来时会原样留着明文 JWT —— 这个用例锁住该行为。
import assert from 'node:assert/strict'
import test from 'node:test'

const LEGACY_KEYS = ['wsw_token', 'wsw_user', 'wsw_auth_version', 'wsw_login_at']

function installStorage() {
  const store = new Map()
  globalThis.localStorage = {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => { store.set(key, String(value)) },
    removeItem: (key) => { store.delete(key) },
    clear: () => store.clear(),
    key: (index) => [...store.keys()][index] ?? null,
    get length() { return store.size },
  }
  // Node 里没有 indexedDB，因此 isPersistent() 恒为 false —— 正是要覆盖的降级分支。
  delete globalThis.indexedDB
  return store
}

function seedLegacy(store) {
  store.set('wsw_auth_version', '5')
  store.set('wsw_token', 'legacy-token')
  store.set('wsw_user', JSON.stringify({ id: 1, nickname: '旧用户' }))
  store.set('wsw_login_at', String(Date.now()))
}

function assertNoPlaintext(store) {
  for (const key of LEGACY_KEYS) {
    assert.equal(store.has(key), false, `${key} 不应留在 localStorage`)
  }
}

test('迁移旧版明文缓存后立即清除明文键', async () => {
  const store = installStorage()
  seedLegacy(store)
  // 每次带不同 query 动态导入，拿到互不共享模块级状态（cache/hydrated）的新实例。
  const auth = await import('../src/authStorage.js?case=legacy-migration')

  const loaded = await auth.loadAuth()

  assert.equal(loaded.token, 'legacy-token')
  assertNoPlaintext(store)
})

test('非安全上下文保存新凭证时不落盘、也不留明文键', async () => {
  const store = installStorage()
  store.set('wsw_token', 'stale-plaintext')
  const auth = await import('../src/authStorage.js?case=save-non-secure')

  await auth.saveAuth({ token: 'fresh-token', user: { id: 2 }, remember: false })

  assert.equal(auth.getTokenSync(), 'fresh-token')
  assertNoPlaintext(store)
  // 非安全上下文只留内存：既不能写明文，也不能写自己解不开的密文。
  assert.equal(store.has('wsw_auth'), false)
})

test('清除凭证时同时清掉明文键与加密缓存', async () => {
  const store = installStorage()
  seedLegacy(store)
  store.set('wsw_auth', '{"v":"7","iv":"x","data":"y"}')
  store.set('wsw_auth_format', '7')
  const auth = await import('../src/authStorage.js?case=clear')

  await auth.clearAuth()

  assertNoPlaintext(store)
  assert.equal(store.has('wsw_auth'), false)
  assert.equal(store.has('wsw_auth_format'), false)
})
