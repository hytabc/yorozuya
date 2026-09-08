import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const source = name => readFileSync(new URL('../src/' + name, import.meta.url), 'utf8')
test('life navigation and page guards share existing role-manager permission, retain desktop gate', () => {
  const nav = source('components/AppHeader.vue')
  assert.match(nav, /auth\.ready && auth\.isLoggedIn && auth\.canManageRoles && lifeDesktop" to="\/life"/)
  const app = source('App.vue')
  assert.match(app, /auth\.isLoggedIn && auth\.canManageRoles && lifeDesktop/)
  assert.match(app, /!auth\.canManageRoles \|\| !lifeDesktop\.value/)
  assert.doesNotMatch(app, /auth\.isAdmin/)
})
test('life route refreshes identity and allows staff or superadmin, not other roles or mobile', async () => {
  const route = source('router.js').split('router.beforeEach(async (to) => {')[1].split('\n})')[0]
  for (const role of ['user', 'volunteer', 'staff']) {
    for (const superAdmin of [false, true]) {
      let restored = false
      const auth = { token:'test', isLoggedIn:true, canManageRoles:false, restore:async () => { restored = true; auth.canManageRoles = superAdmin || role === 'staff' } }
      const guard = vm.runInNewContext('(async (to) => {' + route + '})', { useAuthStore:() => auth, isLifeDesktop:() => true })
      assert.equal(await guard({meta:{lifeOnly:true}}), superAdmin || role === 'staff' ? undefined : '/')
      assert.equal(restored, true)
    }
  }
  for (const [desktop, token] of [[false,'test'],[true,null]]) {
    const guard = vm.runInNewContext('(async (to) => {' + route + '})', { useAuthStore:() => ({token, restore:() => assert.fail('must reject before identity fetch')}), isLifeDesktop:() => desktop })
    assert.equal(await guard({meta:{lifeOnly:true}}), '/')
  }
})
