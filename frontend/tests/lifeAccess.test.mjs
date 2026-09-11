import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const source = name => readFileSync(new URL('../src/' + name, import.meta.url), 'utf8')
const route = source('router.js').split('router.beforeEach(async (to) => {')[1].split('\n})')[0]
const createGuard = auth => vm.runInNewContext('(async (to) => {' + route + '})', { useAuthStore: () => auth })
function createAuth(user) {
  const store = source('stores/auth.js').replace(/^import .*$/gm, '').replace('export const useAuthStore', 'const useAuthStore')
  return vm.runInNewContext(store + '\nuseAuthStore()', {
    computed: getter => ({ get value() { return getter() } }),
    ref: value => ({ value }),
    defineStore: (_, setup) => setup,
    localStorage: {
      getItem: key => ({
        wsw_token: 'test',
        wsw_user: JSON.stringify(user),
        wsw_auth_version: '5',
        wsw_login_at: String(Date.now()),
      }[key] ?? null),
      setItem() {},
      removeItem() {},
    },
    window: { addEventListener() {} },
  })
}

test('life navigation and page guards split player and manager permissions', () => {
  const nav = source('components/AppHeader.vue')
  assert.match(nav, /auth\.ready && auth\.isLoggedIn && auth\.canPlayLife" to="\/life"/)
  const app = source('App.vue')
  assert.match(app, /v-if="\(!route\.meta\.lifeOnly \|\| \(auth\.isLoggedIn && auth\.canPlayLife\)\) && \(!route\.meta\.lifeManager \|\| \(auth\.isLoggedIn && auth\.canManageRoles\)\)"/)
  assert.match(app, /route\.meta\.lifeOnly && \(!auth\.isLoggedIn \|\| !auth\.canPlayLife\)/)
  assert.match(app, /route\.meta\.lifeManager && \(!auth\.isLoggedIn \|\| !auth\.canManageRoles\)/)
  assert.match(app, /!route\.meta\.lifeOnly && !route\.meta\.lifeManager/)
  assert.doesNotMatch(app, /auth\.isAdmin/)
})
test('life-admin route uses the separate lifeManager guard', () => {
  const router = source('router.js')
  assert.match(router, /path: '\/life'.*meta: \{ lifeOnly: true \}/)
  assert.match(router, /path: '\/life-admin'.*meta: \{ lifeManager: true \}/)
  assert.match(source('views/LifeAdmin.vue'), /loadPacks/)
})
test('life routes refresh identity: any logged-in user may play, management stays staff-only', async () => {
  for (const role of ['user', 'volunteer', 'staff']) {
    for (const superAdmin of [false, true]) {
      for (const meta of [{ lifeOnly: true }, { lifeManager: true }]) {
        let restored = false
        const auth = { token: 'test', isLoggedIn: true, canManageRoles: false, canPlayLife: false, restore: async () => {
          restored = true
          auth.canManageRoles = superAdmin || role === 'staff'
          auth.canPlayLife = true // 登录即可玩
        } }
        const expected = meta.lifeOnly ? undefined : (superAdmin || role === 'staff' ? undefined : '/')
        assert.equal(await createGuard(auth)({ meta }), expected)
        assert.equal(restored, true)
      }
    }
  }
  for (const meta of [{ lifeOnly: true }, { lifeManager: true }]) {
    const guard = createGuard({ token: null, isLoggedIn: false, canPlayLife: true, canManageRoles: true, restore: () => assert.fail('must reject before identity fetch') })
    assert.equal(await guard({ meta }), '/')
  }
  for (const meta of [{ lifeOnly: true }, { lifeManager: true }]) {
    const auth = { token: 'test', isLoggedIn: false, canPlayLife: true, canManageRoles: true, restore: async () => {} }
    assert.equal(await createGuard(auth)({ meta }), '/')
  }
})
test('any logged-in user sees life navigation; beta flag is display-only and grants no management', () => {
  const condition = source('components/AppHeader.vue').match(/v-if="([^"]+)" to="\/life"/)[1]
  for (const beta of [false, true]) {
    const auth = createAuth({ role: 'user', is_admin: false, is_beta_tester: beta })
    assert.equal(auth.isBetaTester.value, beta)
    assert.equal(auth.canPlayLife.value, true)
    assert.equal(auth.canManageRoles.value, false)
    const unwrapped = Object.fromEntries(Object.entries(auth).map(([key, value]) => [key, value?.value]))
    unwrapped.ready = true
    assert.equal(vm.runInNewContext(condition, { auth: unwrapped }), true)
  }
})
test('logged-in users enter life regardless of beta flag, but not life-admin', async () => {
  for (const beta of [false, true]) {
    const auth = { token: 'test', isLoggedIn: true, canManageRoles: true, canPlayLife: true, restore: async () => {
      const store = createAuth({ role: 'user', is_beta_tester: beta })
      auth.canManageRoles = store.canManageRoles.value
      auth.canPlayLife = store.canPlayLife.value
    } }
    assert.equal(await createGuard(auth)({ meta: { lifeOnly: true } }), undefined)
    assert.equal(await createGuard(auth)({ meta: { lifeManager: true } }), '/')
  }
})
test('beta badge is read-only, while applications are available to eligible reviewers', () => {
  assert.match(source('views/ProfileView.vue'), /v-if="auth\.user\.is_beta_tester" class="role-tag beta-tag">内测用户/)
  assert.match(source('views/ProfileView.vue'), /api\.get\('\/beta-applications\/mine'\)/)
  assert.match(source('components/BetaApplyDialog.vue'), /api\.post\('\/beta-applications'/)
  const admin = source('views/AdminView.vue')
  assert.match(admin, /class="beta-toggle"><input type="checkbox" :checked="user\.is_beta_tester" :disabled="!auth\.isAdmin" @change="toggleBetaTester\(user\)" \/> 内测用户/)
  assert.match(admin, /api\.patch\(`\/admin\/users\/\$\{user\.id\}\/beta-tester`, \{ is_beta_tester: !user\.is_beta_tester \}\)/)
  assert.match(admin, /api\.post\(`\/admin\/beta-applications\/\$\{item\.id\}\/review`/)
  assert.match(source('views/OperationsView.vue'), /api\.post\(`\/operations\/beta-applications\/\$\{item\.id\}\/review`/)
})