// 内置默认内容包：NPC、立绘、世界/房间/在场、动作、每日剧本(7 天,超出沿用第 7 天)、初始人生数据。
// 内容与后端种子 backend/app/life_packs/wsw-default-life.json 保持一致
// (tests/lifeRegistry.test.mjs 会断言两者相等),经工厂构建为运行时 Pack;
// 当站点 API 不可达时作为兜底 Pack。
import { createLifePackFromContent } from '../registry.js'

// 同一组选项 + 每天一句不同的开场,组成 7 天剧本(第 8 天起沿用第 7 天)。
function dailyScripts(lines, choices) {
  return lines.map(line => ({ start: 'n1', nodes: { n1: { line, choices } } }))
}

const acheChoices = [
  { label: '好啊，一起拍吧', effects: { bond: 2, stats: { social: 2, mood: 2 } }, reply: '太好了！那我调整一下角度……好了，笑一个！', next: null },
  { label: '我来帮你拍一张', effects: { bond: 3, stats: { social: 3, energy: -2 } }, reply: '欸？可以吗？那就麻烦你了……这张照片我会好好保存的。', next: null },
  { label: '想先安静看一会儿海', effects: { stats: { mood: 4, explore: 1 } }, reply: '嗯，海边确实很适合发呆。那我就先去拍别处了，回头见！', next: null },
]
const xiaomiChoices = [
  { label: '好啊，一起跳', effects: { stats: { social: 3, energy: -4 } }, reply: '哈哈，你的动作好可爱！', next: null },
  { label: '我在旁边看就好', effects: { stats: { mood: 2 } }, reply: '没问题！那我就开始了哦。', next: null },
]
const maoyouChoices = [
  { label: '我可以试试', effects: { bond: 2, stats: { social: 2, energy: -3 } }, reply: '太好了！那就拜托你了。', next: null },
  { label: '我不会诶', effects: {}, reply: '啊……没关系，我再想想办法。', next: null },
]
const yuChoices = [
  { label: '我也是第一次来', effects: { bond: 1, stats: { social: 1, mood: 1 } }, reply: '哈哈，那我们算是同好了！', next: null },
  { label: '偶尔来，这里很放松', effects: { stats: { social: 2 } }, reply: '嗯嗯，我也是这样觉得的。', next: null },
]

const dialogue = {
  ache: dailyScripts([
    '这里的日落每天都不太一样。要不要一起拍张照？就当是今天认识的纪念。',
    '今天的云很低，拍出来像油画。要试试吗？',
    '昨天那张照片洗出来了，效果意外地好。想不想看看？',
    '听说今晚有晚霞，要不要一起去占个好位置？',
    '海风今天有点大，三脚架都在晃。你那边还好吗？',
    '整理相册才发现，这星期拍了好多天空。要不要翻翻看？',
    '周末的海滩人多起来了。要不要试试拍人像？',
  ], acheChoices),
  xiaomi: dailyScripts([
    '今天也想跳一会儿舞呢。你要不要一起来？',
    '昨天练了新动作，今天想试试顺不顺。来看看？',
    '腿有点酸，但还是想动一动。你呢，今天有安排吗？',
    '咖啡馆那边有人在放音乐，节奏超好，想去听听吗？',
    '今天想慢慢练基本功，要不要一起？',
    '我录了一段练习视频，等下你帮我看看好不好？',
    '周末想编一支新舞，正好缺个观众！',
  ], xiaomiChoices),
  maoyou: dailyScripts([
    '……这个模型的骨架好像有点问题。你会改模型吗？',
    '昨晚想到一个改造方案，今天想验证一下。你有空吗？',
    '零件终于到了，今天有得忙了。要不要来看看？',
    '这台机体的平衡还是不太对……你有什么想法吗？',
    '工具箱整理好了，效率应该会高一点。今天改哪台好呢。',
    '改造进度过半了，要不要看看半成品？',
    '周末适合慢慢打磨细节。你来帮我递工具吗？',
  ], maoyouChoices),
  yu: dailyScripts([
    '你经常来这个世界吗？我第一次来，感觉好棒！',
    '昨天去的那个世界也不错，但还是这里最让我放松。',
    '今天打算去探索没去过的房间，要一起吗？',
    '我列了个探索清单，已经完成大半了！',
    '听说聚会大厅晚上很热闹，你去过吗？',
    '发现了一个新世界，先记下来，改天一起去？',
    '探索了一周，最喜欢的还是这里。你呢？',
  ], yuChoices),
}

