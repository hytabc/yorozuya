/**
 * 《糖霜世界》游戏状态：关卡状态机 + 进度/存档。
 * 视图只做展示，全部逻辑收口在此。
 */
import { computed, ref, watch } from 'vue'

import {
  ACHIEVEMENTS,
  ALL_DESIGN_ENDING_IDS,
  CHAPTERS,
  CHARACTERS,
  ENDING_META,
  GLOBAL_ENDINGS,
  LEVELS,
  LEVEL_BY_ID,
  LEVEL_META_BY_ID,
  LEVELS_BY_CHAPTER,
} from './levels.js'
import { DEFAULT_SETTINGS } from './engine/constants.js'
import { computeChainValence, computeCoherence } from './engine/scoring.js'
import { judgeChain } from './engine/judge.js'
import { computeDraggable, detectButterflies, resolveHiddenFragments } from './engine/butterfly.js'
import { getHint, getRuleHint, resolveHintTier } from './engine/hints.js'
import { matchConstraint } from './engine/constraints.js'
import { achievementPoints, endingEntries, evaluateAchievements } from './achievements.js'
import { useFrostSave } from './frostSave.js'

const BOND_KEYS = ['Mio', 'Shiori', 'Rin', 'Yu']

function emptyProgress() {
  return {
    cleared: [],
    endingsSeen: [],
    butterfliesSeen: [],
    bond: { Mio: 0, Shiori: 0, Rin: 0, Yu: 0 },
    hintsUsed: {},
    fails: {},
    attempts: {},
    chaosCount: 0,
    lastLevel: null,
    settings: { ...DEFAULT_SETTINGS },
  }
}

function clamp(value, lo, hi) {
  return Math.min(hi, Math.max(lo, value))
}

