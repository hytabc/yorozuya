// 内置默认内容包：NPC、立绘、世界/房间/在场、动作、节点图剧本、初始人生数据。
// 内容与后端种子 backend/app/life_packs/wsw-default-life.json 保持一致
// (tests/lifeRegistry.test.mjs 会断言两者相等),经工厂构建为运行时 Pack;
// 当站点 API 不可达时作为兜底 Pack。
import { createLifePackFromContent } from '../registry.js'

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
  dialogue: {
    ache: {
      start: 'n1',
      nodes: {
        n1: {
          line: '这里的日落每天都不太一样。要不要一起拍张照？就当是今天认识的纪念。',
          choices: [
            { label: '好啊，一起拍吧', effects: { bond: 2, stats: { social: 2, mood: 2 } }, reply: '太好了！那我调整一下角度……好了，笑一个！', next: null },
            { label: '我来帮你拍一张', effects: { bond: 3, stats: { social: 3, energy: -2 } }, reply: '欸？可以吗？那就麻烦你了……这张照片我会好好保存的。', next: null },
            { label: '想先安静看一会儿海', effects: { stats: { mood: 4, explore: 1 } }, reply: '嗯，海边确实很适合发呆。那我就先去拍别处了，回头见！', next: null },
          ],
        },
      },
    },
    xiaomi: {
      start: 'n1',
      nodes: {
        n1: {
          line: '今天也想跳一会儿舞呢。你要不要一起来？',
          choices: [
            { label: '好啊，一起跳', effects: { stats: { social: 3, energy: -4 } }, reply: '哈哈，你的动作好可爱！', next: null },
            { label: '我在旁边看就好', effects: { stats: { mood: 2 } }, reply: '没问题！那我就开始了哦。', next: null },
          ],
        },
      },
    },
    maoyou: {
      start: 'n1',
      nodes: {
        n1: {
          line: '……这个模型的骨架好像有点问题。你会改模型吗？',
          choices: [
            { label: '我可以试试', effects: { bond: 2, stats: { social: 2, energy: -3 } }, reply: '太好了！那就拜托你了。', next: null },
            { label: '我不会诶', effects: {}, reply: '啊……没关系，我再想想办法。', next: null },
          ],
        },
      },
    },
    yu: {
      start: 'n1',
      nodes: {
        n1: {
          line: '你经常来这个世界吗？我第一次来，感觉好棒！',
          choices: [
            { label: '我也是第一次来', effects: { bond: 1, stats: { social: 1, mood: 1 } }, reply: '哈哈，那我们算是同好了！', next: null },
            { label: '偶尔来，这里很放松', effects: { stats: { social: 2 } }, reply: '嗯嗯，我也是这样觉得的。', next: null },
          ],
        },
      },
    },
  },
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
