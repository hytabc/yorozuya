const SEEN_KEY_PREFIX = 'wsw_seen_announcements_'

function announcementVersion(item) {
  return item?.updated_at || item?.created_at || ''
}

export function announcementSeenKey(userId) {
  const normalized = Number(userId)
  return Number.isSafeInteger(normalized) && normalized > 0
    ? `${SEEN_KEY_PREFIX}${normalized}`
    : null
}

function readSeenVersions(storage, userId) {
  const key = announcementSeenKey(userId)
  if (!key) return {}
  try {
    const value = JSON.parse(storage.getItem(key) || '{}')
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
  } catch {
    return {}
  }
}

export function unseenAnnouncements(items, userId, storage = localStorage) {
  if (!Array.isArray(items) || !items.length) return []
  const key = announcementSeenKey(userId)
  if (!key) return items
  const seen = readSeenVersions(storage, userId)
  return items.filter((item) => seen[item.id] !== announcementVersion(item))
}

export function markAnnouncementsSeen(items, userId, storage = localStorage) {
  const key = announcementSeenKey(userId)
  if (!key) return false
  const versions = Object.fromEntries(
    items.map((item) => [item.id, announcementVersion(item)]).filter(([, version]) => version),
  )
  try {
    storage.setItem(key, JSON.stringify(versions))
    return true
  } catch {
    return false
  }
}
