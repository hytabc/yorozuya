/**
 * 版本更新弹窗的本地记录，以及"每次进入最多一个浮层"的抢占位。
 *
 * 不引入任何运行时依赖，`node --test` 可以直接覆盖。
 */
export const VERSION_ACK_KEY = 'wsw_version_ack'

function storageOf(storage) {
  return storage || globalThis.localStorage
}

/** 未登录用户"这台浏览器看过哪一版"，与 wsw_atmosphere_ack 一样只存版本号字符串。 */
export function readAckedVersion(storage) {
  try {
    return String(storageOf(storage)?.getItem(VERSION_ACK_KEY) || '').trim()
  } catch {
    return ''
  }
}

export function writeAckedVersion(version, storage) {
  const value = String(version ?? '').trim()
  if (!value) return false
  try {
    storageOf(storage).setItem(VERSION_ACK_KEY, value)
    return true
  } catch {
    return false
  }
}

// 每次页面加载（= 一次"进入"）只允许一个浮层占据这个位置。
// 版本更新 > 公告 > 礼仪确认 > 新手引导，谁先抢到谁展示，其余顺延到下次进入。
let promptSlot = null

export function promptOwner() {
  return promptSlot
}

export function claimPrompt(name) {
  if (!name || promptSlot) return false
  promptSlot = name
  return true
}

export function releasePrompt(name) {
  if (promptSlot === name) promptSlot = null
}

export function resetPromptSession() {
  promptSlot = null
}

// 公告与礼仪确认要等版本弹窗先做决定，否则两条请求谁先回来都可能抢走位置。
let settleDecision = null
let decisionPromise = new Promise((resolve) => { settleDecision = resolve })

export function versionDecisionSettled() {
  return decisionPromise
}

export function settleVersionDecision() {
  if (settleDecision) {
    settleDecision()
    settleDecision = null
  }
}

export function resetVersionDecision() {
  decisionPromise = new Promise((resolve) => { settleDecision = resolve })
}
