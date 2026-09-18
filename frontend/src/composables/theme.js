import { ref } from 'vue'

const STORAGE_KEY = 'yorozuya-theme'

export const THEMES = [
  { id: 'classic', label: '经典风' },
  { id: 'pixel', label: '像素风' },
]

function initialTheme() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (THEMES.some((t) => t.id === saved)) return saved
  } catch { /* 无痕模式等场景读不到 localStorage 时退回经典风 */ }
  return 'classic'
}

export const theme = ref(initialTheme())

export function applyTheme(id) {
  theme.value = id
  document.documentElement.dataset.theme = id
  try { localStorage.setItem(STORAGE_KEY, id) } catch { /* 写入失败不影响本次切换 */ }
}

export function cycleTheme() {
  const idx = THEMES.findIndex((t) => t.id === theme.value)
  applyTheme(THEMES[(idx + 1) % THEMES.length].id)
}

// main.js 引入本模块时立即落地,避免首屏闪烁
applyTheme(theme.value)
