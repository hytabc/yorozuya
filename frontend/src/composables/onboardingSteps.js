// 全站新手引导的步骤表：纯数据 + 纯函数，node:test 可直接加载。
// targets 按优先级排列：同一份步骤表服务桌面与移动端，取当前可见的第一个锚点。
// 改了文案或步骤后递增 ONBOARDING_VERSION，已看过的账号会再看一次新版；
// 设为 0 等于整体关停（needsOnboarding 永远返回 false）。

export const ONBOARDING_VERSION = 1

export const onboardingSteps = [
  {
    id: 'welcome',
    title: '欢迎来到万事屋',
    text: '这里把「需要帮忙的事」和「恰好擅长的人」凑到一起：委托人发委托，志愿者接委托，双方各自确认后完成。',
    targets: ['[data-tour="intro"]', '.hall-intro'],
  },
  {
    id: 'create',
    title: '有需要就先发一份委托',
    text: '写清想完成的事、分类和报酬即可发布；可以设置接取密码、指定接单人，也可以匿名。记得先填好 QQ，志愿者才能联系你。',
    targets: ['[data-tour="create-task"]', '.hall-heading-actions .button'],
  },
  {
    id: 'nav',
    title: '六个大厅，各管一类事',
    text: '委托、交流、游戏、分享、交友、官方——顶部导航按大厅分组。手机端点右上角的菜单按钮，展开的是同一套分组。',
    targets: ['[data-tour="nav-mobile"]', '[data-tour="nav"]', '.desktop-nav', '.mobile-menu'],
  },
  {
    id: 'notifications',
    title: '委托有动静，这里会亮',
    text: '有人接取、确认完成、发起取消，或你被采纳时会收到站内通知；铃铛上的红点就是未读数量。',
    targets: ['[data-tour="notifications"]', '.notification-toggle'],
  },
  {
    id: 'profile',
    title: '个人设置里还有这些',
    text: '在「个人设置」可以补 QQ、绑定邮箱、管理头像与介绍图片；「外观」里能切换风格与深色模式，也能随时重新看这份引导。',
    targets: ['[data-tour="profile"]', '.user-chip'],
  },
]

// 浏览器本地只做防闪烁缓存；"看过哪一版"以服务端 users.onboarding_version 为准。
export const onboardingStorageKey = (userId) => {
  const id = Number(userId)
  return Number.isSafeInteger(id) && id > 0 ? `wsw:onboarding:v${ONBOARDING_VERSION}:user:${id}` : null
}

export function needsOnboarding(seenVersion, current = ONBOARDING_VERSION) {
  return current > 0 && Number(seenVersion || 0) < current
}
