import test, { after } from 'node:test'
import assert from 'node:assert/strict'

// theme.js 在导入时就会落地到 <html>，所以每个用例都要先备好最小浏览器环境，
// 再用带唯一 query 的动态 import 拿一份全新实例（绕过模块缓存）。
// 'vue' 在 node 下解析到 runtime-dom，只要 createElement 等几个方法存在即可加载。
function stubElement() {
  const node = {
    style: {}, content: null, innerHTML: '', textContent: '', dataset: {},
    setAttribute() {}, removeAttribute() {}, appendChild() {}, removeChild() {},
    insertBefore() {}, cloneNode() { return stubElement() },
  }
  node.content = { firstChild: null }
  return node
}

function installEnv({ saved = {}, prefersDark = false, now = new Date(2026, 8, 21, 10, 0) } = {}) {
  const dataset = {}
  const store = new Map(Object.entries(saved))
  const listeners = []
  globalThis.document = {
    createElement: () => stubElement(),
    createElementNS: () => stubElement(),
    createTextNode: () => stubElement(),
    createComment: () => stubElement(),
    querySelector: () => null,
    documentElement: { dataset },
  }
  globalThis.localStorage = {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
  }
  globalThis.window = {
    matchMedia: () => ({
      matches: prefersDark,
      addEventListener: (type, handler) => listeners.push({ type, handler }),
    }),
  }
  globalThis.__now = now
  globalThis.__systemDark = prefersDark
  globalThis.__listeners = listeners
  return { dataset, store, listeners }
}

let seq = 0
const loaded = []

async function loadTheme() {
  seq += 1
  const instance = await import(`../src/composables/theme.js?case=${seq}`)
  loaded.push(instance)
  return instance
}

// auto 档会排一个到昼夜边界的定时器；本文件逐份实例化主题模块，
// 结束时统一停掉，否则 node --test 因句柄未释放而无法退出。
after(() => {
  for (const instance of loaded) instance.dispose()
})

// 冻结全局时钟：theme.js 内部按当前时间判定，判定类用例必须固定住时刻，
// 否则用例结果会随"什么时候跑测试"变化。
function freezeClock(fixed) {
  const realDate = globalThis.Date
  globalThis.Date = class extends realDate {
    constructor(...args) {
      if (args.length === 0) return new realDate(fixed.getTime())
      return new realDate(...args)
    }

    static now() { return fixed.getTime() }
  }
  return () => { globalThis.Date = realDate }
}

test('syncFromAccount 用账号上的偏好覆盖本地（登录/刷新后由 auth store 调用）', async () => {
  const restoreClock = freezeClock(new Date(2026, 8, 21, 14, 0))
  try {
    const { dataset, store } = installEnv({ saved: { 'yorozuya-theme': 'classic', 'yorozuya-mode': 'day' } })
    const m = await loadTheme()
    assert.equal(dataset.theme, 'classic')
    assert.equal(dataset.mode, 'day')

    // 账号里存的是像素风 + 保持夜间 → 本地被覆盖，并写回本地缓存
    const changed = m.syncFromAccount('pixel', 'night')
    assert.equal(changed, true)
    assert.equal(dataset.theme, 'pixel')
    assert.equal(dataset.mode, 'night')
    assert.equal(m.theme.value, 'pixel')
    assert.equal(m.modeSource.value, 'night')
    assert.equal(store.get('yorozuya-theme'), 'pixel')
    assert.equal(store.get('yorozuya-mode'), 'night')

    // 已经一致时不重复应用
    assert.equal(m.syncFromAccount('pixel', 'night'), false)

    // 账号没选过风格（theme_style 为 null）时不动本地；auto 档照常接受
    assert.equal(m.syncFromAccount(null, 'auto'), true)
    assert.equal(m.modeSource.value, 'auto')
    assert.equal(m.theme.value, 'pixel')
    assert.equal(m.syncFromAccount(undefined, undefined), false)

    // 非法值一律忽略，不写盘也不改状态
    assert.equal(m.syncFromAccount('neon', 'neon'), false)
    assert.equal(m.theme.value, 'pixel')
    assert.equal(m.modeSource.value, 'auto')
  } finally {
    restoreClock()
  }
})

