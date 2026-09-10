/**
 * 关卡与静态数据加载器。
 * 数据来源：vrcWill/src/lib/data（原样拷贝至 ./data）。
 */

import indexData from './data/levels/index.json'
import charactersData from './data/characters.json'
import achievementsData from './data/achievements.json'
import globalEndingsData from './data/global-endings.json'

const levelModules = import.meta.glob('./data/levels/*.json', { eager: true, import: 'default' })

export const LEVELS = Object.entries(levelModules)
  .filter(([path]) => !path.endsWith('index.json'))
  .map(([, level]) => level)
  .sort((a, b) => a.chapter - b.chapter || a.order - b.order)

export const LEVEL_BY_ID = Object.fromEntries(LEVELS.map((level) => [level.id, level]))

export const CHAPTERS = indexData.chapters

export const LEVEL_INDEX = indexData.levels

export const LEVEL_META_BY_ID = Object.fromEntries(indexData.levels.map((meta) => [meta.id, meta]))

export const CHARACTERS = charactersData.characters

export const CHARACTER_BY_ID = Object.fromEntries(charactersData.characters.map((c) => [c.id, c]))

export const RELATIONSHIPS = charactersData.relationships

export const ACHIEVEMENTS = achievementsData.achievements

export const GLOBAL_ENDINGS = globalEndingsData

/** 结局 ID → { levelId, type }（含混沌结局） */
export const ENDING_META = {}
for (const level of LEVELS) {
  for (const ending of [...level.endings, level.chaosEnding]) {
    ENDING_META[ending.id] = { levelId: level.id, type: ending.type }
  }
}

/** 全部蝴蝶效应 ID */
export const ALL_BUTTERFLY_IDS = LEVELS.flatMap((level) => (level.butterflies ?? []).map((b) => b.id))

/** 全部蓝色独白碎片 ID */
export const ALL_BLUE_FRAGMENT_IDS = LEVELS.flatMap((level) =>
  level.fragments.filter((f) => f.type === 'blue').map((f) => f.id))

/** 全部设计结局 ID（不含混沌兜底） */
export const ALL_DESIGN_ENDING_IDS = LEVELS.flatMap((level) => level.endings.map((e) => e.id))

/** 章节号 → 该章节关卡 */
export const LEVELS_BY_CHAPTER = CHAPTERS.map((chapter) => ({
  ...chapter,
  levels: LEVELS.filter((level) => level.chapter === chapter.id),
}))
