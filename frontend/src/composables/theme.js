import { ref, watch } from 'vue'
import { MODE_SOURCES, isValidModeSource, nextModeChangeIn, resolveMode } from './themeMode.js'

const THEME_KEY = 'yorozuya-theme'
const MODE_KEY = 'yorozuya-mode'

// 纯逻辑（时间窗口、档位表）在 themeMode.js，本文件负责响应式状态与落地到 <html>：
// data-theme（classic|pixel）决定"长什么样"，data-mode（day|night）决定"亮还是暗"，
// 夜间样式集中在 night.css，不需要为两个风格各复制一套。
export { MODE_SOURCES, NIGHT_START_HOUR, NIGHT_END_HOUR, isNightTime } from './themeMode.js'

export const THEMES = [
  { id: 'classic', label: '经典风' },
  { id: 'pixel', label: '像素风' },
]

function prefersDark() {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  } catch {
    return false
  }
}

// auto 之外的三档都存在本地；读不到或值非法时回落到"根据时间切换"。
function initialModeSource() {
  try {
    const saved = localStorage.getItem(MODE_KEY)
    if (isValidModeSource(saved)) return saved
  } catch { /* 无痕模式等场景读不到 localStorage 时用默认值 */ }
  return 'auto'
}

function initialTheme() {
  try {
    const saved = localStorage.getItem(THEME_KEY)
    if (THEMES.some((t) => t.id === saved)) return saved
  } catch { /* 无痕模式等场景读不到 localStorage 时退回经典风 */ }
  return 'classic'
}

export const theme = ref(initialTheme())
export const modeSource = ref(initialModeSource())

function currentMode() {
  return resolveMode(modeSource.value, { systemPrefersDark: prefersDark() })
}

// 实际生效的明暗。auto 档按时间或系统偏好推导，其余档就是用户选的那个。
export const mode = ref(currentMode())

function applyTheme(id) {
  theme.value = id
  document.documentElement.dataset.theme = id
  try { localStorage.setItem(THEME_KEY, id) } catch { /* 写入失败不影响本次切换 */ }
}

function applyMode(id) {
  mode.value = id
  document.documentElement.dataset.mode = id
}

// 每次重新判定都覆盖 dataset，所以 auto 档不需要把推导结果写进 localStorage——
// 时间过去后重新打开页面依然按当时的时间判定。
function applyResolved() {
  applyMode(currentMode())
}

export function cycleTheme() {
  const idx = THEMES.findIndex((t) => t.id === theme.value)
  applyTheme(THEMES[(idx + 1) % THEMES.length].id)
}

// 直接选中某个风格（个人设置的「外观」用它，悬浮按钮用 cycleTheme）。
export function applyThemeById(id) {
  if (!THEMES.some((t) => t.id === id)) return
  applyTheme(id)
}

// 只写用户显式选择的档位；auto 档不落盘（避免把推导结果固化）。
export function setModeSource(id) {
  if (!isValidModeSource(id)) return
  modeSource.value = id
  try { localStorage.setItem(MODE_KEY, id) } catch { /* 写入失败不影响本次切换 */ }
  applyResolved()
}

let timer = null

// 只排一个"到下一次昼夜边界"的定时器，触发后重新判定并排下一个；
// 手动固定档与跟随系统档都不需要定时器（后者由 matchMedia 事件驱动）。
function syncTimer() {
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
  if (modeSource.value !== 'auto') return
  // 边界已过或时钟异常时兜底 1 分钟，避免死循环式补排
  const delay = Math.max(1000, nextModeChangeIn())
  timer = setTimeout(() => {
    timer = null
    applyResolved()
    syncTimer()
  }, delay)
}

try {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (modeSource.value === 'system') applyResolved()
  })
} catch { /* 老浏览器不支持 addEventListener 时忽略；auto 档另有 60 秒轮询 */ }

watch(modeSource, () => {
  syncTimer()
  applyResolved()
})

// 停止边界定时器。应用生命周期内不需要调用（本模块是模块级单例，
// 定时器随页面存活）；单测里逐份实例化主题模块时需要它来收干净句柄。
export function dispose() {
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
}

// 用账号上的外观偏好覆盖本地：登录与 restore（/auth/me）后由 stores/auth.js 调用。
// 服务端值优先，这样换设备或清掉浏览器缓存后依然是用户选过的那套外观。
export function syncFromAccount(accountTheme, accountMode) {
  let changed = false
  if (THEMES.some((t) => t.id === accountTheme) && accountTheme !== theme.value) {
    applyTheme(accountTheme)
    changed = true
  }
  // 'auto' 不在 modeSource 的合法档里也无需写盘：它就是本地默认值。
  if (isValidModeSource(accountMode) && accountMode !== modeSource.value) {
    setModeSource(accountMode)
    changed = true
  }
  return changed
}

// 启动收尾：main.js 在 createPinia() 之后把 auth store 传进来。
// 账号里的外观偏好优先于纯本地值；登录、刷新（/auth/me）、接口回传后 user 会变，
// 这里统一观察它。**刻意不 import auth store**：那样会把 api/authStorage 一并拉进
// 本模块，令纯逻辑单测无法在 node 下加载（见 tests/theme.test.mjs）。
let accountWatch = null

export function initTheme(auth) {
  if (!auth || typeof auth !== 'object') return
  if (accountWatch) accountWatch()
  accountWatch = watch(
    () => [auth.user?.theme_style, auth.user?.theme_mode],
    ([style, source]) => { syncFromAccount(style, source) },
    { immediate: true },
  )
}

// main.js 引入本模块时立即落地，避免首屏闪烁
applyTheme(theme.value)
applyResolved()
syncTimer()