test('applyThemeById 只接受合法风格（个人设置的单选直接指定风格）', async () => {
  installEnv({})
  const m = await loadTheme()

  m.applyThemeById('pixel')
  assert.equal(m.theme.value, 'pixel')
  m.applyThemeById('classic')
  assert.equal(m.theme.value, 'classic')
  m.applyThemeById('neon')
  assert.equal(m.theme.value, 'classic', '非法值应被忽略')

  m.setModeSource('day')
})

test('导入时就把风格与明暗写到 <html>，并只把风格落盘', async () => {
  const restoreClock = freezeClock(new Date(2026, 8, 21, 23, 0))
  try {
    const { dataset, store } = installEnv({ saved: { 'yorozuya-theme': 'pixel' } })
    const m = await loadTheme()

    assert.equal(dataset.theme, 'pixel', '存的风格应生效')
    assert.equal(dataset.mode, 'night', '23:00 导入应判定为夜间')
    assert.equal(m.modeSource.value, 'auto')
    assert.equal(store.get('yorozuya-theme'), 'pixel')
    assert.equal(store.has('yorozuya-mode'), false, 'auto 档不应把推导结果固化到本地')
  } finally {
    restoreClock()
  }
})

test('白天导入用日间，非法/缺失的存档回落到经典风 + 按时间切换', async () => {
  const restoreClock = freezeClock(new Date(2026, 8, 21, 14, 0))
  try {
    const { dataset } = installEnv({ saved: { 'yorozuya-theme': 'neon', 'yorozuya-mode': 'neon' } })
    const m = await loadTheme()

    assert.equal(dataset.theme, 'classic')
    assert.equal(dataset.mode, 'day')
    assert.equal(m.theme.value, 'classic')
    assert.equal(m.modeSource.value, 'auto')
  } finally {
    restoreClock()
  }
})

test('setModeSource 立即改 <html> 并落盘', async () => {
  const { dataset, store } = installEnv({ now: new Date(2026, 8, 21, 14, 0) })
  const m = await loadTheme()

  assert.equal(dataset.mode, 'day')

  m.setModeSource('night')
  await new Promise((resolve) => setTimeout(resolve, 0)) // 等 watch 冲刷
  assert.equal(dataset.mode, 'night')
  assert.equal(store.get('yorozuya-mode'), 'night')
  assert.equal(m.mode.value, 'night')

  m.setModeSource('day')
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.equal(dataset.mode, 'day')

  // 非法档位直接忽略，不改变现状
  m.setModeSource('neon')
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.equal(m.modeSource.value, 'day')
})

test('跟随系统档按系统偏好决定，并响应系统切换', async () => {
  const { dataset } = installEnv({ now: new Date(2026, 8, 21, 14, 0), prefersDark: true })
  const m = await loadTheme()

  m.setModeSource('system')
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.equal(dataset.mode, 'night', '系统偏好深色时应是夜间')

  // 系统偏好翻转后由 matchMedia 的 change 事件驱动
  assert.equal(globalThis.__listeners.length, 1)
  assert.equal(globalThis.__listeners[0].type, 'change')
  globalThis.__systemDark = false
  globalThis.window.matchMedia = () => ({ matches: false, addEventListener: () => {} })
  globalThis.__listeners[0].handler()
  assert.equal(dataset.mode, 'day')

  m.setModeSource('day')
})

// auto 档的排期时长由 themeMode.nextModeChangeIn 负责（tests/themeMode.test.mjs 已穷举），
// 定时器真正到点触发的行为在浏览器里验证——测试里拦截 setTimeout 会留下无法回收的
// 句柄（node --test 无法退出），收益不抵这份脆弱。
