// 登录/注册人机验证状态管理。
//
// 支持多种 provider（由后端 /api/auth/captcha 决定，env 中互斥切换）：
// - turnstile：Cloudflare Turnstile，显式渲染，token 作为 captcha_code 提交。
// - builtin：站内图形验证码，captcha_id + 用户输入作为 captcha_code 提交。
// - click：站内点击图形验证码，按题面依次点击，归一化坐标序列作为 captcha_code 提交。
//   答案只存服务端，前端仅拿到图片与题面。
// - vaptcha：VAPTCHA V4，页面显式调用 validate()，把 token/knock/dfu/ip 打包成 JSON 提交；
//   服务端用 VKEY 本地验签，VKEY 绝不下发到前端。
// - off：未启用，不渲染任何控件、提交时也不带验证码字段。
import { onUnmounted, reactive } from 'vue'
import { api } from '../api'

const TURNSTILE_SCRIPT_ID = 'cf-turnstile-script'
const TURNSTILE_SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
const TURNSTILE_LOAD_TIMEOUT_MS = 15000

const VAPTCHA_SCRIPT_ID = 'vaptcha-v4-script'
const VAPTCHA_SCRIPT_SRC = 'https://c4.vaptcha.com/src/v4.js'
const VAPTCHA_LOAD_TIMEOUT_MS = 15000

let turnstilePromise = null
let vaptchaPromise = null

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

// 全局只加载一次 VAPTCHA V4 SDK（window.vaptcha 为初始化函数）。
function loadVaptchaScript() {
  if (typeof window !== 'undefined' && typeof window.vaptcha === 'function') {
    return Promise.resolve(window.vaptcha)
  }
  if (!vaptchaPromise) {
    vaptchaPromise = new Promise((resolve, reject) => {
      const existing = document.getElementById(VAPTCHA_SCRIPT_ID)
      const script = existing || document.createElement('script')
      if (!existing) {
        script.id = VAPTCHA_SCRIPT_ID
        script.src = VAPTCHA_SCRIPT_SRC
        script.async = true
        script.defer = true
        script.addEventListener('error', () => reject(new Error('vaptcha script error')), { once: true })
        document.head.appendChild(script)
      }
      const startedAt = Date.now()
      const poll = () => {
        if (typeof window.vaptcha === 'function') return resolve(window.vaptcha)
        if (Date.now() - startedAt > VAPTCHA_LOAD_TIMEOUT_MS) return reject(new Error('vaptcha script timeout'))
        setTimeout(poll, 60)
      }
      poll()
    }).catch((error) => {
      vaptchaPromise = null
      throw error
    })
  }
  return vaptchaPromise
}

