// VRChat 信任信息的展示规则：纯逻辑，组件与测试共用。
// 与后端 backend/app/trust.py 的 DISCLOSURE_KEYS 保持一致。

export const TRUST_RANK_LABELS = {
  visitor: '游客',
  new_user: '新用户',
  user: '用户',
  known_user: '熟识用户',
  trusted_user: '可信用户',
  unknown: '未识别',
}

// 与 VRChat 游戏内 Trust Rank 颜色保持一致；后端 backend/app/trust.py 同步。
export const TRUST_RANK_COLORS = {
  visitor: '#808080',
  new_user: '#1778FF',
  user: '#2BCF5C',
  known_user: '#FF7B42',
  trusted_user: '#8143E6',
  unknown: '#8A8A8A',
}

export const TRUST_DISCLOSURE = [
  {
    key: 'identity',
    label: '显示名与主页链接',
    hint: '展示 VRChat 显示名与个人主页。',
    available: true,
  },
  {
    key: 'trust_rank',
    label: 'Trust Rank',
    hint: '验证后由服务端读取并展示 VRChat 信任等级。',
    available: true,
  },
  {
    key: 'account_age',
    label: '账号年龄',
    hint: '验证后展示账号注册时间与年龄。',
    available: true,
  },
  {
    key: 'platform',
    label: '常用平台',
    hint: '验证后展示最近使用的平台（PC / Quest 等）。',
    available: true,
  },
  {
    key: 'common_friends',
    label: '共同好友',
    hint: '显示你与站点机器人之间的共同好友数量（VRChat 只开放这一层共同好友数据）。',
    available: true,
  },
  {
    key: 'common_groups',
    label: '共同社群',
    hint: '只显示你和查看者都在的公开社群，最多 3 个；双方都需要绑定并开启。',
    available: true,
  },
  {
    key: 'worlds',
    label: '常驻 World',
    hint: '展示最多 3 个；自动读取主页 World，也可以手动补充。',
    available: true,
  },
]

export const DISCLOSURE_DEFAULT = Object.fromEntries(
  TRUST_DISCLOSURE.map((item) => [item.key, false]),
)

const PLATFORM_LABELS = {
  standalonewindows: 'PC',
  android: 'Quest / Android',
  quest: 'Quest',
  ios: 'iOS',
  web: 'Web',
}

export function platformLabel(value) {
  if (!value) return ''
  return PLATFORM_LABELS[String(value).toLowerCase()] || value
}

// 徽章只承担「快速判断」；未验证时绝不伪造 Trust Rank / 账号年龄。
export function trustSummary(trust) {
  if (!trust || !trust.bound) return null
  const verified = Boolean(trust.verified)
  const level = verified
    ? TRUST_RANK_LABELS[trust.trust_rank] || '已验证'
    : '未验证'
  const levelColor = verified
    ? trust.trust_rank_color || TRUST_RANK_COLORS[trust.trust_rank] || TRUST_RANK_COLORS.unknown
    : TRUST_RANK_COLORS.unknown
  const name = trust.display_name || ''
  const accountAge = verified && trust.account_age_label ? trust.account_age_label : ''
  const platform = verified && trust.platform ? platformLabel(trust.platform) : ''
  const parts = []
  if (name) parts.push(name)
  parts.push(level)
  if (accountAge) parts.push(`账号 ${accountAge}`)
  if (platform) parts.push(platform)
  return {
    name,
    level,
    levelColor,
    verified,
    trustRank: trust.trust_rank || null,
    accountAge,
    platform,
    text: name ? parts.join(' · ') : ['已绑定 VRChat', ...parts].join(' · '),
    source: verified
      ? `由 VRChat 简介验证码验证${trust.stale ? '；资料可能已过期，建议刷新' : ''}，不构成平台担保。`
      : '未验证：由本人手动填写，不构成平台担保。',
    stale: Boolean(trust.stale),
  }
}

export function commonFriendsText(trust) {
  const count = trust?.common_friends
  if (count === null || count === undefined) return ''
  return count > 0 ? `站点共同好友 ${count} 位` : '暂无站点共同好友'
}

export function commonGroupsText(trust) {
  const groups = Array.isArray(trust?.common_groups) ? trust.common_groups : []
  const names = groups.map((group) => group?.name).filter(Boolean)
  return names.length ? `共同社群：${names.join('、')}` : ''
}

export function worldNames(trust) {
  const worlds = Array.isArray(trust?.worlds) ? trust.worlds : []
  return worlds
    .map((world) => (typeof world === 'string' ? world : world?.name))
    .filter(Boolean)
}

export function disclosureCount(disclosure) {
  if (!disclosure) return 0
  return TRUST_DISCLOSURE.filter((item) => disclosure[item.key]).length
}

// 只允许白名单 key 的布尔值进入请求体，避免把 UI 状态误发给后端。
export function disclosurePatch(disclosure) {
  return Object.fromEntries(
    TRUST_DISCLOSURE.map((item) => [item.key, Boolean(disclosure?.[item.key])]),
  )
}
