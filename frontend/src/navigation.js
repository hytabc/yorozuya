// 顶部导航的六个「大厅」分组与「更多」管理入口。
//
// 纯数据、零依赖，便于用 node:test 直接覆盖：可见性用标记位描述，由调用方按 auth 判定，
// 因此不能把组件/图标组件写进来（图标只存名字，由 AppHeader.vue 映射成组件）。
// 调整页面归属或新增入口时改这里。

export const HALLS = [
  {
    id: 'tasks',
    label: '委托大厅',
    icon: 'BriefcaseBusiness',
    items: [
      { to: '/', label: '委托大厅', icon: 'BriefcaseBusiness' },
      { to: '/mine', label: '我的委托', icon: 'BriefcaseBusiness', auth: true },
    ],
  },
  {
    id: 'talk',
    label: '交流大厅',
    icon: 'MessagesSquare',
    items: [
      { to: '/board', label: '留言板', icon: 'MessagesSquare' },
      { to: '/talk', label: '疑难解答', icon: 'CircleQuestionMark' },
    ],
  },
  {
    id: 'games',
    label: '游戏大厅',
    icon: 'Gamepad2',
    items: [
      { to: '/life', label: '虚拟人生', icon: 'Sparkles', lifeOnly: true },
      { to: '/frost', label: '糖霜世界', icon: 'Snowflake', auth: true },
    ],
  },
  {
    id: 'share',
    label: '分享大厅',
    icon: 'BookOpen',
    items: [
      { to: '/stories', label: '故事会', icon: 'BookOpen', auth: true },
      { to: '/maps', label: '地图推荐', icon: 'Map' },
    ],
  },
  {
    id: 'social',
    label: '交友大厅',
    icon: 'Users',
    items: [
      { to: '/friends', label: '交友厅', icon: 'UserPlus', auth: true },
      { to: '/sugar', label: '砂糖社', icon: 'HeartHandshake', auth: true },
    ],
  },
  {
    id: 'official',
    label: '官方大厅',
    icon: 'Store',
    items: [
      { to: '/staff', label: '成员名录', icon: 'Store' },
      { to: '/announcements', label: '公告中心', icon: 'Megaphone' },
      { to: '/versions', label: '版本更新', icon: 'History' },
    ],
  },
]

// 「更多」只留管理入口（监管台/运营台）；标签由 AppHeader 按角色动态生成。
export const MORE_LINKS = [
  { to: '/admin', label: '监管台', icon: 'ShieldCheck', moderate: true },
  { to: '/operations', label: '运营台', icon: 'BarChart3', operate: true },
]

export function itemVisible(item, auth) {
  // 虚拟人生沿用原守卫：必须等服务端确认过身份（ready + isLoggedIn + canPlayLife）才显示。
  if (item.lifeOnly) return Boolean(auth.ready && auth.isLoggedIn && auth.canPlayLife)
  if (item.auth) return Boolean(auth.isLoggedIn)
  return true
}

export function visibleItems(hall, auth) {
  return hall.items.filter((item) => itemVisible(item, auth))
}

// 当前路由是否属于某个大厅（用于高亮）。
export function hallContainsPath(hall, path) {
  return hall.items.some((item) => item.to === path)
}

export function moreLinks(auth) {
  return MORE_LINKS.filter((link) => {
    if (link.moderate) return Boolean(auth.canModerate)
    if (link.operate) return Boolean(auth.canOperate)
    return true
  })
}
