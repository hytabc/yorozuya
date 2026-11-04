// 礼仪确认的共享状态：大厅首次进入、发布与接取前复用同一个遮罩。
import { reactive } from 'vue'
import { api } from '../api'
import { getTokenSync } from '../authStorage'
import {
  ATMOSPHERE_STORAGE_KEY,
  ATMOSPHERE_VERSION,
  needsAck,
  parseAckValue,
} from '../atmosphereRules'

export const atmosphere = reactive({
  loaded: false,
  version: ATMOSPHERE_VERSION,
  acceptedVersion: 0,
  open: false,
})

function readLocal() {
  try {
    return parseAckValue(localStorage.getItem(ATMOSPHERE_STORAGE_KEY))
  } catch {
    return 0
  }
}

function writeLocal(version) {
  try {
    localStorage.setItem(ATMOSPHERE_STORAGE_KEY, String(version))
  } catch {
    /* 隐私模式下写不进去：本次会话仍可确认，只是下次会重新出现 */
  }
}

export function needsAtmosphereAck() {
  return needsAck(atmosphere.version, atmosphere.acceptedVersion)
}

// 游客只看本地记录；登录用户以服务端记录为准（换设备后不会重复要求）。
export async function loadAtmosphere({ force = false } = {}) {
  if (atmosphere.loaded && !force) return atmosphere
  try {
    if (getTokenSync()) {
      const { data } = await api.get('/atmosphere/status')
      atmosphere.version = data.version
      atmosphere.acceptedVersion = data.accepted_version
      if (data.accepted) writeLocal(data.version)
    } else {
      atmosphere.acceptedVersion = readLocal()
    }
  } catch {
    // 接口不可用时按本地记录判断，不阻塞大厅浏览。
    atmosphere.acceptedVersion = readLocal()
  }
  atmosphere.loaded = true
  return atmosphere
}

export function openAtmosphereGate() {
  atmosphere.open = true
}

export function closeAtmosphereGate() {
  atmosphere.open = false
}

export async function acknowledgeAtmosphere() {
  if (getTokenSync()) {
    const { data } = await api.post('/atmosphere/ack', { version: atmosphere.version })
    atmosphere.version = data.version
    atmosphere.acceptedVersion = data.accepted_version
  } else {
    atmosphere.acceptedVersion = atmosphere.version
  }
  writeLocal(atmosphere.version)
  atmosphere.loaded = true
  atmosphere.open = false
}
