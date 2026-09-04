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
      localStorage.removeItem('wsw_auth_version')
      localStorage.removeItem('wsw_login_at')
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

export function imageUploadErrorMessage(error) {
  const response = error.response
  const detail = response?.data?.detail
  if (typeof detail === 'string' && detail) return detail

  if (!response) {
    if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') return '图片上传超时，请检查网络后重试'
    return '网络连接异常，图片未上传，请检查网络后重试'
  }
  if (response.status === 413) return '图片总大小超过服务器限制，请减少图片数量或压缩后重试'
  if (response.status === 415) return '仅支持 JPEG、PNG、GIF 或 WebP 图片'
  if (response.status === 422) return '图片格式或上传内容不正确，请重新选择图片'
  if (response.status >= 500) return '服务器暂时无法保存图片，请稍后重试'
  return errorMessage(error, '图片上传失败，请稍后重试')
}