export function useFrostGame() {
  const progress = ref(emptyProgress())

  // ---- 界面/关卡状态机 ----
  const screen = ref('chapters')
  const currentLevelId = ref(null)
  const chain = ref([])
  const phase = ref('reading')
  const undoStack = ref([])
  const result = ref(null)
  const overlayVisible = ref(false)
  const endingAlreadySeen = ref(false)
  const globalEnding = ref(null)
  const butterfly = ref(null)
  const pendingButterflies = ref([])
  const hintVisible = ref(false)
  const ruleVisible = ref(false)
  const toast = ref('')

  const currentLevel = computed(() => (currentLevelId.value ? LEVEL_BY_ID[currentLevelId.value] : null))

  const canEdit = computed(() => ['reading', 'arranging', 'previewing'].includes(phase.value))
  const canSubmit = computed(() => canEdit.value && chain.value.length > 2)

  const draggable = computed(() => (currentLevel.value ? computeDraggable(chain.value, currentLevel.value) : new Set()))
  const coherence = computed(() => (currentLevel.value ? computeCoherence(chain.value, currentLevel.value) : 0))
  const valence = computed(() => (currentLevel.value ? computeChainValence(chain.value, currentLevel.value) : 0))

  const fragmentById = computed(() => {
    const map = {}
    for (const level of LEVELS) for (const f of level.fragments) map[f.id] = f
    return map
  })

  const chainFragments = computed(() => chain.value.map((id) => fragmentById.value[id]).filter(Boolean))

  const seenEndingEntries = computed(() => endingEntries(progress.value.endingsSeen))

  const unlockedEndingIds = computed(() => {
    const ids = []
    for (const endingId of progress.value.endingsSeen) {
      const meta = ENDING_META[endingId]
      if (meta) ids.push(`ending:${meta.levelId}:${meta.type}`)
    }
    return ids
  })

  const insights = computed(() => {
    if (!currentLevel.value) return []
    const unlocked = resolveHiddenFragments(currentLevel.value, {
      seenEndings: seenEndingEntries.value,
      triggeredButterflies: progress.value.butterfliesSeen,
    })
    return currentLevel.value.fragments
      .filter((f) => f.type === 'blue' && unlocked.includes(f.id))
  })

  const failCount = computed(() => (currentLevel.value ? progress.value.fails[currentLevel.value.id] || 0 : 0))
  const hintTier = computed(() => resolveHintTier(failCount.value))
  const currentHint = computed(() => {
    if (!hintVisible.value || !currentLevel.value || hintTier.value === 0) return null
    return getHint(currentLevel.value, hintTier.value)
  })
  const ruleHint = computed(() => (currentLevel.value ? getRuleHint(currentLevel.value) : ''))

  const achievements = computed(() => evaluateAchievements(progress.value))
  const achievementsPoints = computed(() => achievementPoints(achievements.value))
  const achievementsTotalPoints = ACHIEVEMENTS.reduce((sum, a) => sum + a.points, 0)

  // ---- 关卡列表 / 图鉴 ----
  const levelStates = computed(() =>
    LEVELS_BY_CHAPTER.map((chapter) => ({
      ...chapter,
      levels: chapter.levels.map((level) => {
        const meta = LEVEL_META_BY_ID[level.id] || {}
        const seen = progress.value.endingsSeen.filter((id) => ENDING_META[id]?.levelId === level.id)
        return {
          id: level.id,
          title: level.title,
          unlocked: isLevelUnlocked(level.id),
          cleared: progress.value.cleared.includes(level.id),
          seenCount: seen.length,
          totalCount: level.endings.length,
          isTutorial: Boolean(meta.isTutorial),
          isFinale: Boolean(meta.isFinale),
        }
      }),
    })),
  )

  const gallery = computed(() =>
    LEVELS_BY_CHAPTER.map((chapter) => ({
      ...chapter,
      levels: chapter.levels.map((level) => ({
        id: level.id,
        title: level.title,
        endings: level.endings.map((ending) => ({
          ...ending,
          seen: progress.value.endingsSeen.includes(ending.id),
        })),
      })),
    })),
  )

  const globalGallery = computed(() =>
    GLOBAL_ENDINGS.globalEndings.map((ending) => ({
      ...ending,
      seen: progress.value.endingsSeen.includes(ending.id),
    })),
  )

  const characters = computed(() =>
    CHARACTERS.map((character) => ({
      ...character,
      bond: progress.value.bond[character.id] ?? 0,
    })),
  )

  const bondList = computed(() =>
    CHARACTERS.filter((c) => BOND_KEYS.includes(c.id)).map((c) => ({
      id: c.id, name: c.name, bond: progress.value.bond[c.id] ?? 0,
    })),
  )

  const designEndingIds = new Set(ALL_DESIGN_ENDING_IDS)
  const totalEndingsSeen = computed(() => progress.value.endingsSeen.filter((id) => designEndingIds.has(id)).length)
  const totalDesignEndings = computed(() => LEVELS.reduce((sum, l) => sum + l.endings.length, 0))

  // ---- 存档 ----
  const save = useFrostSave(snapshot, hydrate)

  function snapshot() {
    const p = progress.value
    return {
      schemaVersion: 1,
      cleared: [...p.cleared],
      endingsSeen: [...p.endingsSeen],
      butterfliesSeen: [...p.butterfliesSeen],
      bond: { ...p.bond },
      hintsUsed: { ...p.hintsUsed },
      fails: { ...p.fails },
      attempts: { ...p.attempts },
      chaosCount: p.chaosCount,
      lastLevel: p.lastLevel,
      settings: { ...p.settings },
    }
  }

  function hydrate(state) {
    const p = emptyProgress()
    if (state) {
      p.cleared = Array.isArray(state.cleared) ? [...state.cleared] : []
      p.endingsSeen = Array.isArray(state.endingsSeen) ? [...state.endingsSeen] : []
      p.butterfliesSeen = Array.isArray(state.butterfliesSeen) ? [...state.butterfliesSeen] : []
      p.bond = { ...p.bond, ...(state.bond || {}) }
      p.hintsUsed = { ...(state.hintsUsed || {}) }
      p.fails = { ...(state.fails || {}) }
      p.attempts = { ...(state.attempts || {}) }
      p.chaosCount = state.chaosCount || 0
      p.lastLevel = state.lastLevel || null
      p.settings = { ...p.settings, ...(state.settings || {}) }
    }
    progress.value = p
  }

  function markChanged() {
    save.changed()
  }

  function isLevelUnlocked(id) {
    const meta = LEVEL_META_BY_ID[id]
    if (!meta || !meta.unlockAfter) return true
    return progress.value.cleared.includes(meta.unlockAfter)
  }

  function buildChain(level) {
    const base = level.initialOrder.slice()
    const unlocked = resolveHiddenFragments(level, {
      seenEndings: seenEndingEntries.value,
      triggeredButterflies: progress.value.butterfliesSeen,
    })
    const extras = level.fragments
      .filter((f) => f.hidden && f.type !== 'blue' && unlocked.includes(f.id) && !base.includes(f.id))
      .map((f) => f.id)
    if (extras.length === 0) return base
    return [...base.slice(0, -1), ...extras, base[base.length - 1]]
  }

  function enterLevel(id) {
    const level = LEVEL_BY_ID[id]
    if (!level || !isLevelUnlocked(id)) return
    currentLevelId.value = id
    chain.value = buildChain(level)
    undoStack.value = []
    phase.value = 'reading'
    result.value = null
    overlayVisible.value = false
    endingAlreadySeen.value = false
    globalEnding.value = null
    butterfly.value = null
    pendingButterflies.value = []
    hintVisible.value = false
    ruleVisible.value = false
    progress.value.lastLevel = id
    screen.value = 'level'
  }

  function showScreen(name) {
    screen.value = name
  }

  function pushUndo() {
    undoStack.value.push(chain.value.slice())
    if (undoStack.value.length > 20) undoStack.value.shift()
  }

  function move(from, to) {
    if (!canEdit.value) return
    const n = chain.value.length
    const fromC = clamp(from, 1, n - 2)
    const toC = clamp(to, 1, n - 2)
    if (fromC === toC) return
    pushUndo()
    const arr = chain.value.slice()
    const [item] = arr.splice(fromC, 1)
    arr.splice(toC, 0, item)
    chain.value = arr
    afterChange()
  }

  function moveBy(fragmentId, delta) {
    if (!canEdit.value) return
    const index = chain.value.indexOf(fragmentId)
    if (index < 0) return
    move(index, index + delta)
  }

  function moveToEdge(fragmentId, edge) {
    if (!canEdit.value) return
    const index = chain.value.indexOf(fragmentId)
    if (index < 0) return
    move(index, edge === 'start' ? 1 : chain.value.length - 2)
  }

  function undo() {
    if (!canEdit.value || undoStack.value.length === 0) return
    chain.value = undoStack.value.pop()
    phase.value = 'previewing'
  }

  function afterChange() {
    phase.value = 'previewing'
    checkButterflies()
  }

  function checkButterflies() {
    if (!currentLevel.value) return
    const hits = detectButterflies(chain.value, currentLevel.value, progress.value.butterfliesSeen)
    if (hits.length === 0) return
    for (const hit of hits) progress.value.butterfliesSeen.push(hit.id)
    pendingButterflies.value.push(...hits)
    if (!butterfly.value) butterfly.value = pendingButterflies.value.shift()
    markChanged()
  }

  function dismissButterfly() {
    butterfly.value = pendingButterflies.value.shift() || null
  }

  function submit() {
    if (!canSubmit.value || !currentLevel.value) return
    const level = currentLevel.value
    phase.value = 'settling'
    progress.value.attempts[level.id] = (progress.value.attempts[level.id] || 0) + 1
    markChanged()
    window.setTimeout(() => {
      const res = judgeChain(chain.value, level, { unlockedEndingIds: unlockedEndingIds.value })
      result.value = res
      endingAlreadySeen.value = !res.isChaos && progress.value.endingsSeen.includes(res.ending.id)
      if (res.isChaos) progress.value.chaosCount += 1
      const failed = res.isChaos || res.ending.type === 'bad'
      progress.value.fails[level.id] = failed ? (progress.value.fails[level.id] || 0) + 1 : 0
      markChanged()
      phase.value = 'revealing'
      window.setTimeout(() => { overlayVisible.value = true }, 650)
    }, 2000)
  }

  function retry() {
    overlayVisible.value = false
    result.value = null
    phase.value = 'arranging'
  }

  function applyBond(effect) {
    if (!effect) return
    for (const key of BOND_KEYS) {
      if (effect[key] === undefined) continue
      progress.value.bond[key] = clamp((progress.value.bond[key] || 0) + effect[key], -100, 100)
    }
  }

  function computeGlobalEnding(level) {
    const config = GLOBAL_ENDINGS
    const res = judgeChain(chain.value, level, { unlockedEndingIds: unlockedEndingIds.value })
    const levelScore = clamp(res.score / 100, 0, 1)
    const types = progress.value.endingsSeen.map((id) => ENDING_META[id]?.type).filter(Boolean)
    const goodCount = types.filter((t) => t === 'good').length
    const trueCount = types.filter((t) => t === 'true').length
    const bondMean = (progress.value.bond.Mio + progress.value.bond.Shiori + progress.value.bond.Rin) / 3
    const bondNorm = clamp((bondMean + 100) / 200, 0, 1)
    const score = 100 * (0.4 * levelScore + 0.2 * Math.min(goodCount, 9) / 9
      + 0.2 * Math.min(trueCount, 10) / 10 + 0.2 * bondNorm)

    let chosenId = null
    const override = (config.overrides || []).find((o) => o.endingId === 'global_give_away')
    if (override) {
      const conditionsOk = override.conditionConstraints.every((c) => matchConstraint(chain.value, c))
      const released = override.releaseEndingIds.filter((id) => progress.value.endingsSeen.includes(id)).length
      if (conditionsOk && released >= override.minReleaseCount) chosenId = override.endingId
    }
    if (!chosenId) {
      for (const threshold of config.thresholds) {
        if (score >= threshold.min) { chosenId = threshold.endingId; break }
      }
    }
    return config.globalEndings.find((e) => e.id === chosenId) || null
  }

  function keepEnding() {
    const level = currentLevel.value
    const res = result.value
    if (!level || !res) return
    if (!res.isChaos) {
      if (!progress.value.endingsSeen.includes(res.ending.id)) progress.value.endingsSeen.push(res.ending.id)
      if (!progress.value.cleared.includes(level.id)) progress.value.cleared.push(level.id)
      applyBond(res.ending.bondEffect)
    }
    const before = evaluateAchievements(progress.value)
    if (!res.isChaos && level.id === '4-3') {
      const ending = computeGlobalEnding(level)
      if (ending) {
        if (!progress.value.endingsSeen.includes(ending.id)) progress.value.endingsSeen.push(ending.id)
        globalEnding.value = ending
      }
    }
    const after = evaluateAchievements(progress.value)
    const newly = Object.keys(after).filter((id) => after[id] && !before[id])
    if (newly.length) {
      const titles = newly.map((id) => ACHIEVEMENTS.find((a) => a.id === id)?.title).filter(Boolean)
      toast.value = `成就解锁：${titles.join('、')}`
    }
    progress.value.lastLevel = level.id
    markChanged()
    overlayVisible.value = false
    result.value = null
    if (globalEnding.value) return
    screen.value = 'chapters'
  }

  function closeGlobalEnding() {
    globalEnding.value = null
    screen.value = 'chapters'
  }

  function backToChapters() {
    overlayVisible.value = false
    result.value = null
    phase.value = 'reading'
    screen.value = 'chapters'
  }

  function openHint() {
    if (!currentLevel.value) return
    hintVisible.value = true
    progress.value.hintsUsed[currentLevel.value.id] = (progress.value.hintsUsed[currentLevel.value.id] || 0) + 1
    markChanged()
  }

  function closeHint() {
    hintVisible.value = false
  }

  function openRule() {
    ruleVisible.value = true
  }

  function closeRule() {
    ruleVisible.value = false
  }

  function toggleSettings(key) {
    progress.value.settings[key] = !progress.value.settings[key]
    markChanged()
  }

  function setFontScale(value) {
    progress.value.settings.fontScale = value
    markChanged()
  }

  watch(toast, (value) => {
    if (value) window.setTimeout(() => { toast.value = '' }, 4000)
  })

  return {
    // data
    chapters: CHAPTERS,
    achievementsList: ACHIEVEMENTS,
    // progress
    progress,
    save,
    // screen state
    screen,
    currentLevel,
    currentLevelId,
    phase,
    chain,
    chainFragments,
    undoStack,
    result,
    overlayVisible,
    endingAlreadySeen,
    globalEnding,
    butterfly,
    hintVisible,
    ruleVisible,
    toast,
    // derived
    canEdit,
    canSubmit,
    draggable,
    coherence,
    valence,
    insights,
    failCount,
    hintTier,
    currentHint,
    ruleHint,
    achievements,
    achievementsPoints,
    achievementsTotalPoints,
    levelStates,
    gallery,
    globalGallery,
    characters,
    bondList,
    totalEndingsSeen,
    totalDesignEndings,
    fragmentById,
    // actions
    enterLevel,
    showScreen,
    move,
    moveBy,
    moveToEdge,
    undo,
    submit,
    retry,
    keepEnding,
    closeGlobalEnding,
    backToChapters,
    dismissButterfly,
    openHint,
    closeHint,
    openRule,
    closeRule,
    toggleSettings,
    setFontScale,
    isLevelUnlocked,
  }
}
