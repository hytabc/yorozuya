// Serial CAS saving. Injected adapters make account changes and races testable.
export function createSaveController({ ownerValid, snapshot, writeCloud, writeLocal, removeLocal, onStatus, delay = 1000 }) {
  let revision = 0, generation = 0, saved = 0, timer, active, conflict = false, disposed = false
  let localQueue = Promise.resolve()
  const report = (status) => onStatus({ dirty: generation !== saved, conflict, ...status })
  function assertOwner() { if (disposed || !ownerValid()) throw new Error('登录身份已变更，请重新进入房屋') }
  async function flush() {
    clearTimeout(timer)
    if (active) return active
    if (conflict || disposed) return false
    active = (async () => {
      try {
        assertOwner(); report({ saving: true, error: '' })
        while (generation !== saved) {
          assertOwner()
          const gen = generation, state = snapshot()
          const result = await writeCloud({ revision, state })
          assertOwner(); revision = result.revision; saved = gen
          if (saved === generation) {
            // Queue removal behind pending local writes; never remove a newer draft.
            localQueue = localQueue.catch(() => {}).then(() => {
              assertOwner()
              return saved === generation ? removeLocal() : undefined
            })
            await localQueue
          }
        }
        report({ saving: false, error: '', savedAt: new Date().toISOString() }); return true
      } catch (e) {
        conflict = e.response?.status === 409
        report({ saving: false, error: conflict ? '另一页面已更新房屋，草稿已保留。请重新载入或导出草稿。' : (typeof e.response?.data?.detail === 'string' ? e.response.data.detail : e.message) }); return false
      } finally { active = null }
    })()
    return active
  }
  function changed() {
    try { assertOwner() } catch (e) { report({ error: e.message }); return }
    generation++
    const draft = { revision, state: snapshot(), updatedAt: Date.now() }
    localQueue = localQueue.catch(() => {}).then(() => { assertOwner(); return writeLocal(draft) })
    localQueue.catch((e) => report({ error: `本地草稿保存失败：${e.message}` }))
    report({ error: '' }); clearTimeout(timer)
    if (!conflict) timer = setTimeout(flush, delay)
  }
  return { changed, flush, reset(value) { revision = value; generation = saved = 0; conflict = false; report({ error: '', saving: false }) },
    dispose() { disposed = true; clearTimeout(timer) }, get revision() { return revision }, get dirty() { return generation !== saved }, get conflict() { return conflict }, get active() { return active } }
}
