import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { HALLS, visibleItems } from '../src/navigation.js'

const source = name => readFileSync(new URL('../src/' + name, import.meta.url), 'utf8')
const gamesHall = HALLS.find((hall) => hall.id === 'games')
const route = source('router.js').split('router.beforeEach(async (to) => {')[1].split('\n})')[0]
const createGuard = auth => {
  auth.hydrate ??= async () => {}
  return vm.runInNewContext('(async (to) => {' + route + '})', { useAuthStore: () => auth, SERVER_VERIFIED_META: ['lifeOnly', 'lifeManager', 'roleManager', 'moderator', 'operations'] })
}
async function createAuth(user, restore = true) {
  const store = source('stores/auth.js').replace(/^import .*$/gm, '').replace('export const useAuthStore', 'const useAuthStore')
  const auth = vm.runInNewContext(store + '\nuseAuthStore()', {
    computed: getter => ({ get value() { return getter() } }),
    ref: value => ({ value }),
    defineStore: (_, setup) => setup,
    AUTH_CACHE_VERSION: 'test', LOGIN_MAX_AGE_MS: 86400000, REMEMBER_MAX_AGE_MS: 604800000,
    loadAuth: async () => ({ token: 'test', user, loginAt: Date.now(), version: 'test' }),
    saveAuth: async () => {}, clearAuth: async () => {},
    api: { get: async () => ({ data: user }) },
    window: { addEventListener() {} },
  })
  await auth.hydrate()
  if (restore) await auth.restore()
  return auth
}

test('life navigation and page guards split player and manager permissions', () => {
  // 导航归属集中在 navigation.js：虚拟人生属于游戏大厅，且必须身份确认后才显示。
  assert.deepEqual(
    visibleItems(gamesHall, { ready: true, isLoggedIn: true, canPlayLife: true }).map((item) => item.to),
    ['/life', '/frost'],
  )
  assert.deepEqual(
    visibleItems(gamesHall, { ready: false, isLoggedIn: true, canPlayLife: true }).map((item) => item.to),
    ['/frost'],
  )
  assert.deepEqual(visibleItems(gamesHall, { ready: true, isLoggedIn: false, canPlayLife: false }), [])
  const app = source('App.vue')
  assert.match(app, /v-if="\(!route\.meta\.lifeOnly \|\| \(auth\.isLoggedIn && auth\.canPlayLife\)\) && \(!route\.meta\.lifeManager \|\| \(auth\.isLoggedIn && auth\.canManageRoles\)\)"/)
  assert.match(app, /route\.meta\.lifeOnly && \(!auth\.isLoggedIn \|\| !auth\.canPlayLife\)/)
  assert.match(app, /route\.meta\.lifeManager && \(!auth\.isLoggedIn \|\| !auth\.canManageRoles\)/)
  assert.match(app, /!route\.meta\.lifeOnly && !route\.meta\.lifeManager/)
  assert.doesNotMatch(app, /auth\.isAdmin/)
})
test('life-admin route uses the separate lifeManager guard', () => {
  const router = source('router.js')
  assert.match(router, /path: '\/life'.*meta: \{ lifeOnly: true[, }]/)
  assert.match(router, /path: '\/life-admin'.*meta: \{ lifeManager: true[, }]/)
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
test('any logged-in user sees life navigation; beta flag is display-only and grants no management', async () => {
  for (const beta of [false, true]) {
    const store = await createAuth({ role: 'user', is_admin: false, is_beta_tester: beta })
    assert.equal(store.isBetaTester.value, beta)
    assert.equal(store.canPlayLife.value, true)
    assert.equal(store.canManageRoles.value, false)
    const auth = { ready: true, isLoggedIn: store.isLoggedIn.value, canPlayLife: store.canPlayLife.value }
    // 内测标记不影响导航：所有登录用户都能看到虚拟人生。
    assert.deepEqual(visibleItems(gamesHall, auth).map((item) => item.to), ['/life', '/frost'])
  }
})
test('logged-in users enter life regardless of beta flag, but not life-admin', async () => {
  for (const beta of [false, true]) {
    const auth = { token: 'test', isLoggedIn: true, canManageRoles: true, canPlayLife: true, restore: async () => {
      const store = await createAuth({ role: 'user', is_beta_tester: beta })
      auth.canManageRoles = store.canManageRoles.value
      auth.canPlayLife = store.canPlayLife.value
    } }
    assert.equal(await createGuard(auth)({ meta: { lifeOnly: true } }), undefined)
    assert.equal(await createGuard(auth)({ meta: { lifeManager: true } }), '/')
  }
})
test('beta review stays in admin/operations only (profile/staff pages untouched)', () => {
  const admin = source('views/AdminView.vue')
  assert.match(admin, /class="beta-toggle"><input type="checkbox" :checked="user\.is_beta_tester" :disabled="!auth\.isAdmin" @change="toggleBetaTester\(user\)" \/> 内测用户/)
  assert.match(admin, /api\.patch\(`\/admin\/users\/\$\{user\.id\}\/beta-tester`, \{ is_beta_tester: !user\.is_beta_tester \}\)/)
  assert.match(admin, /api\.post\(`\/admin\/beta-applications\/\$\{item\.id\}\/review`/)
  assert.match(source('views/OperationsView.vue'), /api\.post\(`\/operations\/beta-applications\/\$\{item\.id\}\/review`/)
})

test('cached admin flags cannot grant authority before server restoration', async () => {
  const auth = await createAuth({ role: 'staff', is_admin: true, is_beta_tester: true }, false)
  assert.equal(auth.verified.value, false)
  assert.equal(auth.isAdmin.value, false)
  assert.equal(auth.canManageRoles.value, false)
  assert.equal(auth.isBetaTester.value, false)
  await auth.restore()
  assert.equal(auth.verified.value, true)
  assert.equal(auth.isAdmin.value, true)
})
