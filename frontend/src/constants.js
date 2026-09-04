// 委托分类：面向 VRChat 常见委托内容
export const CATEGORIES = ['拍摄', '建模', '聊天', '陪睡', '解惑', '倾听', '陪玩', '其他']

// 管理员（内部值 staff）继承志愿者的接单权限，并可管理用户权限等级、处理用户反馈。
export const ROLE_LABELS = { user: '普通用户', volunteer: '志愿者', staff: '管理员' }
export const ROLE_HINTS = {
  user: '普通用户：可发布委托，凭正确密码也可接取带密码委托',
  volunteer: '志愿者：可发布委托，也可接取全部委托',
  staff: '管理员：拥有志愿者权限，并可管理用户权限等级、处理用户反馈',
}
export function roleLabel(user) {
  if (!user) return ''
  if (user.is_admin) return '超级管理员'
  return ROLE_LABELS[user.role] || ROLE_LABELS.user
}
