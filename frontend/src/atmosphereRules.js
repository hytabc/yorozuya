// 礼仪确认的纯规则：与后端 backend/app/atmosphere.py 的 ATMOSPHERE_VERSION 同步。
// 修改礼仪文案或 /terms 条款后必须递增版本号，已确认用户会被要求重新确认一次。
export const ATMOSPHERE_VERSION = 1
export const ATMOSPHERE_STORAGE_KEY = 'wsw_atmosphere_ack'

// 只保留「已确认到哪一版」这一条事实，旧版本号自然小于当前版本。
export function parseAckValue(raw) {
  const value = Number.parseInt(raw ?? '', 10)
  return Number.isFinite(value) && value > 0 ? value : 0
}

export function needsAck(version = ATMOSPHERE_VERSION, acceptedVersion = 0) {
  return Number(acceptedVersion || 0) < Number(version)
}
