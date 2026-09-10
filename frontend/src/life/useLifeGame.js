// 虚拟人生游戏状态与业务逻辑。从 LifeSimulator.vue 抽离，行为不变。
// 持有全部游戏状态、存档接线与 UI 状态；展示组件通过 props.game 消费。
// 阶段 2 起内容(NPC/剧本/初始数据)一律经 Registry 的活动 Pack 提供。
// 阶段 4b 起挂载时先拉取站点活动 Pack(站长配置),失败回退内置 Pack;
// 世界/房间/在场/动作数据注入 lifePresence/lifeActions 规则层。
// 阶段 4c 起对话走节点图引擎:选项 effects 显式生效,next 非空当天推进,
// 对话进度(dialogueNodes)随存档持久化。
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useLifeSave } from '../composables/lifeSave'
import { createLifePlayback } from '../composables/lifePlayback'
import { resolveLifeAction, setLifeActions, currentLifeActions } from '../composables/lifeActions'
import { presenceFor, sceneRoster, canInteract, planJoin, roomFor, worldFor, roomDecision, migrateSocialState, friendshipDecision, setLifePresenceData, currentRooms } from '../composables/lifePresence'
import { scriptForDay, nodeFor, startMessages, resolveDialogueChoice, sanitizeDialogueNodes, groupMessages, pickFallbackReply } from '../composables/lifeDialogue'
import { eventScriptForDay, eventsForRoom, isEventDone, applyEventChoice, normalizeEventProgress } from '../composables/lifeEvents'
import './builtin'
import { getActiveLifePack, portraitFor, effectText } from './registry'
import { loadActiveLifePack } from './packLoader'
import { resolveEnding, startRoomIdOf } from './endings'

