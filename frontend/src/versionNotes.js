/**
 * 版本更新记录：唯一数据源是 `public/versions/versions.json`。
 *
 * 这份数据同时喂三处：/versions 历史页、页脚版本号、登录后的版本更新弹窗。
 * 纯函数与网络加载分开，`node --test` 可以直接覆盖判定逻辑。
 */
const NOTES_PATH = '/versions/versions.json'

let notesPromise = null

export function normalizeVersion(value) {
  return String(value ?? '').trim()
}

/** 当前版本 = entries 的第一项（约定按从新到旧排列）。 */
export function currentVersion(notes) {
  return normalizeVersion(notes?.entries?.[0]?.version)
}

export function currentVersionEntry(notes) {
  return notes?.entries?.[0] || null
}

export function versionIndex(notes, version) {
  const target = normalizeVersion(version)
  if (!target || !Array.isArray(notes?.entries)) return -1
  return notes.entries.findIndex((entry) => normalizeVersion(entry?.version) === target)
}

/**
 * 用户错过了几个版本：已确认版本在列表中的位置就是错过的数量。
 * 已确认版本不在列表里（太久远或换了版本号格式）时，按"除了最新版都错过了"算。
 */
export function missedVersionCount(notes, ackedVersion) {
  const total = notes?.entries?.length || 0
  if (total <= 1) return 0
  const index = versionIndex(notes, ackedVersion)
  if (index > 0) return index
  return index === -1 && normalizeVersion(ackedVersion) ? total - 1 : 0
}

/** 只要版本号与已确认版本不同就弹；同一版本号下改文案不会重新弹。 */
export function shouldPromptVersion(notes, ackedVersion) {
  const current = currentVersion(notes)
  return Boolean(current) && current !== normalizeVersion(ackedVersion)
}

/** 读取版本记录，失败时返回 null 且不缓存失败结果（下次进入可重试）。 */
export function loadVersionNotes(fetcher = globalThis.fetch) {
  if (!notesPromise) {
    notesPromise = Promise.resolve()
      .then(() => fetcher(NOTES_PATH, { cache: 'no-cache' }))
      .then((response) => {
        if (!response || !response.ok) throw new Error('version notes unavailable')
        return response.json()
      })
      .catch(() => {
        notesPromise = null
        return null
      })
  }
  return notesPromise
}

export function resetVersionNotesCache() {
  notesPromise = null
}
