import { ref, onMounted, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import axios from 'axios'
import { getToken, getTokenSync } from '../authStorage'

// Serial saves + optimistic revision; never retry a conflict by overwriting it.
// autoLoad: false 时由调用方在内容包就绪后手动调用 load()。
export function useLifeSave(snapshot, hydrate, { autoLoad = true } = {}) {
  // 凭证为加密存储，用同步快照做“账号未变更”判定；请求头按需异步取令牌。
  const ownerToken = getTokenSync()
  const api = axios.create({ baseURL: '/api', timeout: 15000 })
  api.interceptors.request.use(async (config) => {
    const token = await getToken()
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  })
  function ownerValid() {
    if (ownerToken && getTokenSync() === ownerToken) return true
    ready.value = false
    error.value = '登录身份已变更，请重新进入游戏。未向其他账号写入进度。'
    return false
  }
  const ready = ref(false)
  const saving = ref(false)
  const dirty = ref(false)
  const error = ref('')
  const conflict = ref(false)
  const savedAt = ref('')
  let revision = 0, generation = 0, timer, active, disposed = false

  async function load() {
    if (saving.value || !ownerValid()) return
    ready.value = false
    error.value = ''
    try {
      const { data } = await api.get('/virtual-life/save')
      if (disposed || !ownerValid()) return
      if (data.state) hydrate(data.state)
      revision = data.revision
      savedAt.value = data.updatedAt || ''
      dirty.value = false
      conflict.value = false
      ready.value = true
    } catch (e) {
      error.value = '读取存档失败，未启用游戏操作：' + (e.response?.data?.detail || e.message)
    }
  }

  function changed() {
    if (!ownerValid() || !ready.value || conflict.value) return
    generation++
    dirty.value = true
    clearTimeout(timer)
    timer = setTimeout(() => { flush() }, 700)
  }

  async function flush() {
    clearTimeout(timer)
    if (active) return active
    if (!ownerValid() || !ready.value || conflict.value) return false
    if (!dirty.value) return true
    active = (async () => {
      saving.value = true
      error.value = ''
      try {
        while (dirty.value) {
          if (!ownerValid()) return false
          const version = generation
          const state = snapshot()
          const { data } = await api.put('/virtual-life/save', { revision, state })
          revision = data.revision
          savedAt.value = data.updatedAt
          dirty.value = version !== generation
        }
        return !dirty.value
      } catch (e) {
        conflict.value = e.response?.status === 409
        error.value = conflict.value ? '另一页面已更新此存档。请重新载入，当前修改尚未保存。' :
          '保存失败，当前修改尚未落库：' + (typeof e.response?.data?.detail === 'string' ? e.response.data.detail : e.message)
        return false
      } finally {
        saving.value = false
        active = null
      }
    })()
    return active
  }

  function beforeUnload(event) {
    if (!dirty.value) return
    event.preventDefault()
    event.returnValue = ''
  }
  const storageChanged = () => { ownerValid() }
  onMounted(() => {
    if (autoLoad) load()
    window.addEventListener('beforeunload', beforeUnload)
    window.addEventListener('storage', storageChanged)
  })
  onBeforeRouteLeave(async () => {
    if (!dirty.value) return true
    if (await flush()) return true
    return window.confirm('修改尚未保存，离开将丢失本次修改。仍要离开吗？')
  })
  onBeforeUnmount(() => {
    // Responsive layout can unmount without router leave: finish a best-effort save.
    if (dirty.value && ownerValid()) flush()
    disposed = true
    clearTimeout(timer)
    window.removeEventListener('storage', storageChanged)
    window.removeEventListener('beforeunload', beforeUnload)
  })
  return { ready, saving, dirty, error, conflict, savedAt, changed, flush, load }
}
