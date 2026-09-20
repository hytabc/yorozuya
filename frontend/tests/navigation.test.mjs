import test from 'node:test'
import assert from 'node:assert/strict'
import { HALLS, MORE_LINKS, hallContainsPath, moreLinks, visibleItems } from '../src/navigation.js'

// navigation.js 是纯数据，这里用假的 auth 视图直接验证「谁能看到哪个大厅」。
const guest = { ready: true, isLoggedIn: false, canPlayLife: false, canModerate: false, canOperate: false }
const member = { ready: true, isLoggedIn: true, canPlayLife: true, canModerate: false, canOperate: false }

const visibleHalls = (auth) => HALLS.filter((hall) => visibleItems(hall, auth).length)
const hallBy = (id) => HALLS.find((hall) => hall.id === id)
const pathsOf = (id, auth) => visibleItems(hallBy(id), auth).map((item) => item.to)

test('六个大厅覆盖全部页面，且 key 唯一', () => {
  assert.deepEqual(HALLS.map((hall) => hall.id), ['tasks', 'talk', 'games', 'share', 'social', 'official'])
  const allPaths = HALLS.flatMap((hall) => hall.items.map((item) => item.to))
  assert.equal(new Set(allPaths).size, allPaths.length)
  for (const path of ['/', '/board', '/talk', '/life', '/frost', '/stories', '/maps', '/friends', '/sugar', '/staff', '/announcements', '/versions', '/mine']) {
    assert.ok(allPaths.includes(path), `${path} 应属于某个大厅`)
  }
})

test('游客只看得到公开大厅，且单条大厅只暴露该条目', () => {
  assert.deepEqual(visibleHalls(guest).map((hall) => hall.id), ['tasks', 'talk', 'share', 'official'])
  assert.deepEqual(pathsOf('tasks', guest), ['/'])
  assert.deepEqual(pathsOf('talk', guest), ['/board', '/talk'])
  assert.deepEqual(pathsOf('share', guest), ['/maps'])
  assert.deepEqual(pathsOf('official', guest), ['/staff', '/announcements', '/versions'])
})

test('登录用户看到全部六个大厅及其条目', () => {
  assert.deepEqual(visibleHalls(member).map((hall) => hall.id), ['tasks', 'talk', 'games', 'share', 'social', 'official'])
  assert.deepEqual(pathsOf('tasks', member), ['/', '/mine'])
  assert.deepEqual(pathsOf('games', member), ['/life', '/frost'])
  assert.deepEqual(pathsOf('social', member), ['/friends', '/sugar'])
})

test('「更多」只放管理入口，并按角色显隐', () => {
  assert.deepEqual(moreLinks(guest), [])
  assert.deepEqual(moreLinks(member), [])
  assert.deepEqual(moreLinks({ canModerate: true, canOperate: true }).map((link) => link.to), ['/admin', '/operations'])
  // 风纪委员只能进审核台，看板娘只能进运营台。
  assert.deepEqual(moreLinks({ canModerate: true, canOperate: false }).map((link) => link.to), ['/admin'])
  assert.deepEqual(moreLinks({ canModerate: false, canOperate: true }).map((link) => link.to), ['/operations'])
  assert.equal(MORE_LINKS.length, 2)
})

test('大厅高亮按当前路由命中任一子项', () => {
  assert.equal(hallContainsPath(hallBy('talk'), '/talk'), true)
  assert.equal(hallContainsPath(hallBy('talk'), '/board'), true)
  assert.equal(hallContainsPath(hallBy('talk'), '/maps'), false)
  assert.equal(hallContainsPath(hallBy('official'), '/versions'), true)
})

test('虚拟人生必须等身份确认（ready）后才出现在导航里', () => {
  assert.deepEqual(pathsOf('games', { ready: false, isLoggedIn: true, canPlayLife: true }), ['/frost'])
  assert.deepEqual(pathsOf('games', { ready: true, isLoggedIn: true, canPlayLife: true }), ['/life', '/frost'])
  assert.deepEqual(pathsOf('games', { ready: true, isLoggedIn: false, canPlayLife: false }), [])
})
