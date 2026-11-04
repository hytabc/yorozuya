// 聚光灯引导的纯几何工具：虚拟人生的 17 步指引与全站新手引导共用同一套。
// 纯函数、不碰全局对象，node:test 可以直接加载。
export function spotlightRect(rect, width, height) {
  if (!rect || rect.width <= 0 || rect.height <= 0 || rect.bottom <= 0 || rect.top >= height || rect.right <= 0 || rect.left >= width) return null
  const left = Math.max(0, rect.left - 6), top = Math.max(0, rect.top - 6)
  return { left, top, width: Math.max(0, Math.min(width, rect.right + 6) - left), height: Math.max(0, Math.min(height, rect.bottom + 6) - top) }
}

// 锚点是否"当前真的看得见"：display:none（例如 680px 以上的移动端菜单）、
// visibility:hidden 与零尺寸元素都算不可见，引导会顺延到下一个候选锚点。
export function isAnchorVisible(element) {
  if (!element) return false
  if (typeof element.getClientRects === 'function' && element.getClientRects().length === 0) return false
  const rect = typeof element.getBoundingClientRect === 'function' ? element.getBoundingClientRect() : null
  return Boolean(rect && rect.width > 0 && rect.height > 0)
}

// 同一份步骤表服务桌面与移动端：targets 按优先级排列，取第一个可见的锚点。
export function pickAnchor(step, root = typeof document === 'undefined' ? null : document) {
  const selectors = step?.targets || (step?.target ? [step.target] : [])
  if (!root || !selectors.length) return null
  for (const selector of selectors) {
    const element = root.querySelector(selector)
    if (isAnchorVisible(element)) return element
  }
  return null
}