export function useCaptcha() {
  const captcha = reactive({
    provider: 'off',
    siteKey: '',
    captchaId: '',
    code: '',
    image: '',
    prompt: '',
    targetCount: 0,
    clicks: [],
    vaptchaVid: '',
    vaptcha: { token: '', knock: '', dfu: '', ip: '' },
    error: '',
  })
  let widgetId = null
  let vaptchaObj = null

  async function load() {
    captcha.error = ''
    captcha.code = ''
    captcha.clicks = []
    captcha.vaptcha = { token: '', knock: '', dfu: '', ip: '' }
    vaptchaObj = null
    try {
      const { data } = await api.get('/auth/captcha')
      captcha.provider = data.provider || 'off'
      captcha.siteKey = data.site_key || ''
      captcha.captchaId = data.captcha_id || ''
      captcha.image = data.image || ''
      captcha.prompt = data.prompt || ''
      captcha.targetCount = data.target_count || 0
      captcha.vaptchaVid = data.vaptcha_vid || ''
    } catch {
      // 加载失败时置为 error：界面提示且阻止提交，避免绕过验证码。
      captcha.provider = 'error'
      captcha.error = '人机验证加载失败，请刷新页面重试'
    }
  }

  // 挂载人机验证组件：turnstile 渲染 widget；vaptcha 初始化 SDK 实例（锚点容器）。
  async function attach(container) {
    if (!container) return
    if (captcha.provider === 'vaptcha') {
      try {
        const sdk = await loadVaptchaScript()
        // VAPTCHA 不注入按钮：容器只是挂载锚点，验证入口由页面显式调用 validate()。
        vaptchaObj = await sdk({ vid: captcha.vaptchaVid, container, lang: 'zh-CN' })
        captcha.error = ''
      } catch {
        captcha.error = '人机验证组件加载失败，请检查网络后重试'
      }
      return
    }
    if (captcha.provider !== 'turnstile') return
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

  // vaptcha：显式发起验证，成功后缓存 SDK 返回的 token/knock/dfu/ip。
  async function validate() {
    if (captcha.provider !== 'vaptcha' || !vaptchaObj) {
      captcha.error = '人机验证尚未就绪，请刷新页面重试'
      return false
    }
    try {
      const result = await vaptchaObj.validate()
      if (!result || !result.token || !result.knock) {
        captcha.error = '请完成人机验证'
        return false
      }
      captcha.vaptcha = {
        token: result.token,
        knock: result.knock || '',
        dfu: result.dfu || '',
        ip: result.ip || '',
      }
      captcha.error = ''
      return true
    } catch {
      captcha.error = '人机验证未通过，请重试'
      return false
    }
  }

  // click：记录一次归一化点击落点（0..1）；超出目标数量后忽略。
  function selectPoint(x, y) {
    if (captcha.provider !== 'click') return
    if (captcha.clicks.length >= captcha.targetCount) return
    captcha.clicks.push({ x, y })
  }

  // click：清空已选落点。
  function clearClicks() {
    captcha.clicks = []
  }

  // 失效后重新挑战：turnstile 重置组件，builtin/click 重新出题。
  function reset() {
    captcha.code = ''
    if (captcha.provider === 'turnstile') {
      if (typeof window !== 'undefined' && window.turnstile && widgetId !== null) {
        try { window.turnstile.reset(widgetId) } catch { /* ignore */ }
      }
    } else if (captcha.provider === 'builtin' || captcha.provider === 'click') {
      load()
    } else if (captcha.provider === 'vaptcha') {
      // 清空本次结果，下次点击「验证」时重新挑战。
      captcha.vaptcha = { token: '', knock: '', dfu: '', ip: '' }
    }
  }

  function payload() {
    if (captcha.provider === 'turnstile') return { captcha_id: '', captcha_code: captcha.code || '' }
    if (captcha.provider === 'builtin') return { captcha_id: captcha.captchaId, captcha_code: captcha.code.trim() }
    if (captcha.provider === 'click') {
      const code = captcha.clicks.map((point) => `${point.x.toFixed(4)},${point.y.toFixed(4)}`).join(';')
      return { captcha_id: captcha.captchaId, captcha_code: code }
    }
    if (captcha.provider === 'vaptcha') {
      // 四个值打包成 JSON 放进 captcha_code（非密钥，服务端用 VKEY 本地验签）。
      return { captcha_id: '', captcha_code: JSON.stringify(captcha.vaptcha) }
    }
    return { captcha_id: '', captcha_code: '' }
  }

  function isSatisfied() {
    if (captcha.provider === 'off') return true
    if (captcha.provider === 'turnstile') return Boolean(captcha.code)
    if (captcha.provider === 'builtin') return Boolean(captcha.captchaId && captcha.code.trim())
    if (captcha.provider === 'click') {
      return captcha.targetCount > 0 && captcha.clicks.length === captcha.targetCount
    }
    if (captcha.provider === 'vaptcha') return Boolean(captcha.vaptcha.token)
    return false
  }

  function destroy() {
    if (widgetId !== null && typeof window !== 'undefined' && window.turnstile) {
      try { window.turnstile.remove(widgetId) } catch { /* ignore */ }
    }
    widgetId = null
  }

  onUnmounted(destroy)

  return { captcha, load, attach, reset, payload, isSatisfied, selectPoint, clearClicks, validate }
}
