import axios from 'axios'

export const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE || '/api' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('wsw_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && localStorage.getItem('wsw_token')) {
      localStorage.removeItem('wsw_token')
      localStorage.removeItem('wsw_user')
      window.dispatchEvent(new Event('auth-expired'))
    }
    return Promise.reject(error)
  },
)

export function errorMessage(error, fallback = '操作失败，请稍后重试') {
  const detail = error.response?.data?.detail
  if (Array.isArray(detail)) return detail[0]?.msg || fallback
  return detail || fallback
}

