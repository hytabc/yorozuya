// 登录/注册人机验证状态管理。
//
// 支持两种 provider（由后端 /api/auth/captcha 决定）：
// - turnstile：Cloudflare Turnstile，显式渲染，token 作为 captcha_code 提交。
// - builtin：站内图形验证码，captcha_id + 用户输入作为 captcha_code 提交。
// - off：未启用，不渲染任何控件、提交时也不带验证码字段。
import { onUnmounted, reactive } from 'vue'
import { api } from '../api'

const TURNSTILE_SCRIPT_ID = 'cf-turnstile-script'
const TURNSTILE_SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
const TURNSTILE_LOAD_TIMEOUT_MS = 15000

let turnstilePromise = null

// 全局只加载一次 Turnstile 脚本（显式渲染模式）。
function loadTurnstileScript() {
  if (typeof window !== 'undefined' && window.turnstile) return Promise.resolve(window.turnstile)
  if (!turnstilePromise) {
    turnstilePromise = new Promise((resolve, reject) => {
      const existing = document.getElementById(TURNSTILE_SCRIPT_ID)
      const script = existing || document.createElement('script')
      if (!existing) {
        script.id = TURNSTILE_SCRIPT_ID
        script.src = TURNSTILE_SCRIPT_SRC
        script.async = true
        script.defer = true
        script.addEventListener('error', () => reject(new Error('turnstile script error')), { once: true })
        document.head.appendChild(script)
      }
      const startedAt = Date.now()
      const poll = () => {
        if (window.turnstile) return resolve(window.turnstile)
        if (Date.now() - startedAt > TURNSTILE_LOAD_TIMEOUT_MS) return reject(new Error('turnstile script timeout'))
        setTimeout(poll, 60)
      }
      poll()
    }).catch((error) => {
      turnstilePromise = null
      throw error
    })
  }
  return turnstilePromise
}

export function useCaptcha() {
  const captcha = reactive({
    provider: 'off',
    siteKey: '',
    captchaId: '',
    code: '',
    image: '',
    error: '',
  })
  let widgetId = null

  async function load() {
    captcha.error = ''
    captcha.code = ''
    try {
      const { data } = await api.get('/auth/captcha')
      captcha.provider = data.provider || 'off'
      captcha.siteKey = data.site_key || ''
      captcha.captchaId = data.captcha_id || ''
      captcha.image = data.image || ''
    } catch {
      // 加载失败时置为 error：界面提示且阻止提交，避免绕过验证码。
      captcha.provider = 'error'
      captcha.error = '人机验证加载失败，请刷新页面重试'
    }
  }

  // 把 Turnstile 组件挂载到指定容器；重复调用会先移除旧组件。
  async function attach(container) {
    if (captcha.provider !== 'turnstile' || !container) return
    try {
      const turnstile = await loadTurnstileScript()
      if (widgetId !== null) {
        try { turnstile.remove(widgetId) } catch { /* 旧组件可能已随 DOM 移除 */ }
        widgetId = null
      }
      widgetId = turnstile.render(container, {
        sitekey: captcha.siteKey,
        theme: 'light',
        language: 'zh-CN',
        callback: (token) => { captcha.code = token },
        'expired-callback': () => { captcha.code = '' },
        'error-callback': () => { captcha.code = '' },
      })
      captcha.error = ''
    } catch {
      captcha.error = '人机验证组件加载失败，请检查网络后重试'
    }
  }

  // 失效后重新挑战：turnstile 重置组件，builtin 重新取图。
  function reset() {
    captcha.code = ''
    if (captcha.provider === 'turnstile') {
      if (typeof window !== 'undefined' && window.turnstile && widgetId !== null) {
        try { window.turnstile.reset(widgetId) } catch { /* ignore */ }
      }
    } else if (captcha.provider === 'builtin') {
      load()
    }
  }

  function payload() {
    if (captcha.provider === 'turnstile') return { captcha_id: '', captcha_code: captcha.code || '' }
    if (captcha.provider === 'builtin') return { captcha_id: captcha.captchaId, captcha_code: captcha.code.trim() }
    return { captcha_id: '', captcha_code: '' }
  }

  function isSatisfied() {
    if (captcha.provider === 'off') return true
    if (captcha.provider === 'turnstile') return Boolean(captcha.code)
    if (captcha.provider === 'builtin') return Boolean(captcha.captchaId && captcha.code.trim())
    return false
  }

  function destroy() {
    if (widgetId !== null && typeof window !== 'undefined' && window.turnstile) {
      try { window.turnstile.remove(widgetId) } catch { /* ignore */ }
    }
    widgetId = null
  }

  onUnmounted(destroy)

  return { captcha, load, attach, reset, payload, isSatisfied }
}
