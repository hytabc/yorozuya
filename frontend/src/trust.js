// VRChat 信任信息的展示规则：纯逻辑，组件与测试共用。
// 与后端 backend/app/trust.py 的 DISCLOSURE_KEYS 保持一致。

export const TRUST_DISCLOSURE = [
  {
    key: 'identity',
    label: '显示名与主页链接',
    hint: '展示你手动填写的 VRChat 显示名与个人主页。',
    available: true,
  },
  {
    key: 'trust_rank',
    label: 'Trust Rank',
    hint: '需要接入 VRChat 同步后才会显示；当前即使开启也不会有数据。',
    available: false,
  },
  {
    key: 'account_age',
    label: '账号年龄',
    hint: '需要接入 VRChat 同步后才会显示；当前即使开启也不会有数据。',
    available: false,
  },
  {
    key: 'common_friends',
    label: '共同好友',
    hint: '需要双方都接入同步并同时开启；当前不可用。',
    available: false,
  },
  {
    key: 'common_groups',
    label: '共同社群',
    hint: '只展示双方共同的公开 Group；当前不可用。',
    available: false,
  },
  {
    key: 'worlds',
    label: '常驻 World',
    hint: '最多展示 3 个；当前不可用。',
    available: false,
  },
]

export const DISCLOSURE_DEFAULT = Object.fromEntries(
  TRUST_DISCLOSURE.map((item) => [item.key, false]),
)

// 徽章只承担「快速判断」，永不伪造 Trust Rank / 账号年龄。
export function trustSummary(trust) {
  if (!trust || !trust.bound) return null
  const level = '未验证'
  const name = trust.display_name || ''
  return {
    name,
    level,
    text: name ? `${name} · ${level}` : `已绑定 VRChat · ${level}`,
    source: '由本人手动填写，未经验证；不构成平台担保。',
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
