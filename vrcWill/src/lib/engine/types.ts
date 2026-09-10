/**
 * 《糖霜世界 Sugar Frost》判定引擎 —— 类型定义
 * ------------------------------------------------------------------
 * 本文件是"数据层 ↔ 引擎层"的唯一契约。所有关卡 JSON、结局定义、
 * 碎片定义都必须满足此处的接口。
 *
 * 设计约束（务必遵守）：
 *  1. 本文件必须保持"纯类型 + 纯常量"，不得引入任何运行时副作用。
 *  2. 不得使用 enum / namespace / 装饰器 —— 以便 Node 24 可直接
 *     以 `node xxx.ts` 运行（type stripping），也便于将来迁移。
 *  3. 所有 import 必须带 `.ts` 后缀，保证 Node 原生执行与 Vite 均可解析。
 */

/* ============================================================
 * 1. 基础枚举（以字面量联合类型表达，避免 enum）
 * ============================================================ */

/** 碎片类型 */
export type FragmentType =
  | 'white' // 白色：普通事件，可自由调整顺序
  | 'gray' // 灰色：固定事件，不可移动（因果锚点）
  | 'gold' // 金色：关键事件，移动后触发文本交换等特殊效果
  | 'red' // 红色：负面事件，需被"覆盖"或移到末位
  | 'blue'; // 蓝色：内心独白，不入主链，仅作氛围与线索

/** 结局类型 */
export type EndingType =
  | 'good' // 修复结局
  | 'bittersweet' // 遗憾结局
  | 'bad' // 破碎结局
  | 'true' // 隐藏/真相结局
  | 'chaos'; // 混沌结局（系统兜底，未探索组合）

/** 角色标识 */
export type CharacterId =
  | 'Mio' // 澪（角色 A）
  | 'Shiori' // 栞（角色 B）
  | 'Rin' // 凛（角色 C）
  | 'Yu' // 悠（角色 D）
  | 'Observer' // 观测者（玩家 / 第四章揭示为澪的残响）
  | 'Echo' // 回声服务器（系统旁白，说话者）
  | 'Narrator'; // 纯旁白（无角色）

/* ============================================================
 * 2. 碎片定义
 * ============================================================ */

/**
 * 单个碎片。
 * 注意：`text` 是唯一权威文案来源，UI 与文档均从此处读取，
 * 不得在组件中硬编码中文。
 */
export interface Fragment {
  /** 唯一 ID，格式 `frag_<章节>_<关卡>_<两位序号>`，如 `frag_2_3_05` */
  id: string;
  /** 所属关卡，如 `2-3` */
  levelId: string;
  /** 碎片类型 */
  type: FragmentType;
  /** 归属角色（Narrator 表示纯旁白） */
  character: CharacterId;
  /** 碎片正文，20–60 字 */
  text: string;
  /** 语义标签，用于提示系统、蝴蝶效应判定与预判动画 */
  tags: string[];
  /**
   * 是否可拖拽。
   * - gray 恒为 false
   * - red 默认 false（需被金色碎片解锁，见 Level.redUnlock）
   * - white / gold 恒为 true
   * - blue 恒为 false（不入链）
   */
  draggable: boolean;
  /**
   * 情感倾向值，取值 -2..+2。
   * 用于实时「情感走向 Valence」指标条的计算。
   * -2 = 强烈疏离 / +2 = 强烈靠近 / 0 = 中性
   */
  valence: number;
  /**
   * 是否为"默认隐藏"碎片（如 1-3 的 frag_1_3_07 灯光）。
   * 隐藏碎片在首次游玩时不进入 initialOrder，不计入判定；
   * 满足 unlockedBy 后才出现在池中。
   */
  hidden?: boolean;
  /**
   * 解锁条件。仅在 hidden === true 时有意义。
   * - 形如 `ending:1-3:good` 表示"通关 1-3 的 good 结局后解锁"
   * - 形如 `endingType:true` 表示"任意关卡达成 true 结局后解锁"
   * - 形如 `butterfly:3-3:A` 表示"触发 3-3 的蝴蝶效应 A 后解锁"
   */
  unlockedBy?: string | null;
  /** 设计备注，不展示给玩家 */
  note?: string;
}

/* ============================================================
 * 3. 约束定义
 * ============================================================ */

/**
 * 约束种类：
 * - `before`   : a 必须排在 b 之前
 * - `adjacent` : a 与 b 必须相邻（顺序不敏感）
 * - `position` : frag 必须落在完整链的第 index 个位置（0-based）
 * - `block`    : a 与 b 必须相邻 —— 仅用于 anti，表达"这两件事不该挨在一起"
 * - `group`    : frags 中的碎片必须占据一段连续区间（内部顺序任意）
 */