export const defaultLifePackContent = {
  npcIds: ['ache', 'xiaomi', 'maoyou', 'yu'],
  npcs: [
    { id: 'ache', name: '阿澈', role: '摄影爱好者', avatar: '📷', status: '正在看着海面', bond: 12 },
    { id: 'xiaomi', name: '小弥', role: '舞蹈玩家', avatar: '💃', status: '在海边散步', bond: 6 },
    { id: 'maoyou', name: '猫又', role: '模型改装师', avatar: '⚙️', status: '在调试设备', bond: 2 },
    { id: 'yu', name: '小宇', role: '世界探索者', avatar: '🧭', status: '刚到达这个世界', bond: 0 },
  ],
  portraits: {
    ache: '/life-assets/avatars/f1fcd71500345a67eb47b4a349339cfc_720.jpg',
    xiaomi: '/life-assets/avatars/850069447b371c8856317390362a550a_720.jpg',
    maoyou: '/life-assets/avatars/e125eb534d189bfc005f4e1e3dac13da_720.jpg',
    yu: '/life-assets/avatars/f134ae516db4415316fbf09384ed62b9_720.jpg',
  },
  worlds: [
    { id: 'beach', name: '潮汐之后', vibe: '安静 · 海边拍照', color: '#3f7777', bg: '' },
    { id: 'cafe', name: '小小咖啡馆', vibe: '轻松 · 咖啡闲聊', color: '#9a7563', bg: '' },
    { id: 'hall', name: '夜间聚会大厅', vibe: '热闹 · 社交聚会', color: '#576c80', bg: '' },
  ],
  rooms: [
    { id: 'beach-1024', worldId: 'beach', label: '#1024', private: false, capacity: 16, occupants: 1 },
    { id: 'beach-2086', worldId: 'beach', label: '#2086', private: false, capacity: 16, occupants: 1 },
    { id: 'beach-empty', worldId: 'beach', label: '#3000', private: false, capacity: 16, occupants: 0 },
    { id: 'cafe-1101', worldId: 'cafe', label: '#1101', private: false, capacity: 12, occupants: 1 },
    { id: 'cafe-private', worldId: 'cafe', label: '#2202', private: true, capacity: 12, occupants: 2 },
    { id: 'hall-1001', worldId: 'hall', label: '#1001', private: false, capacity: 20, occupants: 2 },
    { id: 'hall-full', worldId: 'hall', label: '#2002', private: false, capacity: 4, occupants: 4 },
  ],
  presence: {
    ache: { status: 'green', roomId: 'beach-1024', intro: '喜欢记录日落，也喜欢和新朋友一起拍照。' },
    xiaomi: { status: 'green', roomId: 'cafe-1101', intro: '练舞结束后常去咖啡馆休息。' },
    maoyou: { status: 'orange', roomId: 'beach-2086', intro: '正在调试模型，暂时不接受跟随加入。' },
    yu: { status: 'green', roomId: 'hall-1001', intro: '喜欢探索没去过的世界。' },
  },
  actions: [
    { id: 'headpat', label: '摸摸头', reward: 2, threshold: 0, reply: '轻轻笑了一下：“嗯……谢谢你。”' },
    { id: 'poke', label: '戳戳脸', reward: 1, threshold: 0, reply: '侧过脸笑着说：“被你发现我在发呆啦。”' },
    { id: 'kiss', label: '亲亲', reward: 3, threshold: 30, reply: '有些害羞地笑了：“这个小小的心意，我收到了。”' },
  ],
  dialogue,
  initialState: {
    day: 7,
    stats: { mood: 72, energy: 66, social: 34, explore: 28 },
    tags: ['慢热', '喜欢拍照', '夜猫子'],
    currentWorld: '潮汐之后 · 黄昏',
    unlockedWorlds: 8,
    conversations: {
      ache: [
        { from: 'npc', text: '你第一次来到这个世界吗？', day: 7, time: '18:20' },
      ],
      xiaomi: [
        { from: 'npc', text: '你好呀，我叫小弥，平时喜欢在这里练舞。', day: 7, time: '18:15' },
      ],
      maoyou: [
        { from: 'npc', text: '……嗯？你也是来拍照的吗？', day: 7, time: '18:10' },
      ],
      yu: [
        { from: 'npc', text: '哇，这里好美！你也是玩家吗？', day: 7, time: '18:05' },
      ],
    },
    diary: [
      { day: 6, text: '"原来不说话的时候，也可以和别人共享一段风景。"', mood: '平静' },
      { day: 5, text: '"咖啡杯是热的，但手心里更暖的是有人记得你的名字。"', mood: '安心' },
      { day: 3, text: '"第一次主动开口，声音轻得像羽毛。"', mood: '紧张' },
    ],
  },
}

export const defaultLifePack = createLifePackFromContent({
  id: 'wsw-default-life',
  version: 1,
  content: defaultLifePackContent,
})
