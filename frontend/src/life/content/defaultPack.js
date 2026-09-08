// 内置默认内容包：NPC、剧本、初始人生数据。
// 阶段 2 起按 Pack 结构组织,经 life/builtin.js 注册进 Registry 后供游戏消费;
// 数据本身与原 LifeSimulator.vue 完全一致。

const npcIds = ['ache', 'xiaomi', 'maoyou', 'yu']

const npcs = [
  { id: 'ache', name: '阿澈', role: '摄影爱好者', avatar: '📷', status: '正在看着海面', bond: 12 },
  { id: 'xiaomi', name: '小弥', role: '舞蹈玩家', avatar: '💃', status: '在海边散步', bond: 6 },
  { id: 'maoyou', name: '猫又', role: '模型改装师', avatar: '⚙️', status: '在调试设备', bond: 2 },
  { id: 'yu', name: '小宇', role: '世界探索者', avatar: '🧭', status: '刚到达这个世界', bond: 0 },
]

const portraits = {
  ache: '/life-assets/avatars/f1fcd71500345a67eb47b4a349339cfc_720.jpg',
  xiaomi: '/life-assets/avatars/850069447b371c8856317390362a550a_720.jpg',
  maoyou: '/life-assets/avatars/e125eb534d189bfc005f4e1e3dac13da_720.jpg',
  yu: '/life-assets/avatars/f134ae516db4415316fbf09384ed62b9_720.jpg',
}

const dialogueScripts = {
  ache: {
    npcLine: { from: 'npc', text: '这里的日落每天都不太一样。要不要一起拍张照？就当是今天认识的纪念。', day: 7, time: '18:20' },
    choices: [
      { label: '好啊，一起拍吧', effect: '好感 +2 · 心情 +2', delta: { social: 2, mood: 2 }, npcReply: '太好了！那我调整一下角度……好了，笑一个！', next: 'continue' },
      { label: '我来帮你拍一张', effect: '好感 +3 · 表达 +2', delta: { social: 3, energy: -2 }, npcReply: '欸？可以吗？那就麻烦你了……这张照片我会好好保存的。', next: 'continue' },
      { label: '想先安静看一会儿海', effect: '心情 +4 · 探索 +1', delta: { mood: 4, explore: 1 }, npcReply: '嗯，海边确实很适合发呆。那我就先去拍别处了，回头见！', next: 'end' },
    ],
  },
  xiaomi: {
    npcLine: { from: 'npc', text: '今天也想跳一会儿舞呢。你要不要一起来？', day: 7, time: '18:15' },
    choices: [
      { label: '好啊，一起跳', effect: '社交 +3 · 精力 -4', delta: { social: 3, energy: -4 }, npcReply: '哈哈，你的动作好可爱！', next: 'continue' },
      { label: '我在旁边看就好', effect: '心情 +2', delta: { mood: 2 }, npcReply: '没问题！那我就开始了哦。', next: 'continue' },
    ],
  },
  maoyou: {
    npcLine: { from: 'npc', text: '……这个模型的骨架好像有点问题。你会改模型吗？', day: 7, time: '18:10' },
    choices: [
      { label: '我可以试试', effect: '社交 +2 · 好感 +2', delta: { social: 2, energy: -3 }, npcReply: '太好了！那就拜托你了。', next: 'continue' },
      { label: '我不会诶', effect: '', delta: {}, npcReply: '啊……没关系，我再想想办法。', next: 'continue' },
    ],
  },
  yu: {
    npcLine: { from: 'npc', text: '你经常来这个世界吗？我第一次来，感觉好棒！', day: 7, time: '18:05' },
    choices: [
      { label: '我也是第一次来', effect: '好感 +1 · 心情 +1', delta: { social: 1, mood: 1 }, npcReply: '哈哈，那我们算是同好了！', next: 'continue' },
      { label: '偶尔来，这里很放松', effect: '表达 +2', delta: { social: 2 }, npcReply: '嗯嗯，我也是这样觉得的。', next: 'continue' },
    ],
  },
}

// 每次调用返回全新深拷贝,等价于原组件挂载时的字面量初始值。
function createInitialState() {
  return JSON.parse(JSON.stringify({
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
  }))
}

export const defaultLifePack = {
  id: 'wsw-default-life',
  version: 1,
  npcIds,
  npcs,
  portraits,
  dialogueScripts,
  createInitialState,
}
