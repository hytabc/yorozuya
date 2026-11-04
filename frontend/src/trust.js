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
    hint: '需要双方都绑定并开启；当前版本暂不提供。',
    available: false,
  },
  {
    key: 'common_groups',
    label: '共同社群',
    hint: '只展示双方共同的公开 Group；当前版本暂不提供。',
    available: false,
  },
  {
    key: 'worlds',
    label: '常驻 World',
    hint: '最多展示 3 个；当前版本暂不提供。',
    available: false,
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
  const name = trust.display_name || ''
  const parts = []
  if (name) parts.push(name)
  parts.push(level)
  if (verified && trust.account_age_label) parts.push(`账号 ${trust.account_age_label}`)
  if (verified && trust.platform) parts.push(platformLabel(trust.platform))
  return {
    name,
    level,
    verified,
    trustRank: trust.trust_rank || null,
    text: name ? parts.join(' · ') : ['已绑定 VRChat', ...parts].join(' · '),
    source: verified
      ? `由 VRChat 简介验证码验证${trust.stale ? '；资料可能已过期，建议刷新' : ''}，不构成平台担保。`
      : '未验证：由本人手动填写，不构成平台担保。',
    stale: Boolean(trust.stale),
  }
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
