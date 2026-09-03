// 委托分类：面向 VRChat 常见委托内容
export const CATEGORIES = ['拍摄', '建模', '聊天', '陪睡', '解惑', '倾听', '陪玩', '其他']

// 店员继承志愿者的接单权限，并可管理非管理员账号的普通用户/志愿者等级。
export const ROLE_LABELS = { user: '普通用户', volunteer: '志愿者', staff: '店员' }
export const ROLE_HINTS = {
  user: '普通用户：可发布委托，也可接取无密码委托',
  volunteer: '志愿者：可发布委托，也可接取全部委托',
  staff: '店员：拥有志愿者权限，并可管理用户权限等级',
}
export function roleLabel(user) {
  if (!user) return ''
  if (user.is_admin) return '管理员'
  return ROLE_LABELS[user.role] || ROLE_LABELS.user
}
