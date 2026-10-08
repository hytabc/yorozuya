import axios from 'axios'
import { getToken, getTokenSync, getPersistentToken } from '../authStorage.js'
export function ownedClient() {
  const ownerToken = getTokenSync()
  let invalidated = false, persistent = false
  try { persistent = Boolean(localStorage.getItem('wsw_auth')) } catch { /* Memory-only login. */ }
  const ownerValid = () => Boolean(!invalidated && ownerToken && getTokenSync() === ownerToken)
  async function checkStoredOwner() {
    if (persistent && await getPersistentToken() !== ownerToken) invalidated = true
  }
  const storageChanged = (event) => { if (event.key === 'wsw_auth' || event.key === null) checkStoredOwner() }
  window.addEventListener('storage', storageChanged)
  const client = axios.create({ baseURL: '/api', timeout: 45000 })
  client.interceptors.request.use(async (config) => {
    const token = await getToken()
    await checkStoredOwner()
    if (!ownerValid() || token !== ownerToken) throw new Error('登录身份已变更，请重新进入房屋')
    config.headers.Authorization = `Bearer ${ownerToken}`
    return config
  })
  client.interceptors.response.use((response)=>response,(error)=>{
    if(error.response?.status===401)window.dispatchEvent(new Event('auth-expired'))
    return Promise.reject(error)
  })
  return { client, ownerValid, dispose: () => window.removeEventListener('storage', storageChanged) }
}
