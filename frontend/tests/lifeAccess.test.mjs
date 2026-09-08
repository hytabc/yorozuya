import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const source = name => readFileSync(new URL('../src/' + name, import.meta.url), 'utf8')
const route = source('router.js').split('router.beforeEach(async (to) => {')[1].split('\n})')[0]
const createGuard = (auth, desktop = true) => vm.runInNewContext('(async (to) => {' + route + '})', { useAuthStore: () => auth, isLifeDesktop: () => desktop })
function createAuth(user) {
  const store = source('stores/auth.js').replace(/^import .*$/gm, '').replace('export const useAuthStore', 'const useAuthStore')
  return vm.runInNewContext(store + '\nuseAuthStore()', {
    computed: getter => ({ get value() { return getter() } }),
    ref: value => ({ value }),
    defineStore: (_, setup) => setup,
    localStorage: { getItem: key => key === 'wsw_token' ? 'test' : JSON.stringify(user) },
    window: { addEventListener() {} },
  })
}

test('life navigation and page guards split player and manager permissions, retain desktop gate', () => {
  const nav = source('components/AppHeader.vue')
  assert.match(nav, /auth\.ready && auth\.isLoggedIn && auth\.canPlayLife && lifeDesktop" to="\/life"/)
  const app = source('App.vue')
  assert.match(app, /auth\.isLoggedIn && auth\.canPlayLife && lifeDesktop/)
  assert.match(app, /route\.meta\.lifeOnly && \(!auth\.isLoggedIn \|\| !auth\.canPlayLife \|\| !lifeDesktop\.value\)/)
  assert.match(app, /route\.meta\.lifeManager && \(!auth\.isLoggedIn \|\| !auth\.canManageRoles \|\| !lifeDesktop\.value\)/)
  assert.match(app, /!route\.meta\.lifeManager \|\| \(auth\.isLoggedIn && auth\.canManageRoles && lifeDesktop\)/)
  assert.doesNotMatch(app, /auth\.isAdmin/)
})
test('life-admin route uses the separate lifeManager guard', () => {
  const router = source('router.js')
  assert.match(router, /path: '\/life'.*meta: \{ lifeOnly: true \}/)
  assert.match(router, /path: '\/life-admin'.*meta: \{ lifeManager: true \}/)
  assert.match(source('views/LifeAdmin.vue'), /loadPacks/)
  assert.match(source('views/LifeSimulator.vue'), /<button v-if="auth\.canManageRoles" title="内容管理"/)
})
test('life routes refresh identity and allow staff or superadmin, not other roles or mobile', async () => {
  for (const role of ['user', 'volunteer', 'staff']) {
    for (const superAdmin of [false, true]) {
      for (const meta of [{ lifeOnly: true }, { lifeManager: true }]) {
        let restored = false
        const auth = { token: 'test', isLoggedIn: true, canManageRoles: false, canPlayLife: false, restore: async () => {
          restored = true
          auth.canManageRoles = auth.canPlayLife = superAdmin || role === 'staff'
        } }
        assert.equal(await createGuard(auth)({ meta }), superAdmin || role === 'staff' ? undefined : '/')
        assert.equal(restored, true)
      }
    }
  }
  for (const [desktop, token] of [[false, 'test'], [true, null]]) {
    for (const meta of [{ lifeOnly: true }, { lifeManager: true }]) {
      const guard = createGuard({ token, restore: () => assert.fail('must reject before identity fetch') }, desktop)
      assert.equal(await guard({ meta }), '/')
    }
  }
})
test('beta identity exposes life navigation without granting management', () => {
  const condition = source('components/AppHeader.vue').match(/v-if="([^"]+)" to="\/life"/)[1]
  for (const beta of [false, true]) {
    const auth = createAuth({ role: 'user', is_admin: false, is_beta_tester: beta })
    assert.equal(auth.isBetaTester.value, beta)
    assert.equal(auth.canPlayLife.value, beta)
    assert.equal(auth.canManageRoles.value, false)
    const unwrapped = Object.fromEntries(Object.entries(auth).map(([key, value]) => [key, value?.value]))
    unwrapped.ready = true
    assert.equal(vm.runInNewContext(condition, { auth: unwrapped, lifeDesktop: true }), beta)
    assert.equal(vm.runInNewContext(condition, { auth: unwrapped, lifeDesktop: false }), false)
  }
})
test('beta users may enter life but not life-admin, and revoked cached access is rejected', async () => {
  for (const beta of [false, true]) {
    const auth = { token: 'test', isLoggedIn: true, canManageRoles: true, canPlayLife: true, restore: async () => {
      const store = createAuth({ role: 'user', is_beta_tester: beta })
      auth.canManageRoles = store.canManageRoles.value
      auth.canPlayLife = store.canPlayLife.value
    } }
    assert.equal(await createGuard(auth)({ meta: { lifeOnly: true } }), beta ? undefined : '/')
    assert.equal(await createGuard(auth)({ meta: { lifeManager: true } }), '/')
  }
})
test('beta badge is read-only and beta management is restricted to admins', () => {
  assert.match(source('views/ProfileView.vue'), /v-if="auth\.user\.is_beta_tester" class="role-tag beta-tag">内测用户/)
  const admin = source('views/AdminView.vue')
  assert.match(admin, /<th v-if="auth\.isAdmin">内测<\/th>/)
  assert.match(admin, /if \(!auth\.isAdmin \|\| user\.is_admin/)
  assert.match(admin, /api\.patch\(`\/admin\/users\/\$\{user\.id\}\/beta-tester`, \{ is_beta_tester: !user\.is_beta_tester \}\)/)
})
