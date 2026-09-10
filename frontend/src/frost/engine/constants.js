/**
 * 《糖霜世界 Sugar Frost》判定引擎 —— 常量
 * 移植自 vrcWill/src/lib/engine/types.ts（仅保留运行时常量部分）。
 */

/** 存档结构版本号 */
export const SAVE_VERSION = 1

/** 默认设置 */
export const DEFAULT_SETTINGS = {
  reduceMotion: false,
  colorBlind: false,
  highContrast: false,
  fontScale: 'medium',
}

/** 角色显示名 */
export const CHARACTER_LABEL = {
  Mio: '澪',
  Shiori: '栞',
  Rin: '凛',
  Yu: '悠',
  Observer: '观测者',
  Echo: '回声服务器',
  Narrator: '旁白',
}

/** 角色主色（边框） */
export const CHARACTER_COLOR = {
  Mio: '#A8C4DD',
  Shiori: '#E0B08A',
  Rin: '#B9A8DD',
  Yu: '#A8DDBB',
  Observer: '#BDBDBD',
  Echo: '#8FA9A0',
  Narrator: '#D8D8D2',
}

/** 角色卡片背景色 */
export const CHARACTER_BG = {
  Mio: '#EEF3F8',
  Shiori: '#FBF3EE',
  Rin: '#F3EEFB',
  Yu: '#EEFBF3',
  Observer: '#F5F5F5',
  Echo: '#F0F5F3',
  Narrator: '#FAFAF7',
}

/** 角色形状标识（色盲模式下不依赖颜色区分角色） */
export const CHARACTER_SHAPE = {
  Mio: 'circle',
  Shiori: 'triangle',
  Rin: 'square',
  Yu: 'star',
  Observer: 'dashed',
  Echo: 'none',
  Narrator: 'dot',
}

/** 结局色调（渐变起止） */
export const ENDING_GRADIENT = {
  good: ['#F5D9A8', '#FBF6EE'],
  bittersweet: ['#9FB3C8', '#EEF2F5'],
  bad: ['#7A3B3B', '#2A2A2E'],
  true: ['#F5D9A8', '#A8C4DD'],
  chaos: ['#3A3A3E', '#3A3A3E'],
}

/** 结局中文标签 */
export const ENDING_LABEL = {
  good: '修复',
  bittersweet: '遗憾',
  bad: '破碎',
  true: '真相',
  chaos: '混沌',
}

/** 指标条配色 */
export const METER_COLOR = {
  coherence: '#7BA7C7',
  valenceWarm: '#E0B08A',
  valenceCold: '#8FA9A0',
}
