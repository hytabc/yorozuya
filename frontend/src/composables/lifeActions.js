// 互动动作规则。LIFE_ACTIONS 为内置默认数据;游戏加载内容包后经
// setLifeActions 注入包数据,resolveLifeAction 读取当前数据。
import { shallowRef } from 'vue'

export const LIFE_ACTIONS = Object.freeze([
  { id: 'headpat', label: '摸摸头', reward: 2, threshold: 0, reply: '轻轻笑了一下：“嗯……谢谢你。”' },
  { id: 'poke', label: '戳戳脸', reward: 1, threshold: 0, reply: '侧过脸笑着说：“被你发现我在发呆啦。”' },
  { id: 'kiss', label: '亲亲', reward: 3, threshold: 30, reply: '有些害羞地笑了：“这个小小的心意，我收到了。”' },
])

const actionsData = shallowRef(LIFE_ACTIONS)

export function setLifeActions(actions) {
  if (Array.isArray(actions) && actions.length) actionsData.value = actions
}
export const currentLifeActions = () => actionsData.value

// Pure, immutable daily ledger: game day -> NPC -> action -> awarded.
export function resolveLifeAction({ ledger = {}, day, npcId, bond, actionId }) {
  const action = actionsData.value.find(item => item.id === actionId)
  if (!action || !Number.isInteger(day) || day < 1 || !npcId || !Number.isFinite(bond)) return { allowed: false, reason: '动作不可用' }
  if (bond < action.threshold) return { allowed: false, reason: `需要好感度达到 ${action.threshold}（当前 ${bond}）` }
  const key = String(day)
  const repeated = ledger[key]?.[npcId]?.[actionId] === true
  const newBond = Math.min(100, Math.max(0, bond) + (repeated ? 0 : action.reward))
  const nextLedger = repeated ? ledger : {
    ...ledger,
    [key]: { ...ledger[key], [npcId]: { ...ledger[key]?.[npcId], [actionId]: true } },
  }
  return { allowed: true, repeated, reward: newBond - bond, bond: newBond, ledger: nextLedger, action }
}
