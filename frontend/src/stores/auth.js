import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api'
import { AUTH_CACHE_VERSION, LOGIN_MAX_AGE_MS, REMEMBER_MAX_AGE_MS, clearAuth, loadAuth, saveAuth } from '../authStorage'

export const useAuthStore = defineStore('auth', () => {
  // 凭证以加密形式存放，需异步解密（hydrate）后才能拿到，故初始为空。
  const token = ref(null)
  const user = ref(null)
  // 权限可信标记：只有服务端（登录/注册响应或 /auth/me）确认过身份后才为 true。
  // 本地缓存即便被解密也仍视为不可信，所有权限判断都必须等 verified 之后。
  const verified = ref(false)
  const ready = ref(false)
  let loginAt = 0
  // 本地缓存的「自动登录」标记：true 时有效期窗口为 7 天，否则 24 小时。
  let remember = false
  let hydratePromise = null

  const isLoggedIn = computed(() => Boolean(token.value && user.value))
  const isAdmin = computed(() => verified.value && Boolean(user.value?.is_admin))
  const isStaff = computed(() => verified.value && !isAdmin.value && user.value?.role === 'staff')
  const isMascot = computed(() => verified.value && !isAdmin.value && user.value?.role === 'mascot')
  const isDisciplinarian = computed(() => verified.value && !isAdmin.value && user.value?.role === 'disciplinarian')
  const role = computed(() => (verified.value ? user.value?.role ?? null : null))
  const canModerate = computed(() => isAdmin.value || isStaff.value || isDisciplinarian.value)
  const canManageRoles = computed(() => isAdmin.value || isStaff.value)
  // 运营台入口：看板娘管公告/内测、管理员组看数据看板与内测，超管全部可见。
  const canOperate = computed(() => isAdmin.value || isMascot.value || isStaff.value)
  const isBetaTester = computed(() => verified.value && Boolean(user.value?.is_beta_tester))
  // 邮箱验证状态：只有服务端确认过身份（verified）后才可信。
  // emailGateRequired 由后端下发（它知道 require_email_verification 策略），前端不自作判断。
  const emailVerified = computed(() => verified.value && Boolean(user.value?.email_verified))
  const emailGateRequired = computed(() => verified.value && Boolean(user.value?.email_gate_required))
  // 虚拟人生对所有登录用户开放（内测标记仅作身份展示，不再门控）
  const canPlayLife = computed(() => isLoggedIn.value)

  // 幂等：只解密一次本地凭证；不联网、不置 verified（身份仍需服务端确认）。
  function hydrate() {
    if (!hydratePromise) {
      hydratePromise = loadAuth()
        .then((cached) => {
          if (cached) {
            token.value = cached.token
            user.value = cached.user
            loginAt = Number(cached.loginAt) || 0
            remember = Boolean(cached.remember)
          }
        })
        .catch(() => {
          // 解密/存储异常一律视为未登录，避免阻塞路由守卫。
          token.value = null
          user.value = null
          loginAt = 0
          remember = false
        })
    }
    return hydratePromise
  }

  async function persist(payload) {
    token.value = payload.access_token
    user.value = payload.user
    // 登录/注册响应由服务端签发，可据此信任身份。
    verified.value = true
    loginAt = Date.now()
    remember = Boolean(payload.remember)
    await saveAuth({ token: token.value, user: user.value, loginAt, remember, version: AUTH_CACHE_VERSION })
  }

  async function login(credentials) {
    const { data } = await api.post('/auth/login', credentials)
    await persist(data)
  }

  async function register(payload) {
    const { data } = await api.post('/auth/register', payload)
    // 注册不再直接登录：必须先点邮件里的验证链接，这里把受理结果交给视图展示。
    return data
  }

  async function restore() {
    await hydrate()
    // “自动登录”缓存在 7 天内有效，普通缓存在 24 小时内有效。
    const maxAge = remember ? REMEMBER_MAX_AGE_MS : LOGIN_MAX_AGE_MS
    const age = Date.now() - loginAt
    const valid = Boolean(
      token.value && user.value && Number.isFinite(loginAt) && loginAt > 0 && age >= 0 && age < maxAge,
    )
    if (!valid) {
      // 本地缺少有效凭证（或已超过有效期），需要重新登录。
      await logout()
      ready.value = true
      return
    }
    try {
      const { data } = await api.get('/auth/me')
      user.value = data
      // 以服务端返回为准确认身份，之后权限判断才可信。
      verified.value = true
      await saveAuth({ token: token.value, user: data, loginAt, remember, version: AUTH_CACHE_VERSION })
    } catch {
      await logout()
    } finally {
      ready.value = true
    }
  }

  function updateUser(data) {
    user.value = data
    if (!token.value) return Promise.resolve()
    return saveAuth({ token: token.value, user: data, loginAt, remember, version: AUTH_CACHE_VERSION })
  }

  // 局部更新：接口回传的是完整 UserSelf，但只合并这些字段，
  // 避免旧响应覆盖掉本地更新的其它字段（外观偏好用它）。
  function patchUser(partial) {
    if (!user.value) return Promise.resolve()
    return updateUser({ ...user.value, ...partial })
  }

  // 登出 = 本地清理 + 服务端吊销。先清本地再请求，避免服务端 401 触发
  // auth-expired 又重新进入 logout；请求显式带上刚捕获的令牌，失败静默。
  async function logout() {
    const current = token.value
    token.value = null
    user.value = null
    verified.value = false
    loginAt = 0
    remember = false
    await clearAuth()
    if (!current) return
    try {
      await api.post('/auth/logout', null, { headers: { Authorization: `Bearer ${current}` } })
    } catch {
      // 网络异常或令牌已失效都不影响本地登出。
    }
  }

  window.addEventListener('auth-expired', logout)
  return { token, user, verified, ready, isLoggedIn, isAdmin, isStaff, isMascot, isDisciplinarian, role, canModerate, canManageRoles, canOperate, isBetaTester, emailVerified, emailGateRequired, canPlayLife, login, register, restore, updateUser, patchUser, logout, hydrate }
})