export type ConstraintKind = 'before' | 'adjacent' | 'position' | 'block' | 'group';

/**
 * 单条因果约束。
 * `weight` 语义：
 *  - 出现在 `ending.constraints` 时，为**正向得分**（满足即加分）
 *  - 出现在 `ending.anti` 时，为**扣分**（满足即扣分）
 */
export interface Constraint {
  kind: ConstraintKind;
  /** before / adjacent / block 的左操作数 */
  a?: string;
  /** before / adjacent / block 的右操作数 */
  b?: string;
  /** position 的目标碎片 */
  frag?: string;
  /** group 的碎片集合 */
  frags?: string[];
  /** position 的 0-based 目标下标（对完整链而言，含首尾锚点） */
  index?: number;
  /** 权重 / 扣分，正整数 */
  weight: number;
}

/* ============================================================
 * 4. 蝴蝶效应
 * ============================================================ */

/** 蝴蝶效应（跨角色交换碎片触发的隐藏剧情） */
export interface Butterfly {
  /** 如 `3-3:A` */
  id: string;
  /** 触发条件（一组需同时满足的约束） */
  requires: Constraint[];
  /** 触发后解锁的碎片 ID 列表 */
  unlocks: string[];
  /** 触发时展示的演出文本 */
  revealText: string;
}

/* ============================================================
 * 5. 提示
 * ============================================================ */

/** 分级提示 */
export interface Hint {
  /** 提示层级：1 = 方向性，2 = 高亮，3 = 直接步骤 */
  tier: 1 | 2 | 3;
  /** 提示文本 */
  text: string;
  /** tier>=2 时高亮的碎片 ID */
  highlight?: string[];
}

/* ============================================================
 * 6. 结局
 * ============================================================ */

/** 单个结局定义 */
export interface Ending {
  /** 结局 ID，唯一。通常形如 `1_1_good` */
  id: string;
  /** 所属关卡 */
  levelId: string;
  /** 结局类型 */
  type: EndingType;
  /** 结局标题（展示名） */
  title: string;
  /**
   * 命中阈值：`scoreEnding() >= threshold` 才判定为"可命中"。
   * 阈值设定原则见 docs/02-判定引擎规格.md
   */
  threshold: number;
  /** 情感倾向：+1 偏"靠近"，-1 偏"疏离"，0 中性 */
  valence: number;
  /** 正向约束 */
  constraints: Constraint[];
  /** 负向约束（满足即扣分） */
  anti: Constraint[];
  /** 结局正文（60–160 字） */
  text: string;
  /** 图鉴中的一句话摘要（≤30 字） */
  excerpt: string;
  /** 结局展示缩略图（可空，缺省时用纯色渐变） */
  thumbnail?: string;
  /**
   * 前置解锁条件。满足后才在关卡中"可被命中"（用于隐藏结局的二周目解锁）。
   * 形如 `["ending:1-3:good"]`。
   */
  requires?: string[];
  /** 是否在图鉴中默认显示为剪影（隐藏结局） */
  hidden?: boolean;
  /**
   * 达成该结局时对各角色羁绊值的增减。
   * 例：{ "Mio": 10, "Shiori": -5 }
   */
  bondEffect?: Partial<Record<CharacterId, number>>;
}

/* ============================================================
 * 7. 关卡
 * ============================================================ */

/** 锚点定义 */
export interface LevelAnchors {
  /** 固定首位碎片 ID */
  first: string;
  /** 固定末位碎片 ID */
  last: string;
}

/** 红色碎片的解锁规则 */
export interface RedUnlock {
  /** 被解锁的红色碎片 ID */
  redFragmentId: string;
  /** 解锁条件 */
  requires: Constraint[];
}

/** 关卡定义 */
export interface Level {
  /** 关卡 ID，如 `2-3` */
  id: string;
  /** 关卡标题 */
  title: string;
  /** 章节号 1..4 */
  chapter: number;
  /** 章内序号 1..3 */
  order: number;
  /** 章首语（仅每章第一关需要，其余为空串） */
  epigraph: string;
  /** 开场文本 */
  intro: string;
  /** 是否存在蝴蝶效应 */
  hasButterfly: boolean;
  /** 全部碎片（含隐藏碎片） */
  fragments: Fragment[];
  /**
   * 初始链顺序（完整链，长度 = 参与判定的碎片数）。
   * 首尾必须是 anchors.first / anchors.last。
   * 隐藏碎片不出现在此数组中。
   */
  initialOrder: string[];
  /** 首尾锚点 */
  anchors: LevelAnchors;
  /** 可命中的结局（含隐藏结局） */
  endings: Ending[];
  /** 混沌兜底结局 */
  chaosEnding: Ending;
  /** 蝴蝶效应定义 */
  butterflies?: Butterfly[];
  /** 分级提示 */
  hints?: Hint[];
  /** 红色碎片解锁规则 */
  redUnlock?: RedUnlock;
  /** 集齐全部结局后解锁的幕后注释 */
  behindTheScenes: string;
}

