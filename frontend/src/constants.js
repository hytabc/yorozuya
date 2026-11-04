// 官方群聊（QQ 群）：顶部导航常驻展示，点击复制群号
export const OFFICIAL_GROUP = { label: '官方群聊', id: '187814540' }

// 委托分类：与后端 main.py 的 TASK_CATEGORIES 白名单保持一致
export const CATEGORIES = ['萌新上路', '心理倾听', '技术疑难', 'VRC寻图', '搭子召集', '其他委托']

// VRChat 地图推荐类型
export const MAP_CATEGORIES = ['游戏', '休闲', '恐怖', '风景', '解谜', '社交', '其他']

// 交流大厅·疑难解答区子版块：key 需与后端 main.py 的 TALK_BOARDS 保持一致
export const TALK_BOARDS = [
  { key: 'newbie', label: '萌新求助' },
  { key: 'tech', label: '技术疑难' },
  { key: 'vrc', label: 'VRC 相关' },
  { key: 'resource', label: '资源分享' },
  { key: 'chat', label: '闲聊水区' },
  { key: 'other', label: '其他' },
]

// 委托模块化标签：与后端 backend/app/facets.py 的 SKILLS / PLATFORMS /
// ATMOSPHERE_GROUPS / FACET_LIMITS 保持一致（改一处必须同步另一处）。
export const TASK_SKILLS = [
  'Blender', 'Unity', 'PhysBones', 'lilToon', 'Udon',
  'VRChat SDK', '灯光', '世界优化', 'Quest 兼容', '音频',
]

export const TASK_PLATFORMS = ['PCVR', 'Quest', 'Desktop', '不限']

export const ATMOSPHERE_GROUPS = [
  { key: 'contact', label: '沟通方式', options: ['文字为主', '语音沟通', '游戏内沟通'] },
  { key: 'pace', label: '节奏', options: ['轻松推进', '紧凑交付', '可长期协作'] },
  { key: 'boundary', label: '边界', options: ['可录屏', '不录屏', '可二次创作', '不可二次创作'] },
  { key: 'payment', label: '报酬', options: ['有偿', '无偿', '以物易物', '可协商'] },
  { key: 'expectation', label: '期望', options: ['新手友好', '需要经验', '可指导'] },
]

export const ATMOSPHERE_TAGS = ATMOSPHERE_GROUPS.flatMap((group) => group.options)

export const FACET_LIMITS = { skill: 6, platform: 2, world: 3, atmosphere: 5 }
export const FACET_LABELS = { skill: '技能', platform: '平台', world: '参考 World', atmosphere: '氛围' }

// 管理员（内部值 staff）继承志愿者的接单权限，并可管理用户权限等级、处理用户反馈。
export const ROLE_LABELS = { user: '普通用户', volunteer: '志愿者', staff: '管理员', mascot: '看板娘', disciplinarian: '风纪委员' }
export const ROLE_HINTS = {
  user: '普通用户：可发布委托，凭正确密码也可接取带密码委托',
  volunteer: '志愿者：可发布委托，也可接取全部委托',
  staff: '管理员：拥有志愿者权限，并可管理用户权限等级、处理用户反馈',
  mascot: '看板娘：负责网站公告、活动公告与社区运营数据分析',
  disciplinarian: '风纪委员：负责图片审核，以及委托和地图推荐举报处理',
}
export function roleLabel(user) {
  if (!user) return ''
  if (user.is_admin) return '超级管理员'
  return ROLE_LABELS[user.role] || ROLE_LABELS.user
}
