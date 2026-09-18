// 页面曝光时长（停留时长）计时：只累计「页面可见」的时间。
//
// 纯逻辑、零依赖，时钟通过参数注入，便于用 node:test 直接覆盖。
// 用法：enter(新页) 会结算并返回上一页的停留；pause() 切后台时结算并暂停；
// resume() 回到前台继续计时；finish() 关标签时结算并停止。

// 单次结算上限（秒）：与后端 PageDwellCreate 的 le=7200 保持一致，
// 避免「挂机开着页面」把平均值拉爆。
export const MAX_DWELL_SECONDS = 7200

export function createDwellTracker({ now = () => Date.now(), maxSeconds = MAX_DWELL_SECONDS } = {}) {
  let page = null
  // null 表示未在计时（不能用 0，否则与合法的时钟起点冲突）。
  let enteredAt = null

  function take() {
    if (!page || enteredAt === null) return null
    const seconds = Math.round((now() - enteredAt) / 1000)
    // 不足 1 秒的闪现不产生记录，避免噪音。
    if (seconds < 1) return null
    return { page, seconds: Math.min(seconds, maxSeconds) }
  }

  return {
    // 切换到新页面：结算上一页（若在计时），并从此刻开始为新页计时。
    enter(nextPage) {
      const left = take()
      page = nextPage || null
      enteredAt = page ? now() : null
      return left
    },
    // 切后台/最小化：结算当前页并暂停计时（后台时间不计入曝光）。
    pause() {
      const left = take()
      enteredAt = null
      return left
    },
    // 回到前台：当前页仍在，继续计时。
    resume() {
      if (page && enteredAt === null) enteredAt = now()
    },
    // 页面卸载：结算并彻底停止，重复调用是安全的空操作。
    finish() {
      const left = take()
      enteredAt = null
      page = null
      return left
    },
    get page() {
      return page
    },
    get counting() {
      return Boolean(page && enteredAt !== null)
    },
  }
}
