import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api'

const AUTH_CACHE_VERSION = '2'
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
  const ready = ref(false)

  const isLoggedIn = computed(() => Boolean(token.value && user.value))
  const isAdmin = computed(() => Boolean(user.value?.is_admin))
  const isStaff = computed(() => !isAdmin.value && user.value?.role === 'staff')
  const canManageRoles = computed(() => isAdmin.value || isStaff.value)

  function persist(payload) {
    token.value = payload.access_token
    user.value = payload.user
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
    localStorage.removeItem('wsw_token')
    localStorage.removeItem('wsw_user')
    localStorage.removeItem('wsw_auth_version')
    localStorage.removeItem('wsw_login_at')
  }

  window.addEventListener('auth-expired', logout)
  return { token, user, ready, isLoggedIn, isAdmin, isStaff, canManageRoles, login, register, restore, updateUser, logout }
})
