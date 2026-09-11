// 登录凭证的本地加密存储。
//
// 目标：localStorage 里不再出现明文 JWT / 用户信息。
// 做法：AES-GCM 加密后写入 wsw_auth（IV + 密文，base64）；密钥为不可导出的 CryptoKey，
// 存于 IndexedDB —— 脚本（含 XSS）拿不到密钥原文，只能调用本页解密逻辑。
//
// 降级：非安全上下文（纯 HTTP 非 localhost）或 IndexedDB 不可用时，令牌只留内存、不落盘，
// 绝不回退为明文存储。

// 缓存结构版本：改动 localStorage 中保存的字段时递增，旧缓存会被清理并要求重新登录。
export const AUTH_CACHE_VERSION = '6'
// 上一个（明文）缓存版本，用于把旧缓存无感迁移成加密存储。
const LEGACY_CACHE_VERSION = '5'
export const LOGIN_MAX_AGE_MS = 24 * 60 * 60 * 1000

const SW_AUTH_KEY = 'wsw_auth'
const SW_AUTH_FORMAT_KEY = 'wsw_auth_format'
const LEGACY_KEYS = ['wsw_token', 'wsw_user', 'wsw_auth_version', 'wsw_login_at']

const IDB_NAME = 'wsw-auth'
const IDB_STORE = 'keys'
const IDB_KEY = 'aes-gcm'

// 内存缓存：{ token, user, loginAt, version } | null
let cache = null
// loadAuth() 只在此后走存储；未水合前任何读取都视为无缓存。
let hydrated = false
let keyPromise = null

function hasCrypto() {
  return typeof crypto !== 'undefined' && Boolean(crypto.subtle) && typeof crypto.subtle.generateKey === 'function'
}

function hasIndexedDb() {
  return typeof indexedDB !== 'undefined'
}

function isPersistent() {
  return hasCrypto() && hasIndexedDb()
}

function toBase64(bytes) {
  let binary = ''
  for (let index = 0; index < bytes.length; index += 1) binary += String.fromCharCode(bytes[index])
  return btoa(binary)
}

function fromBase64(value) {
  const binary = atob(value)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
  return bytes
}

function readItem(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeItem(key, value) {
  try {
    localStorage.setItem(key, value)
    return true
  } catch {
    return false
  }
}

function removeItem(key) {
  try {
    localStorage.removeItem(key)
  } catch {
    /* 忽略：隐私模式下可能不可写 */
  }
}

function removeLegacy() {
  LEGACY_KEYS.forEach(removeItem)
}

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(IDB_NAME, 1)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(IDB_STORE)) db.createObjectStore(IDB_STORE)
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function readKey() {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readonly')
    const request = tx.objectStore(IDB_STORE).get(IDB_KEY)
    request.onsuccess = () => resolve(request.result || null)
    request.onerror = () => reject(request.error)
  })
}

async function writeKey(key) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readwrite')
    tx.objectStore(IDB_STORE).put(key, IDB_KEY)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

// 取得（或首次生成）不可导出的 AES-GCM 密钥；失败时返回 null（调用方降级为仅内存）。
function getKey() {
  if (!isPersistent()) return Promise.resolve(null)
  if (!keyPromise) {
    keyPromise = (async () => {
      let key = await readKey()
      if (!key) {
        key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'])
        await writeKey(key)
      }
      return key
    })().catch(() => {
      keyPromise = null
      return null
    })
  }
  return keyPromise
}

function readLegacy() {
  if (readItem('wsw_auth_version') !== LEGACY_CACHE_VERSION) return null
  try {
    const token = readItem('wsw_token')
    const rawUser = readItem('wsw_user')
    if (!token || !rawUser) return null
    const user = JSON.parse(rawUser)
    if (!user) return null
    const loginAt = Number(readItem('wsw_login_at'))
    return {
      token,
      user,
      loginAt: Number.isFinite(loginAt) && loginAt > 0 ? loginAt : Date.now(),
      version: AUTH_CACHE_VERSION,
    }
  } catch {
    return null
  }
}

async function readStoredAuth() {
  // 旧版明文缓存 → 迁移为加密存储，用户无感、不必重新登录。
  const legacy = readLegacy()
  const raw = readItem(SW_AUTH_KEY)
  if (!raw) {
    if (legacy) {
      await saveAuth(legacy)
      return cache
    }
    return null
  }
  if (readItem(SW_AUTH_FORMAT_KEY) !== AUTH_CACHE_VERSION) {
    await clearAuth()
    return null
  }
  try {
    const key = await getKey()
    if (!key) return null
    const block = JSON.parse(raw)
    if (block.v !== AUTH_CACHE_VERSION || !block.iv || !block.data) return null
    const plaintext = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: fromBase64(block.iv) },
      key,
      fromBase64(block.data),
    )
    const parsed = JSON.parse(new TextDecoder().decode(plaintext))
    if (!parsed || !parsed.token) return null
    removeLegacy()
    return parsed
  } catch {
    // 密钥丢失或密文损坏：清理并要求重新登录。
    await clearAuth()
    return null
  }
}

// 幂等：整个应用生命周期只读一次存储。返回 { token, user, loginAt, version } | null。
export async function loadAuth() {
  if (hydrated) return cache
  hydrated = true
  cache = await readStoredAuth()
  return cache
}

export async function saveAuth({ token, user, loginAt, version }) {
  cache = {
    token: token ?? null,
    user: user ?? null,
    loginAt: loginAt ?? Date.now(),
    version: version ?? AUTH_CACHE_VERSION,
  }
  hydrated = true
  if (!isPersistent()) return
  try {
    const key = await getKey()
    if (!key) return
    const iv = crypto.getRandomValues(new Uint8Array(12))
    const plaintext = new TextEncoder().encode(JSON.stringify(cache))
    const cipher = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, plaintext)
    writeItem(SW_AUTH_KEY, JSON.stringify({ v: AUTH_CACHE_VERSION, iv: toBase64(iv), data: toBase64(new Uint8Array(cipher)) }))
    writeItem(SW_AUTH_FORMAT_KEY, AUTH_CACHE_VERSION)
    removeLegacy()
  } catch {
    // 加密或写入失败：丢弃落盘内容，保持仅内存，绝不写明文。
    removeItem(SW_AUTH_KEY)
    removeItem(SW_AUTH_FORMAT_KEY)
  }
}

export async function clearAuth() {
  cache = null
  hydrated = true
  removeItem(SW_AUTH_KEY)
  removeItem(SW_AUTH_FORMAT_KEY)
  removeLegacy()
  // 保留 IndexedDB 中的密钥，便于下次登录复用。
}

// 供 axios 拦截器等异步场景使用：优先内存缓存，否则先解密存储。
export async function getToken() {
  if (cache) return cache.token
  const loaded = await loadAuth()
  return loaded?.token ?? null
}

// 同步读取内存中的令牌；未水合时为 null（游戏存档用于“账号未变更”的同步判定）。
export function getTokenSync() {
  return cache?.token ?? null
}
