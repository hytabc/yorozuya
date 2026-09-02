// 委托分类：面向 VRChat 常见委托内容
export const CATEGORIES = ['拍摄', '建模', '聊天', '陪睡', '解惑', '倾听', '陪玩', '其他']

// 用户权限等级：普通用户仅可发布委托；志愿者可发布+接取；管理员不接单
export const ROLE_LABELS = { user: '普通用户', volunteer: '志愿者' }
export const ROLE_HINTS = {
  user: '普通用户：可发布委托；接取委托需升级为志愿者',
  volunteer: '志愿者：可发布委托，也可接取委托',
}
export function roleLabel(user) {
  if (!user) return ''
  if (user.is_admin) return '管理员'
  return ROLE_LABELS[user.role] || ROLE_LABELS.user
}