/* ============================================================
 * 8. 判定结果
 * ============================================================ */

/** 单条约束的命中轨迹（用于调试面板与开发工具） */
export interface ConstraintTrace {
  constraint: Constraint;
  matched: boolean;
  /** 实际对总分的贡献（满足为正，anti 为负） */
  delta: number;
}

/** 单个结局的评估结果 */
export interface EndingEvaluation {
  endingId: string;
  title: string;
  type: EndingType;
  score: number;
  threshold: number;
  /** score >= threshold 且前置已解锁 */
  qualified: boolean;
  /** 是否满足该结局的 requires 前置 */
  unlocked: boolean;
  trace: ConstraintTrace[];
}

/** 判定输出 */
export interface JudgeResult {
  /** 最终命中的结局 */
  ending: Ending;
  /** 是否为混沌兜底 */
  isChaos: boolean;
  /** 命中结局的得分 */
  score: number;
  /** 归一化连贯度 0–100（用于 UI 指标条） */
  coherence: number;
  /** 链的情感走向 -100..+100（用于 UI 指标条） */
  valence: number;
  /** 所有结局的评估明细（调试/图鉴用） */
  evaluations: EndingEvaluation[];
  /** 次优结局（用于"最接近的另一种可能"提示，可空） */
  runnerUp?: EndingEvaluation;
}

/* ============================================================
 * 9. 存档
 * ============================================================ */

/** 设置 */
export interface GameSettings {
  masterVolume: number;
  sfxVolume: number;
  musicVolume: number;
  fontScale: 'small' | 'medium' | 'large';
  reduceMotion: boolean;
  colorBlind: boolean;
  highContrast: boolean;
}

/** 单存档槽 */
export interface SaveSlot {
  id: number;
  updatedAt: number;
  progress: {
    currentLevel: string;
    cleared: string[];
  };
  /** 已见结局 ID 集合 */
  endingsSeen: string[];
  /** 已触发的蝴蝶效应 ID 集合 */
  butterfliesSeen: string[];
  /** 各角色羁绊值 -100..100 */
  bond: Record<string, number>;
  /** 各关卡提示使用次数 */
  hintsUsed: Record<string, number>;
  settings: GameSettings;
}

/** 存档根结构 */
export interface SaveFile {
  version: number;
  slots: SaveSlot[];
}

/* ============================================================
 * 10. 常量
 * ============================================================ */

/** 存档结构版本号（升级时递增并编写迁移逻辑） */
export const SAVE_VERSION = 2;

/** 默认设置 */
export const DEFAULT_SETTINGS: GameSettings = {
  masterVolume: 0.7,
  sfxVolume: 0.8,
  musicVolume: 0.5,
  fontScale: 'medium',
  reduceMotion: false,
  colorBlind: false,
  highContrast: false,
};

/** 角色显示名 */
export const CHARACTER_LABEL: Record<CharacterId, string> = {
  Mio: '澪',
  Shiori: '栞',
  Rin: '凛',
  Yu: '悠',
  Observer: '观测者',
  Echo: '回声服务器',
  Narrator: '旁白',
};

/** 角色主色（边框） */
export const CHARACTER_COLOR: Record<CharacterId, string> = {
  Mio: '#A8C4DD',
  Shiori: '#E0B08A',
  Rin: '#B9A8DD',
  Yu: '#A8DDBB',
  Observer: '#BDBDBD',
  Echo: '#8FA9A0',
  Narrator: '#D8D8D2',
};

/** 角色卡片背景色 */
export const CHARACTER_BG: Record<CharacterId, string> = {
  Mio: '#EEF3F8',
  Shiori: '#FBF3EE',
  Rin: '#F3EEFB',
  Yu: '#EEFBF3',
  Observer: '#F5F5F5',
  Echo: '#F0F5F3',
  Narrator: '#FAFAF7',
};

/** 结局色调（渐变起止） */
export const ENDING_GRADIENT: Record<EndingType, [string, string]> = {
  good: ['#F5D9A8', '#FBF6EE'],
  bittersweet: ['#9FB3C8', '#EEF2F5'],
  bad: ['#7A3B3B', '#2A2A2E'],
  true: ['#F5D9A8', '#A8C4DD'],
  chaos: ['#3A3A3E', '#3A3A3E'],
};

/** 结局中文标签 */
export const ENDING_LABEL: Record<EndingType, string> = {
  good: '修复',
  bittersweet: '遗憾',
  bad: '破碎',
  true: '真相',
  chaos: '混沌',
};
