import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const ready = ref(false)

  const isLoggedIn = computed(() => Boolean(user.value))
  const isAdmin = computed(() => Boolean(user.value?.is_admin))
  const isStaff = computed(() => !isAdmin.value && user.value?.role === 'staff')
  const canManageRoles = computed(() => isAdmin.value || isStaff.value)

  function persist(payload) {
    user.value = payload.user
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
    try {
      const { data } = await api.get('/auth/me')
      user.value = data
    } catch {
      user.value = null
    } finally {
      ready.value = true
    }
  }

  function updateUser(data) {
    user.value = data
  }

  async function logout() {
    try { await api.post('/auth/logout') } catch { /* Clear local UI state even if the session has expired. */ }
    user.value = null
  }

  window.addEventListener('auth-expired', () => { user.value = null })
  return { user, ready, isLoggedIn, isAdmin, isStaff, canManageRoles, login, register, restore, updateUser, logout }
})
