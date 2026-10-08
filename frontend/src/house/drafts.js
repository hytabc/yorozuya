let opening
function database() {
  if (!globalThis.indexedDB) return Promise.reject(new Error('浏览器不支持本地草稿存储'))
  if (!opening) opening = new Promise((resolve, reject) => {
    const request = indexedDB.open('yorozuya-house-drafts', 1)
    request.onupgradeneeded = () => request.result.createObjectStore('drafts')
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  return opening
}
export async function draftOperation(ownerId, kind, operation, value) {
  const db = await database()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('drafts', operation === 'get' ? 'readonly' : 'readwrite')
    const store = tx.objectStore('drafts'), key = `${ownerId}:${kind}`
    const request = operation === 'get' ? store.get(key) : operation === 'delete' ? store.delete(key) : store.put(value, key)
    let result
    request.onsuccess = () => { result = request.result }
    tx.oncomplete = () => resolve(result)
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error || new Error('草稿存储中断'))
  })
}