export function useLifeGame() {
  let pack = getActiveLifePack()
  // 响应式修订号:applyPack 换包后,依赖包内容的 computed 强制重算。
  const packRev = ref(0)
  const initial = pack.createInitialState()

  // ==== 玩家人生数据 ====
  const day = ref(initial.day)
  const npcListOpen = ref(false)
  const tutorialDemo = ref(false)
  const currentRoomId = ref(startRoomIdOf(pack))
  const friendIds = ref([])
  const interactedNpcIds = ref([])
  const stats = ref(initial.stats)
  const tags = ref(initial.tags)
  const currentWorld = ref(initial.currentWorld)
  const unlockedWorlds = ref(initial.unlockedWorlds)

  // ==== 当前世界人物 ====
  const npcs = ref(pack.npcs.map(npc => ({ ...npc })))
  const currentNpcId = ref(pack.npcIds[0])

  const friends = computed(() => npcs.value.filter(n => friendIds.value.includes(n.id)))
  const sceneNpcs = computed(() => sceneRoster(npcs.value, currentRoomId.value))
  const worldPopulation = computed(() => (roomFor(currentRoomId.value)?.occupants || 0) + 1)
  const currentRoom = computed(() => roomFor(currentRoomId.value))
  const currentWorldDef = computed(() => {
    const room = roomFor(currentRoomId.value)
    return room ? worldFor(room.worldId) : null
  })
  const currentNpc = computed(() => npcs.value.find(n => n.id === currentNpcId.value))
  const actions = computed(() => currentLifeActions())
  // 条件结局:实时按当前属性/好感匹配,换包后重算。
  const ending = computed(() => {
    packRev.value
    return resolveEnding(pack, { stats: stats.value, npcs: npcs.value })
  })

  // ==== 对话历史(每个 NPC 独立保存) ====
  const conversations = ref(initial.conversations)

  // ==== 当前对话节点(阶段 4c 节点图引擎) ====
  // 房间事件只记录当日完成项；播放中的事件属于展示态，不写入存档。
  const eventProgress = ref(normalizeEventProgress(undefined, day.value))
  const activeEvent = ref(null)
  const roomEvents = computed(() => {
    packRev.value // 换包后重算
    return eventsForRoom(pack.events, currentRoomId.value).map(event => ({
      ...event, done: isEventDone(eventProgress.value, day.value, event.id),
    }))
  })
  function openEvent(eventId) {
    if (!saveReady.value || saveConflict.value || activeEvent.value) return
    const event = eventsForRoom(pack.events, currentRoomId.value).find(item => item.id === eventId)
    if (!event || isEventDone(eventProgress.value, day.value, eventId)) return
    const script = eventScriptForDay(event, day.value)
    if (!script) return
    cancelPresentation()
    activeEvent.value = { event, script }
  }
  function closeEvent() {
    activeEvent.value = null
  }
  function finishEvent(effects = {}) {
    if (!saveReady.value || saveConflict.value || !activeEvent.value) return
    const eventId = activeEvent.value.event.id
    if (isEventDone(eventProgress.value, day.value, eventId)) { closeEvent(); return }
    stats.value = applyEventChoice(stats.value, effects.stats)
    const parts = [effectText({ stats: effects.stats })].filter(Boolean)
    for (const [npcId, value] of Object.entries(effects.bonds || {})) {
      const npc = npcs.value.find(n => n.id === npcId)
      if (!npc || !value) continue
      npc.bond = Math.max(0, Math.min(100, npc.bond + value))
      parts.push(`${npc.name} 好感 ${value > 0 ? '+' : ''}${value}`)
    }
    eventProgress.value = normalizeEventProgress(eventProgress.value, day.value)
    eventProgress.value.done.push(eventId)
    closeEvent()
    showToast('✦ ' + (parts.join(' · ') || '已记录'))
    markChanged()
  }

  const dialogueNodes = ref({})
  const currentDialogue = computed(() => {
    packRev.value // 换包后重算
    const script = scriptForDay(pack.dialogue[currentNpcId.value], day.value)
    return script ? nodeFor(script, dialogueNodes.value[currentNpcId.value]) : null
  })
  const currentConversation = computed(() => conversations.value[currentNpcId.value] || [])

  const completed = ref({})
  const actionLedger = ref({})
  const replyTab = ref('dialogue')
  const actionFeedback = ref('')
  const bondDelta = ref(0)
  let bondFeedbackTimer
  function showBondGain(delta) {
    clearTimeout(bondFeedbackTimer)
    bondDelta.value = delta
    if (delta > 0) bondFeedbackTimer = setTimeout(() => { bondDelta.value = 0 }, 4000)
  }
  function actionState(action) {
    return resolveLifeAction({ ledger: actionLedger.value, day: day.value, npcId: currentNpcId.value, bond: currentNpc.value.bond, actionId: action.id })
  }
  function performAction(action) {
    if (!saveReady.value || saveConflict.value || speech.value.playing || !dialogueVisible.value || !canInteract(currentNpcId.value, currentRoomId.value)) return
    const result = actionState(action)
    if (!result.allowed) return
    const npc = currentNpc.value
    if (!interactedNpcIds.value.includes(npc.id)) interactedNpcIds.value.push(npc.id)
    npc.bond = result.bond
    showBondGain(result.reward)
    actionLedger.value = result.ledger
    const text = `（对${npc.name}${action.label}）`
    const reply = `${npc.name}${action.reply}`
    conversations.value[npc.id].push(
      { from: 'player', text, day: day.value, time: '18:20' },
      { from: 'npc', text: reply, day: day.value, time: '18:20' },
    )
    actionFeedback.value = result.repeated ? '今天已获得该动作奖励，本次仍可互动，好感不再增加。' :
      result.reward ? `今日首次${action.label} · 好感 +${result.reward}` : '今日首次互动已记录 · 好感已达上限 100'
    diaryHistory.value.unshift({ day: day.value, text: `${text} ${actionFeedback.value}`, mood: '亲近' })
    markChanged()
    playback.play([{ from: 'player', text }, { from: 'npc', text: reply }])
  }
  const pending = ref({})
  const dialogueVisible = ref(false)
  const speech = ref({ from: 'npc', text: '', typing: false, playing: false })
  const playback = createLifePlayback(value => { speech.value = value }, {
    reducedMotion: () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  })
  const npcPortrait = computed(() => {
    packRev.value // 换包后重算
    return portraitFor(currentNpcId.value)
  })
  const showChoices = computed(() => dialogueVisible.value && !speech.value.playing && !completed.value[currentNpcId.value] && !pending.value[currentNpcId.value])
  function cancelPresentation() {
    closeEvent()
    playback.stop()
    showBondGain(0)
    dialogueVisible.value = false
  }
  let toastTimer
  onBeforeUnmount(() => {
    cancelPresentation()
    clearTimeout(toastTimer)
  })
  const toast = ref('')

  function showToast(msg) {
    toast.value = msg
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => { toast.value = '' }, 2000)
  }

  function switchNpc(npcId) {
    if (!saveReady.value || saveConflict.value || !canInteract(npcId, currentRoomId.value)) return
    cancelPresentation()
    currentNpcId.value = npcId
    actionFeedback.value = ''
    const conv = conversations.value[npcId]
    if (completed.value[npcId] === true) {
      dialogueVisible.value = true
      // 配置始终取活动包,好感取玩家状态,兼容缺少默认回复字段的旧存档。
      const replies = pack.npcs.find(npc => npc.id === npcId)?.fallbackReplies
      const text = pickFallbackReply(replies, currentNpc.value.bond)
      if (text !== null) {
        const reply = { from: 'npc', text, day: day.value, time: '18:20' }
        conv.push(reply)
        markChanged()
        playback.play([reply])
      } else {
        // 无可用台词仍保存人物切换,但不重播已说过的回复。
        markChanged()
      }
      return
    }
    if (conv.length === 1) {
      conv.push(...startMessages(scriptForDay(pack.dialogue[npcId], day.value), day.value))
    }
    dialogueVisible.value = true
    const latest = [...conv].reverse().find(msg => msg.from === 'npc')
    if (latest) playback.play([latest])
    markChanged()
  }

  function chooseOption(choice) {
    if (!saveReady.value || saveConflict.value || !showChoices.value || !canInteract(currentNpcId.value, currentRoomId.value)) return
    const npcId = currentNpcId.value
    if (!interactedNpcIds.value.includes(npcId)) interactedNpcIds.value.push(npcId)
    const sentDay = day.value
    pending.value[npcId] = true
    conversations.value[npcId].push({
      from: 'player',
      text: choice.label,
      day: day.value,
      time: '18:20',
    })

    // 节点图引擎:effects 显式生效,不再从文案解析。
    const result = resolveDialogueChoice(scriptForDay(pack.dialogue[npcId], day.value), choice)
    for (const [k, v] of Object.entries(result.stats)) {
      stats.value[k] = Math.max(0, Math.min(100, stats.value[k] + v))
    }
    const npc = npcs.value.find(n => n.id === npcId)
    if (npc && result.bond) {
      const previousBond = npc.bond
      npc.bond = Math.min(100, npc.bond + result.bond)
      showBondGain(npc.bond - previousBond)
    }
    showToast('✦ ' + (effectText(choice.effects) || '已记录'))

    // 回复消息组(8a 多句连播;图片挂最后一句)。完整轮次原子写入,导航不丢回复。
    const replyMsgs = groupMessages(result.replies, result.replyImage, sentDay)
    conversations.value[npcId].push(...replyMsgs)
    const currentNode = nodeFor(scriptForDay(pack.dialogue[npcId], day.value), dialogueNodes.value[npcId])
    const played = [{ from: 'player', text: choice.label, bg: result.replyImage || currentNode.image || null }, ...replyMsgs]
    if (result.done) {
      delete dialogueNodes.value[npcId]
      completed.value[npcId] = true
    } else {
      // next 非空:当天推进到下一节点,NPC 接着说下一节点台词组。
      dialogueNodes.value[npcId] = result.nextNodeId
      const nextMsgs = groupMessages(result.nextLines, result.nextImage, sentDay)
      conversations.value[npcId].push(...nextMsgs)
      played.push(...nextMsgs)
    }
    pending.value[npcId] = false
    diaryHistory.value.unshift({ day: sentDay, text: `${currentNpc.value.name}：${choice.label}`, mood: '日常' })
    markChanged()
    playback.play(played)
  }

  // ==== 对话历史记录 ====
  const showHistory = ref(false)
  const historyNpcId = ref(pack.npcIds[0])
  const historyConversation = computed(() => conversations.value[historyNpcId.value] || [])

  function openHistory() {
    historyNpcId.value = currentNpcId.value
    showHistory.value = true
  }

  // ==== 世界/手记面板 ====
  const panel = ref('')
  const profileId = ref('')
  const profileNpc = computed(() => npcs.value.find(npc => npc.id === profileId.value))
  const profilePresence = computed(() => presenceFor(profileId.value))
  const profileJoin = computed(() => friendIds.value.includes(profileId.value) ? planJoin(profileId.value) : { allowed: false, reason: '添加好友后才能通过资料跟随加入' })
  const profileRoom = computed(() => roomFor(profilePresence.value.roomId))
  const profileAdd = computed(() => friendshipDecision(profileId.value, profileNpc.value?.bond || 0, interactedNpcIds.value, friendIds.value))
  const selectedWorldId = ref(pack.worlds[0].id)
  const selectedWorld = computed(() => worldFor(selectedWorldId.value))
  const visibleRooms = computed(() => currentRooms().filter(r => r.worldId === selectedWorldId.value))
  function addFriend() {
    if (!saveReady.value || saveConflict.value || !profileAdd.value.allowed) return
    friendIds.value.push(profileId.value)
    markChanged()
    showToast(profileNpc.value.name + '已接受好友申请')
  }
  function selectFriend(npcId) {
    profileId.value = npcId
    panel.value = 'profile'
  }
  function joinFriend() {
    if (!profileJoin.value.allowed) return
    enterRoom(profileJoin.value.roomId)
  }
  function exploreWorld(world) {
    selectedWorldId.value = world.id
    panel.value = 'rooms'
  }
  function enterRoom(roomId) {
    if (!saveReady.value || saveConflict.value) return
    const access = roomDecision(roomFor(roomId))
    if (!access.allowed) { showToast(access.reason); return }
    cancelPresentation()
    currentRoomId.value = roomId
    currentWorld.value = access.world
    panel.value = ''
    npcListOpen.value = false
    actionFeedback.value = ''
    markChanged()
    showToast('已进入' + access.world + ' ' + roomFor(roomId).label + '，点击房间人物交谈')
  }

  const diaryHistory = ref(initial.diary)

  // ==== 新手引导接线(展示态快照与恢复) ====
  let tutorialUi = null
  function prepareTutorial(view) {
    if (!tutorialUi) tutorialUi = { panel: panel.value, npcListOpen: npcListOpen.value, showHistory: showHistory.value, profileId: profileId.value, selectedWorldId: selectedWorldId.value }
    // Presentation only: never call switchNpc, choices, actions, travel or save.
    panel.value = ''; showHistory.value = false; tutorialDemo.value = false
    if (view === 'roster') npcListOpen.value = true
    if (view === 'demo') { tutorialDemo.value = true }
    if (view === 'history') showHistory.value = true
    if (['worlds', 'friends', 'diary'].includes(view)) panel.value = view
    if (view === 'rooms') { selectedWorldId.value = currentRoom.value?.worldId || pack.worlds[0].id; panel.value = 'rooms' }
    if (view === 'profile') { profileId.value = sceneNpcs.value[0]?.id || npcs.value[0]?.id; panel.value = 'profile' }
  }
  function closeTutorial() {
    tutorialDemo.value = false
    if (!tutorialUi) return
    panel.value = tutorialUi.panel; npcListOpen.value = tutorialUi.npcListOpen
    showHistory.value = tutorialUi.showHistory; profileId.value = tutorialUi.profileId; selectedWorldId.value = tutorialUi.selectedWorldId
    tutorialUi = null
  }

  // ==== 内容包应用(阶段 4b):站点活动 Pack 到达后整体重建初始状态 ====
  function applyPack(nextPack) {
    pack = nextPack
    packRev.value += 1
    setLifePresenceData({ worlds: pack.worlds, rooms: pack.rooms, presence: pack.presence })
    setLifeActions(pack.actions)
    const fresh = pack.createInitialState()
    day.value = fresh.day
    eventProgress.value = normalizeEventProgress(undefined, day.value)
    closeEvent()
    stats.value = fresh.stats
    tags.value = fresh.tags
    currentWorld.value = fresh.currentWorld
    unlockedWorlds.value = fresh.unlockedWorlds
    currentRoomId.value = startRoomIdOf(pack)
    friendIds.value = []
    interactedNpcIds.value = []
    npcs.value = pack.npcs.map(npc => ({ ...npc }))
    currentNpcId.value = pack.npcIds[0]
    conversations.value = fresh.conversations
    diaryHistory.value = fresh.diary
    completed.value = {}
    actionLedger.value = {}
    pending.value = {}
    dialogueNodes.value = {}
    historyNpcId.value = pack.npcIds[0]
    selectedWorldId.value = pack.worlds[0].id
    actionFeedback.value = ''
  }

  function snapshot() {
    return JSON.parse(JSON.stringify({
      schemaVersion: 2, packId: pack.id, day: day.value, stats: stats.value, tags: tags.value,
      currentWorld: currentWorld.value, unlockedWorlds: unlockedWorlds.value,
      // 默认回复属于内容包配置,不写入只接受人物状态字段的存档模型。
      currentNpcId: currentNpcId.value, npcs: npcs.value.map(({ fallbackReplies, ...npc }) => npc),
      conversations: conversations.value, diary: diaryHistory.value, completed: completed.value,
      actionLedger: actionLedger.value, dialogueNodes: dialogueNodes.value,
      eventProgress: eventProgress.value,
      currentRoomId: currentRoomId.value, friendIds: friendIds.value, interactedNpcIds: interactedNpcIds.value,
    }))
  }
  function hydrate(state) {
    cancelPresentation()
    // v1 为无 packId 的旧存档;v2 必须声明当前活动 Pack。
    if (![1, 2].includes(state.schemaVersion) || !state.npcs?.length ||
        state.npcs.some(n => !pack.dialogue[n.id]) ||
        !state.npcs.some(n => n.id === state.currentNpcId)) throw new Error('存档版本或人物不兼容')
    if (state.packId && state.packId !== pack.id) throw new Error('存档内容包与当前站点内容不匹配')
    day.value = state.day
    stats.value = state.stats
    tags.value = state.tags
    const social = migrateSocialState(state)
    currentRoomId.value = social.currentRoomId
    friendIds.value = social.friendIds
    interactedNpcIds.value = social.interactedNpcIds
    currentWorld.value = worldFor(roomFor(currentRoomId.value).worldId).name
    unlockedWorlds.value = state.unlockedWorlds
    currentNpcId.value = state.currentNpcId
    npcs.value = state.npcs
    conversations.value = state.conversations
    diaryHistory.value = state.diary
    completed.value = state.completed
    actionLedger.value = state.actionLedger || {}
    dialogueNodes.value = sanitizeDialogueNodes(pack.dialogue, state.dialogueNodes)
    eventProgress.value = normalizeEventProgress(state.eventProgress, day.value)
    actionFeedback.value = ''
    pending.value = {}
  }
  const {
    ready: saveReady, saving: saveBusy, dirty: saveDirty, error: saveError,
    conflict: saveConflict, savedAt, changed: markChanged, flush: flushSave, load: reloadSave,
  } = useLifeSave(snapshot, hydrate, { autoLoad: false })
  async function save() {
    if (!saveReady.value || saveConflict.value) return
    markChanged()
    if (await flushSave()) showToast('存档已保存到服务器')
  }
  function reloadConfirmed() {
    if (!saveDirty.value || window.confirm('重新载入会丢弃尚未保存的本地修改，继续吗？')) reloadSave()
  }

  // 挂载后先确定站点活动内容包,再载入存档(存档校验依赖活动 Pack)。
  onMounted(async () => {
    applyPack(await loadActiveLifePack())
    reloadSave()
  })

  function nextDay() {
    if (!saveReady.value || saveConflict.value || day.value >= 7) return
    day.value += 1
    eventProgress.value = normalizeEventProgress(eventProgress.value, day.value)
    stats.value.energy = Math.min(100, stats.value.energy + 10)
    cancelPresentation()
    pending.value = {}
    completed.value = {}
    dialogueNodes.value = {}
    for (const npcId in conversations.value) {
      conversations.value[npcId].push(...startMessages(scriptForDay(pack.dialogue[npcId], day.value), day.value))
    }
    markChanged()
    showToast('新的一天开始了，精力恢复了 10 点')
  }

  function resetToday() {
    if (!saveReady.value || saveConflict.value) return
    cancelPresentation()
    completed.value = {}
    pending.value = {}
    dialogueNodes.value = {}
    eventProgress.value = { day: day.value, done: [] }
    activeEvent.value = null
    // 测试用：只清空当天进度，天数、属性、好感、好友与手记不回滚。
    actionLedger.value = {}
    actionFeedback.value = ''
    const fresh = pack.createInitialState()
    conversations.value = Object.fromEntries(npcs.value.map(npc => {
      const greeting = fresh.conversations[npc.id]?.[0]
      return [npc.id, [
        ...(greeting ? [{ ...greeting, day: day.value }] : []),
        ...startMessages(scriptForDay(pack.dialogue[npc.id], day.value), day.value),
      ]]
    }))
    showToast('↺ 已重置今天：对话、事件与动作奖励都可重玩')
    markChanged()
  }

  // 结局后的「重新开始」:整段人生回到第 1 天初始态,并立即落库。
  // 与 resetToday 不同:天数、属性、好感、好友、手记、对话全部回滚。
  async function restartJourney() {
    if (!saveReady.value || saveConflict.value) return
    applyPack(pack)
    markChanged()
    if (await flushSave()) showToast('🌱 已重新开始：回到第 1 天')
  }

  return {
    // 状态
    day, stats, tags, currentWorld, unlockedWorlds, npcs, currentNpcId,
    conversations, completed, actionLedger, pending, diaryHistory, dialogueNodes,
    currentRoomId, friendIds, interactedNpcIds, eventProgress, activeEvent, roomEvents,
    // 计算
    friends, sceneNpcs, worldPopulation, currentRoom, currentWorldDef, currentNpc, currentDialogue,
    historyConversation, profileNpc, profilePresence, profileJoin, profileRoom,
    profileAdd, selectedWorld, visibleRooms, npcPortrait, showChoices, actions, ending,
    // UI 状态
    npcListOpen, tutorialDemo, replyTab, actionFeedback, bondDelta, dialogueVisible,
    speech, playback, showHistory, historyNpcId, panel, profileId, selectedWorldId, toast,
    // 动作
    actionState, performAction, switchNpc, chooseOption, openHistory,
    openEvent, closeEvent, finishEvent,
    addFriend, selectFriend, joinFriend, exploreWorld, enterRoom, nextDay, resetToday, restartJourney,
    cancelPresentation, showToast, showBondGain, portraitFor,
    // 引导
    prepareTutorial, closeTutorial,
    // 存档
    snapshot, hydrate, save, reloadConfirmed,
    saveReady, saveBusy, saveDirty, saveError, saveConflict, savedAt,
    markChanged, flushSave, reloadSave,
  }
}
