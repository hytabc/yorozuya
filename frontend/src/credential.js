// 凭证与作品集的纯展示逻辑：组件与 node --test 共用。
export const VISIBILITY_LABELS = { public: '公开', link: '仅链接', private: '私有' }
export const VISIBILITY_HINTS = {
  public: '任何人都能查看，并会出现在你的作品集凭证墙里。',
  link: '只有拿到链接的人能查看；不会出现在作品集列表里。',
  private: '只有你自己能查看。',
}
export const VISIBILITY_OPTIONS = ['link', 'public', 'private']

// 编号由服务端按 WS-{年份}-{6 位序号} 生成；前端只做展示与格式校验。
export const SERIAL_PATTERN = /^WS-\d{4}-\d{6}$/

export function isSerialValid(serial) {
  return SERIAL_PATTERN.test(serial || '')
}

export function truncate(text, max = 40) {
  const value = String(text ?? '')
  if (max <= 0 || value.length <= max) return value
  return `${value.slice(0, Math.max(0, max - 1))}…`
}

export function credentialMeta(credential) {
  if (!credential) return []
  const rows = [
    ['委托标题', credential.title || '—'],
    ['委托类型', credential.category || '—'],
    ['委托方', credential.publisher || '—'],
    ['接单人', credential.taker || '—'],
    ['完成时间', credential.completed_at || '—'],
    ['签发时间', credential.issued_at || '—'],
  ]
  if (credential.skills?.length) rows.splice(2, 0, ['技能栈', credential.skills.join(' / ')])
  if (credential.platforms?.length) rows.splice(3, 0, ['平台', credential.platforms.join(' / ')])
  return rows.map(([label, value]) => ({ label, value }))
}

export function portfolioTagLabel(tag) {
  return `${tag.value} · ${tag.count} 次完成`
}

// 作品集只展示公开且未撤销的凭证；其余凭证只有本人能看。
export function isPublicCredential(credential) {
  return Boolean(credential) && credential.visibility === 'public' && !credential.revoked
}

export function formatIssued(credential) {
  const raw = credential?.issued_at
  if (!raw) return ''
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'long' }).format(date)
}
