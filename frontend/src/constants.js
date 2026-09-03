// 委托分类：面向 VRChat 常见委托内容
export const CATEGORIES = ['拍摄', '建模', '聊天', '陪睡', '解惑', '倾听', '陪玩', '其他']

// 用户权限等级：普通用户可接取无密码委托；志愿者可接取全部委托；管理员不接单
export const ROLE_LABELS = { user: '普通用户', volunteer: '志愿者' }
export const ROLE_HINTS = {
  user: '普通用户：可发布委托，也可接取无密码委托',
  volunteer: '志愿者：可发布委托，也可接取全部委托',
}
export function roleLabel(user) {
  if (!user) return ''
  if (user.is_admin) return '管理员'
  return ROLE_LABELS[user.role] || ROLE_LABELS.user
}
