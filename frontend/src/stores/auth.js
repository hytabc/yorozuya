import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api'

const AUTH_CACHE_VERSION = '5'
const LOGIN_MAX_AGE_MS = 24 * 60 * 60 * 1000

function clearAuthCache() {
  localStorage.removeItem('wsw_token')
  localStorage.removeItem('wsw_user')
  localStorage.removeItem('wsw_auth_version')
  localStorage.removeItem('wsw_login_at')
}

function readCachedUser() {
  try {
    return JSON.parse(localStorage.getItem('wsw_user') || 'null')
  } catch {
    return null
  }
}

function readPersistedAuth() {
  const cachedToken = localStorage.getItem('wsw_token')
  const cachedUser = readCachedUser()
  const loginAt = Number(localStorage.getItem('wsw_login_at'))
  const age = Date.now() - loginAt
  const valid = Boolean(
    cachedToken && cachedUser && localStorage.getItem('wsw_auth_version') === AUTH_CACHE_VERSION
    && Number.isFinite(loginAt) && loginAt > 0 && age >= 0 && age < LOGIN_MAX_AGE_MS,
  )
  if (!valid) {
    // 缺少版本/时间标记的缓存来自旧版本，默认视为需要重新登录。
    clearAuthCache()
    return { token: null, user: null }
  }
  return { token: cachedToken, user: cachedUser }
}

export const useAuthStore = defineStore('auth', () => {
  const persisted = readPersistedAuth()
  const token = ref(persisted.token)
  const user = ref(persisted.user)
  // 权限可信标记：只有服务端（登录/注册响应或 /auth/me）确认过身份后才为 true。
  // localStorage 中的 wsw_user 可被任意篡改，因此所有权限判断都必须等 verified 之后，
  // 这样即便手动改写缓存也无法让界面认为自己拥有管理员权限。
  const verified = ref(false)
  const ready = ref(false)

  const isLoggedIn = computed(() => Boolean(token.value && user.value))
  const isAdmin = computed(() => verified.value && Boolean(user.value?.is_admin))
  const isStaff = computed(() => verified.value && !isAdmin.value && user.value?.role === 'staff')
  const isMascot = computed(() => verified.value && !isAdmin.value && user.value?.role === 'mascot')
  const isDisciplinarian = computed(() => verified.value && !isAdmin.value && user.value?.role === 'disciplinarian')
  const role = computed(() => (verified.value ? user.value?.role ?? null : null))
  const canModerate = computed(() => isAdmin.value || isStaff.value || isDisciplinarian.value)
  const canManageRoles = computed(() => isAdmin.value || isStaff.value)
  const canOperate = computed(() => isAdmin.value || isMascot.value)
  const isBetaTester = computed(() => verified.value && Boolean(user.value?.is_beta_tester))
  // 虚拟人生对所有登录用户开放（内测标记仅作身份展示，不再门控）
  const canPlayLife = computed(() => isLoggedIn.value)

  function persist(payload) {
    token.value = payload.access_token
    user.value = payload.user
    // 登录/注册响应由服务端签发，可据此信任身份。
    verified.value = true
    localStorage.setItem('wsw_token', token.value)
    localStorage.setItem('wsw_user', JSON.stringify(user.value))
    localStorage.setItem('wsw_auth_version', AUTH_CACHE_VERSION)
    localStorage.setItem('wsw_login_at', String(Date.now()))
  }

  async function login(credentials) {
    const { data } = await api.post('/auth/login', credentials)
    persist(data)
  }

  async function register(payload) {
    const { data } = await api.post('/auth/register', payload)
    persist(data)
  }

  async function restore() {
    const loginAt = Number(localStorage.getItem('wsw_login_at'))
    const age = Date.now() - loginAt
    if (!token.value || !user.value || localStorage.getItem('wsw_auth_version') !== AUTH_CACHE_VERSION
      || !Number.isFinite(loginAt) || loginAt <= 0 || age < 0 || age >= LOGIN_MAX_AGE_MS) {
      logout()
      ready.value = true
      return
    }
    try {
      const { data } = await api.get('/auth/me')
      user.value = data
      // 以服务端返回为准确认身份，之后权限判断才可信。
      verified.value = true
      localStorage.setItem('wsw_user', JSON.stringify(data))
    } catch {
      logout()
    } finally {
      ready.value = true
    }
  }

  function updateUser(data) {
    user.value = data
    localStorage.setItem('wsw_user', JSON.stringify(data))
  }

  function logout() {
    token.value = null
    user.value = null
    verified.value = false
    localStorage.removeItem('wsw_token')
    localStorage.removeItem('wsw_user')
    localStorage.removeItem('wsw_auth_version')
    localStorage.removeItem('wsw_login_at')
  }

  window.addEventListener('auth-expired', logout)
  return { token, user, verified, ready, isLoggedIn, isAdmin, isStaff, isMascot, isDisciplinarian, role, canModerate, canManageRoles, canOperate, isBetaTester, canPlayLife, login, register, restore, updateUser, logout }
})
