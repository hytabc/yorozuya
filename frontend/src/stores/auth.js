import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('wsw_token'))
  const user = ref(JSON.parse(localStorage.getItem('wsw_user') || 'null'))
  const ready = ref(false)

  const isLoggedIn = computed(() => Boolean(token.value && user.value))
  const isAdmin = computed(() => Boolean(user.value?.is_admin))

  function persist(payload) {
    token.value = payload.access_token
    user.value = payload.user
    localStorage.setItem('wsw_token', token.value)
    localStorage.setItem('wsw_user', JSON.stringify(user.value))
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
    if (!token.value) {
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
  }

  window.addEventListener('auth-expired', logout)
  return { token, user, ready, isLoggedIn, isAdmin, login, register, restore, updateUser, logout }
})

