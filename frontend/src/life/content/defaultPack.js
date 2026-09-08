// 内置默认内容包：NPC、立绘、世界/房间/在场、动作、每日剧本(7 天,超出沿用第 7 天)、初始人生数据。
// 内容与后端种子 backend/app/life_packs/wsw-default-life.json 保持一致
// (tests/lifeRegistry.test.mjs 会断言两者相等),经工厂构建为运行时 Pack;
// 当站点 API 不可达时作为兜底 Pack。
import { createLifePackFromContent } from '../registry.js'

// 每个 NPC 的 7 天剧本:每天一条小对话链(2~3 个节点),部分天带分支。
// n1 = 当天开场;部分选项推进到 n2/n3 深入话题,其余当天结束;第 8 天起沿用第 7 天。
const C = (label, effects, reply, next = null) => ({ label, effects, reply, next })
const S = nodes => ({ start: 'n1', nodes })

const dialogue = {
  ache: [
    S({
      n1: { line: '这里的日落每天都不太一样。要不要一起拍张照？就当是今天认识的纪念。', choices: [
        C('好啊，一起拍吧', { bond: 2, stats: { social: 2, mood: 2 } }, '太好了！那我调整一下角度……好了，笑一个！', 'n2'),
        C('我来帮你拍一张', { bond: 3, stats: { social: 3, energy: -2 } }, '欸？可以吗？那就麻烦你了……先别动，这个光线正好。', 'n3'),
        C('想先安静看一会儿海', { stats: { mood: 4, explore: 1 } }, '嗯，海边确实很适合发呆。那我就先去拍别处了，回头见！'),
      ] },
      n2: { lines: ['拍好了！你看，浪刚好在你身后碎成一圈金边。', '这张洗出来送你一份？'], choices: [
        C('好啊，谢谢！', { bond: 2, stats: { mood: 2 } }, ['那就说定了。', '今天谢谢你陪我等到这么好的光。']),
        C('能再拍一张背影吗', { bond: 1, stats: { mood: 3, energy: -2 } }, '当然可以。背对海站好……三、二、一！'),
      ] },
      n3: { line: '这张把我拍得很好诶，快门时机刚刚好。你以前玩过相机吗？', choices: [
        C('玩过一点', { bond: 2, stats: { social: 2 } }, '真的？那下次交流一下参数，我带两台机器出来！'),
        C('完全没有，凭感觉', { stats: { mood: 2 } }, '那你的感觉很好。这张照片我会好好保存的。'),
      ] },
    }),
    S({
      n1: { line: '今天的云很低，拍出来像油画。要试试吗？', choices: [
        C('试试', { bond: 1, stats: { mood: 2 } }, '好！你站在那块礁石旁边，云就压在你头顶了。', 'n2'),
        C('今天想偷个懒', { stats: { mood: 3 } }, '哈哈好，那我拍云，你负责当观众。'),
      ] },
      n2: { line: '这张怎么样？我觉得云的形状很像一只展翅的鸟。', choices: [
        C('真的很像', { bond: 2, stats: { mood: 2 } }, '对吧！能看到一样的形状，说明我们挺合拍的。'),
        C('我觉得更像鲸鱼', { bond: 1, stats: { mood: 3 } }, '鲸鱼吗……哈哈，也不错！那这张就叫《鲸》好了。'),
      ] },
    }),
    S({
      n1: { line: '昨天那张照片洗出来了，效果意外地好。想不想看看？', choices: [
        C('快给我看看', { bond: 2, stats: { mood: 2 } }, '给——就是这张。你笑得比本人还自然。', 'n2'),
        C('下次再看吧', { stats: { social: 1 } }, '好，那我先收着，你想看的时候随时说。'),
      ] },
      n2: { line: '其实我偷偷多洗了一张，打算自己留着。你不介意吧？', choices: [
        C('当然不介意', { bond: 3, stats: { mood: 2 } }, '太好了。那这张照片就是我的收藏第一号。'),
        C('介意，快销毁', { bond: 1, stats: { mood: 4 } }, '欸——？！哈哈哈，晚了，已经过塑了。'),
      ] },
    }),
    S({
      n1: { line: '听说今晚有晚霞，要不要一起去占个好位置？', choices: [
        C('走，现在就去', { bond: 2, stats: { social: 2, energy: -2 } }, '等等，带上这个——折叠椅和热茶，占位可是持久战。', 'n2'),
        C('今天有点累', { stats: { mood: 3 } }, '那你好好休息。如果晚霞够美，我拍下来带给你。'),
      ] },
      n2: { line: '其实占位置是借口。这个角度看海，云烧起来的时候，人都会变安静。我想和你再看一次。', choices: [
        C('那我不说话，陪你安静看', { bond: 3, stats: { mood: 3 } }, '……嗯。谢谢。'),
        C('我负责讲今天的事', { bond: 2, stats: { social: 2 } }, '也行，那等云烧起来之前，先听你讲讲今天的事吧。'),
      ] },
    }),
    S({
      n1: { line: '海风今天有点大，三脚架都在晃。你那边还好吗？', choices: [
        C('我来帮你扶着', { bond: 2, stats: { social: 2, energy: -2 } }, '谢谢！就扶那条腿……好，稳了！', 'n2'),
        C('我这边挺好的', { stats: { mood: 2 } }, '那就好。风大的时候海特别有精神，你看那排浪！'),
      ] },
      n2: { line: '风大也有风大的好处——长曝光拍出来，浪会像牛奶一样丝滑。要不要试试？', choices: [
        C('怎么试？', { bond: 1, stats: { explore: 2 } }, '你按快门，我数秒。三秒钟，别呼吸……开玩笑的，呼吸照常。'),
        C('听起来很玄学', { stats: { mood: 3 } }, '摄影本来就是一半技术一半玄学嘛。'),
      ] },
    }),
    S({
      n1: { line: '整理相册才发现，这星期拍了好多天空。要不要翻翻看？', choices: [
        C('好啊，翻翻', { bond: 1, stats: { mood: 2 } }, '这张是星期一，这张是星期三……你猜我最喜欢哪张？', 'n2'),
        C('天空有什么好看的', { stats: { mood: 1 } }, '你这人……等你看到那张火烧云再评价吧。'),
      ] },
      n2: { line: '是这张——其实也没什么特别的构图，但那天你在旁边，所以记得特别清楚。', choices: [
        C('原来照片是这样记住事情的', { bond: 3, stats: { mood: 3 } }, '对啊。相机记画面，人记感觉。'),
        C('这张确实最好看', { bond: 1, stats: { mood: 2 } }, '嘿嘿，眼光不错。'),
      ] },
    }),
    S({
      n1: { line: '周末的海滩人多起来了。要不要试试拍人像？', choices: [
        C('拍我吧', { bond: 2, stats: { social: 3 } }, '好啊！站到光里去……对，就那里，回头看我。', 'n2'),
        C('拍别人多尴尬', { stats: { social: 1 } }, '也是。那我们去拍风筝和狗，狗不尴尬。'),
      ] },
      n2: { line: '你面对镜头的时候一点都不僵，很难得。下周还愿意当我的模特吗？', choices: [
        C('愿意', { bond: 3, stats: { mood: 2 } }, '太好了，那说好了。下周的主题我都想好了。'),
        C('收费的哦', { bond: 1, stats: { mood: 4 } }, '哈哈，报酬是洗出来的全套照片，成交吗？'),
      ] },
    }),
  ],
  xiaomi: [
    S({
      n1: { line: '今天也想跳一会儿舞呢。你要不要一起来？', choices: [
        C('好啊，一起跳', { stats: { social: 3, energy: -4 } }, '哈哈，你的动作好可爱！', 'n2'),
        C('我在旁边看就好', { stats: { mood: 2 } }, '没问题！那我就开始了哦。'),
      ] },
      n2: { line: '来，跟我做——手抬高，转身！……对对，就是这样！你学得很快嘛。', choices: [
        C('是老师教得好', { bond: 2, stats: { mood: 2 } }, '嘴真甜！那老师奖励你再学一个八拍。'),
        C('不行了，喘口气', { stats: { mood: 3, energy: 2 } }, '哈哈好，休息休息。跳舞最重要的就是开心。'),
      ] },
    }),
    S({
      n1: { line: '昨天练了新动作，今天想试试顺不顺。来看看？', choices: [
        C('来了来了', { bond: 1, stats: { social: 2 } }, '看好了——预备，起！……怎么样怎么样？', 'n2'),
        C('今天想当安静的观众', { stats: { mood: 2 } }, '好呀，观众席第一排留给你。'),
      ] },
      n2: { line: '刚才那个转身我自己也不太满意，脚底下有点飘。你看得出来吗？', choices: [
        C('看不出来，已经很好了', { bond: 2, stats: { mood: 2 } }, '真的？……谢谢，你这么说我就有信心了。'),
        C('确实有一点点晃', { bond: 1, stats: { mood: 1 } }, '对吧！果然是这里。我再多练几遍，你帮我数拍子？'),
      ] },
    }),
    S({
      n1: { line: '腿有点酸，但还是想动一动。你呢，今天有安排吗？', choices: [
        C('陪你做拉伸吧', { bond: 2, stats: { social: 2 } }, '好呀，那就低强度恢复日。来，跟我压腿——慢点，别硬来。', 'n2'),
        C('建议彻底休息', { stats: { mood: 2 } }, '嗯……你说得对，那今天就偷个懒，聊聊天吧。', 'n3'),
      ] },
      n2: { line: '呼——拉伸完整个人都松了。你柔韧性不错诶，以前练过什么？', choices: [
        C('什么都没练过', { stats: { mood: 2 } }, '那就是天赋！要不要考虑跟我学舞？'),
        C('以前体育课勉强及格', { bond: 1, stats: { mood: 3 } }, '哈哈哈哈，那我们现在算是共同进步了。'),
      ] },
      n3: { line: '其实腿酸的时候最适合聊舞蹈以外的事。你平时不跳舞的时候都做什么？', choices: [
        C('发呆、看海', { stats: { mood: 3 } }, '听起来就很好。下次带我一起发呆。'),
        C('到处逛逛', { bond: 1, stats: { explore: 2 } }, '那等你发现好地方，要第一个告诉我哦。'),
      ] },
    }),
    S({
      n1: { line: '咖啡馆那边有人在放音乐，节奏超好，想去听听吗？', choices: [
        C('走啊', { bond: 1, stats: { social: 2 } }, '等等我拿个外套！……好了，出发！', 'n2'),
        C('人多的地方我有点怵', { stats: { mood: 2 } }, '那我们就站在门口听，不进去。这样行吗？'),
      ] },
      n2: { line: '你听这个鼓点——脚是不是已经自己想动了？我刚刚在门口悄悄比划了两下。', choices: [
        C('看到了，很可爱', { bond: 2, stats: { mood: 3 } }, '欸？！被看到了吗……那、那你就当没看到！'),
        C('进去跳一段？', { bond: 1, stats: { social: 3, energy: -3 } }, '你认真的吗？！……好啊，反正音乐这么好。'),
      ] },
    }),
    S({
      n1: { line: '今天想慢慢练基本功，要不要一起？', choices: [
        C('一起', { bond: 1, stats: { social: 2, energy: -3 } }, '那就从最简单的开始——站姿、呼吸、重心。别小看这些哦。', 'n2'),
        C('基本功好枯燥', { stats: { mood: 1 } }, '枯燥是枯燥，但它会在某个转身里救你一命。'),
      ] },
      n2: { line: '你看，同样的动作，重心稳了看起来就完全不一样。舞蹈没有捷径，但每一步都算数。', choices: [
        C('这句话我要记下来', { bond: 2, stats: { mood: 2 } }, '哈哈，记吧记吧，下次我再说点更帅的。'),
        C('那我明天还能来吗', { bond: 3 }, '当然可以！明天继续，我等你。'),
      ] },
    }),
    S({
      n1: { line: '我录了一段练习视频，等下你帮我看看好不好？', choices: [
        C('没问题', { bond: 1, stats: { social: 1 } }, '给——重点看第二段，那个转圈我总觉得差点什么。', 'n2'),
        C('我怕我看不出门道', { stats: { mood: 1 } }, '没关系，你就说「哪里好看哪里怪」，直觉最准了。'),
      ] },
      n2: { line: '你说这里手再打开一点会更好看？……哇，真的诶！你眼睛好毒。', choices: [
        C('瞎说的，蒙对了', { stats: { mood: 3 } }, '蒙的也这么准，下次还问你。'),
        C('多看就懂了', { bond: 2, stats: { social: 1 } }, '那以后我的视频都先给你过目！'),
      ] },
    }),
    S({
      n1: { line: '周末想编一支新舞，正好缺个观众！', choices: [
        C('观众就位', { bond: 2, stats: { mood: 2 } }, '好！那我开始咯……这支舞的名字还没定，你看完帮我想一个？', 'n2'),
        C('缺伴舞吗', { bond: 1, stats: { social: 3, energy: -4 } }, '欸？！你认真的？来来来，C 位让给你一半！'),
      ] },
      n2: { line: '……呼，跳完了！怎么样怎么样？哪里印象最深？', choices: [
        C('最后那个定格', { bond: 2, stats: { mood: 2 } }, '英雄所见略同！那个动作我练了三天。'),
        C('全程都很好看', { bond: 1, stats: { mood: 3 } }, '谢谢——有观众的练习，果然不一样。'),
      ] },
    }),
  ],
  maoyou: [
    S({
      n1: { line: '……这个模型的骨架好像有点问题。你会改模型吗？', choices: [
        C('我可以试试', { bond: 2, stats: { social: 2, energy: -3 } }, '太好了！那就拜托你了。', 'n2'),
        C('我不会诶', {}, '啊……没关系。', 'n3'),
      ] },
      n2: { line: '你看这里，关节的限位器装反了，所以手臂抬不起来。帮我递一下那把蓝色钳子？', choices: [
        C('递过去', { bond: 2, stats: { mood: 1 } }, '谢谢。……好了！你看，抬起来了。'),
        C('蓝色的是哪把', { stats: { mood: 2 } }, '呃，左边数第二把……对就是它。看来我们还需要磨合。'),
      ] },
      n3: { line: '那……我拆给你看？反正也要重装。你可以帮我记一下零件顺序吗？', choices: [
        C('好，我记', { bond: 2, stats: { social: 1 } }, '拜托了。第一步，卸下肩胛的外甲……'),
        C('我看着就好', { stats: { mood: 1 } }, '也行。那你坐着，别碰那瓶胶水就行。'),
      ] },
    }),
    S({
      n1: { line: '昨晚想到一个改造方案，今天想验证一下。你有空吗？', choices: [
        C('有，说来听听', { bond: 1, stats: { social: 2 } }, '简单说，就是把腰部的球形关节换成双段式的，可动范围能大一圈。', 'n2'),
        C('今天只想摸鱼', { stats: { mood: 2 } }, '……好吧。那我自己先画图纸，你摸鱼的时候帮我看着点胶水别干。'),
      ] },
      n2: { line: '理论上可行，但换完要重新调平衡。你觉得我是先改腰，还是先改腿？', choices: [
        C('先改腰', { bond: 1, stats: { explore: 1 } }, '嗯，中心先定下来，四肢就好调了。就这么办。'),
        C('先改腿', { bond: 1, stats: { explore: 1 } }, '也行，站得稳才能摆姿势。听你的。'),
      ] },
    }),
    S({
      n1: { line: '零件终于到了，今天有得忙了。要不要来看看？', choices: [
        C('来了', { bond: 1, stats: { social: 1 } }, '给，你拆这个小的，我拆大的。小心别崩飞了——上次一颗螺丝找了半小时。', 'n2'),
        C('拆快递最快乐', { stats: { mood: 3 } }, '对吧对吧！你果然懂。', 'n2'),
      ] },
      n2: { line: '零件全对，一个没缺！今天运气不错。照这个进度，周末就能试着合体了。', choices: [
        C('期待成品', { bond: 2, stats: { mood: 2 } }, '嗯！到时候第一个给你看。'),
        C('缺了你打算怎么办', { stats: { mood: 2 } }, '缺了？那就只能自己打磨一个了……千万别缺。'),
      ] },
    }),
    S({
      n1: { line: '这台机体的平衡还是不太对……你有什么想法吗？', choices: [
        C('脚掌加重试试', { bond: 2, stats: { explore: 2 } }, '加重……有道理！重心下移到脚掌，站得就稳了。我去找配重块。', 'n2'),
        C('换个姿势摆', { stats: { mood: 1 } }, '嗯，也是一种思路——平衡不够，姿势来凑。'),
      ] },
      n2: { line: '你看，加了配重之后单脚都能站住了！……就是脚掌厚了一圈，有点像拖鞋。', choices: [
        C('拖鞋也可爱', { bond: 2, stats: { mood: 3 } }, '哈哈，那就当它是居家款机体吧。'),
        C('实用最重要', { bond: 1 }, '对，站得稳比好看重要……大概。'),
      ] },
    }),
    S({
      n1: { line: '工具箱整理好了，效率应该会高一点。今天改哪台好呢。', choices: [
        C('改最喜欢的那台', { bond: 1, stats: { mood: 2 } }, '好，那就这台初代机。', 'n2'),
        C('改最旧的那台', { stats: { explore: 1 } }, '好，那就这台最老的。', 'n3'),
      ] },
      n2: { line: '最喜欢的是这台初代机……说实话有点下不去手。但你说得对，好机体就该被好好对待。', choices: [
        C('从骨架开始检查', { bond: 1, stats: { social: 1 } }, '嗯，稳妥。', 'n4'),
        C('直接上新关节', { stats: { mood: 2 } }, '激进派啊……行！', 'n4'),
      ] },
      n3: { line: '最旧的这台螺丝都锈了，得先除锈。不过复活老伙计最有成就感。', choices: [
        C('我来帮你除锈', { bond: 2, stats: { social: 2, energy: -2 } }, '谢了，那瓶除锈剂递你。', 'n4'),
        C('我负责记录步骤', { stats: { social: 1 } }, '好，拆到哪步都靠你记了。', 'n4'),
      ] },
      n4: { line: '决定了，开工！今天应该能改完一半——你帮我打个下手？', choices: [
        C('好', { bond: 2, stats: { social: 2, energy: -2 } }, '谢了。那就开始吧。'),
        C('我负责加油', { stats: { mood: 3 } }, '……也行，精神上的扳手也很重要。'),
      ] },
    }),
    S({
      n1: { line: '改造进度过半了，要不要看看半成品？', choices: [
        C('看', { bond: 1, stats: { mood: 1 } }, '当当——虽然现在还插着一堆线，但你看这个肩部的可动！', 'n2'),
        C('半成品有什么好看', { stats: { mood: 1 } }, '你不懂，半成品才有「正在变成什么」的感觉。'),
      ] },
      n2: { line: '昨天试转的时候它差点散架，吓死我了。不过改造就是这样，失败九十九次，成功一次。', choices: [
        C('那成功的那次给我看', { bond: 2, stats: { mood: 2 } }, '一言为定。'),
        C('九十九次也太多了', { stats: { mood: 3 } }, '哈哈，习惯就好。'),
      ] },
    }),
    S({
      n1: { line: '周末适合慢慢打磨细节。你来帮我递工具吗？', choices: [
        C('来了', { bond: 2, stats: { social: 2 } }, '好。今天打磨水口——砂纸从粗到细，换的时候我喊你。', 'n2'),
        C('打磨是什么', { stats: { social: 1 } }, '呃，就是把零件表面的毛刺磨平……你来看一眼就知道了。', 'n2'),
      ] },
      n2: { line: '你听，砂纸的声音从沙沙变成嘶嘶，就说明快磨好了。是不是很治愈？', choices: [
        C('有点困', { stats: { mood: 3 } }, '喂！……算了，打磨确实催眠。困就靠一会儿吧。'),
        C('治愈', { bond: 2, stats: { mood: 2 } }, '对吧。周末就该这样过。'),
      ] },
    }),
  ],
  yu: [
    S({
      n1: { line: '你经常来这个世界吗？我第一次来，感觉好棒！', choices: [
        C('我也是第一次来', { bond: 1, stats: { social: 1, mood: 1 } }, '哈哈，那我们算是同好了！', 'n2'),
        C('偶尔来，这里很放松', { stats: { social: 2 } }, '嗯嗯，我也是这样觉得的。', 'n3'),
      ] },
      n2: { line: '那正好！两个新人一起迷路，总比一个人迷路强。你想先去哪里？', choices: [
        C('海边', { bond: 1, stats: { explore: 2 } }, '好耶，海边！听说那里的日落很厉害。'),
        C('咖啡馆', { bond: 1, stats: { social: 1 } }, '走！探索的第一步是先补充咖啡因。'),
      ] },
      n3: { line: '那你一定有推荐的地方吧？带我走一遍你的路线，我请你喝东西！', choices: [
        C('成交', { bond: 2, stats: { social: 2 } }, '耶！那就说定了，向导大人。'),
        C('路线保密', { stats: { mood: 3 } }, '欸——小气！那我自己探索，发现了也不告诉你。……开玩笑的啦。'),
      ] },
    }),
    S({
      n1: { line: '昨天去的那个世界也不错，但还是这里最让我放松。', choices: [
        C('这里确实舒服', { bond: 1, stats: { mood: 2 } }, '对吧！我已经把这里标记成「常驻地」了。', 'n2'),
        C('昨天那个什么样', { stats: { explore: 2 } }, '那边是雪山主题，好看是好看，就是冷得我直跺脚。', 'n3'),
      ] },
      n2: { line: '你觉得这里的哪个角落最好？我在选我的「秘密基地」。', choices: [
        C('防波堤尽头', { bond: 2, stats: { explore: 2 } }, '哦——！那里看海确实一绝。那它就是候选一号了。'),
        C('咖啡馆窗边', { bond: 1, stats: { mood: 2 } }, '嗯，适合下雨天待着的基地。记下了。'),
      ] },
      n3: { line: '雪山上有条路走到一半会突然看到整片云海，当时我就哇出声了。', choices: [
        C('想去看看', { bond: 1, stats: { explore: 2 } }, '是吧！改天带你去，我认路。'),
        C('怕冷', { stats: { mood: 2 } }, '哈哈，那还是这里好，四季如春。'),
      ] },
    }),
    S({
      n1: { line: '今天打算去探索没去过的房间，要一起吗？', choices: [
        C('一起', { bond: 1, stats: { explore: 2, energy: -2 } }, '好！我列了三个候选，你抽签决定先去哪个。', 'n2'),
        C('今天想宅着', { stats: { mood: 2 } }, '好吧，那我探完回来跟你汇报。'),
      ] },
      n2: { line: '抽到这个——#3000 号房，备注写着「什么都没有」。什么都没有的房间，你不觉得最可疑吗？', choices: [
        C('确实可疑', { bond: 2, stats: { explore: 2 } }, '对吧！走，现在就去。'),
        C('也可能真的什么都没有', { stats: { mood: 2 } }, '那我们就当第一个证明它「什么都没有」的人！'),
      ] },
    }),
    S({
      n1: { line: '我列了个探索清单，已经完成大半了！', choices: [
        C('我看看', { bond: 1, stats: { social: 1 } }, '给——划掉的都是去过的。剩下这三个，你帮我挑一个？', 'n2'),
        C('好厉害', { stats: { mood: 2 } }, '嘿嘿，都是一步一步走出来的嘛。'),
      ] },
      n2: { line: '「在日落时分的防波堤上坐着发呆」……这条是谁写的？哦，是我昨天加的。阿澈推荐的。', choices: [
        C('那今天就去完成它', { bond: 2, stats: { explore: 2 } }, '好！正好今天天气不错。'),
        C('发呆也算探索？', { stats: { mood: 3 } }, '算！高质量的探索包括高质量的发呆。'),
      ] },
    }),
    S({
      n1: { line: '听说聚会大厅晚上很热闹，你去过吗？', choices: [
        C('去过几次', { stats: { social: 2 } }, '真的吗？那里的人多吗？我稍微有点紧张……', 'n2'),
        C('没有，不敢去', { stats: { mood: 1 } }, '我也是！那……要不要结伴壮胆？', 'n3'),
      ] },
      n2: { line: '要不今晚你带我一次？你负责打招呼，我负责在旁边笑。', choices: [
        C('分工明确', { bond: 2, stats: { social: 2 } }, '耶，完美搭档！'),
        C('我也只会笑', { stats: { mood: 3 } }, '那完了，我们两个社恐。……那就一起去门口看看就走！'),
      ] },
      n3: { line: '就这么定了！人多有个伴就不慌了。听说大厅晚上有即兴表演？', choices: [
        C('小弥会去跳舞', { bond: 1, stats: { social: 2 } }, '诶？那必须去捧场了！'),
        C('去了才知道', { stats: { explore: 1 } }, '也是，探索精神！'),
      ] },
    }),
    S({
      n1: { line: '发现了一个新世界，先记下来，改天一起去？', choices: [
        C('什么世界', { bond: 1, stats: { explore: 1 } }, '好像是个深夜食堂主题的世界，这个点说出来我都有点饿了。', 'n2'),
        C('好啊，记我一票', { bond: 2, stats: { social: 1 } }, '一票收到！候选名单上你的名字排第一个。', 'n2'),
      ] },
      n2: { line: '等我把路线摸熟了就带你去。新世界第一天通常有很多彩蛋，去晚了就没了。', choices: [
        C('那你快去摸', { stats: { mood: 2 } }, '好嘞！等我消息。'),
        C('别一个人乱跑', { bond: 2, stats: { mood: 1 } }, '……放心啦，我会小心的。'),
      ] },
    }),
    S({
      n1: { line: '探索了一周，最喜欢的还是这里。你呢？', choices: [
        C('我也是', { bond: 3, stats: { mood: 2 } }, '真的？！那……下周也在这里集合？老地方，老时间。', 'n2'),
        C('我还想去更多地方', { stats: { explore: 2 } }, '也对，世界这么大。那这里就当我们的据点？', 'n3'),
      ] },
      n2: { line: '那就说定了。下周见的时候，我要把这一周的探索手记都讲给你听。', choices: [
        C('我等着', { bond: 2, stats: { mood: 2 } }, '嗯！一言为定。'),
        C('我也攒了一周的故事', { bond: 2, stats: { social: 2 } }, '太好了，那要聊到天黑了。'),
      ] },
      n3: { line: '据点里要有暗号。敲门三长两短，怎么样？', choices: [
        C('幼稚', { stats: { mood: 3 } }, '哈哈，幼稚才好玩嘛。'),
        C('好，三长两短', { bond: 2, stats: { mood: 2 } }, '成交！据点就拜托你常来看看了。'),
      ] },
    }),
  ],
}

// 节点/选项归一化(阶段 8a):字面量里的单句 line/reply 升级为 lines/replies 数组,
// 补齐 image/replyImage 默认值;多句节点直接写字面量 lines: [...] 即可。
function normalizeDialogue(dialogue) {
  for (const days of Object.values(dialogue)) {
    for (const script of days) {
      for (const node of Object.values(script.nodes)) {
        if (node.line != null) { node.lines = Array.isArray(node.line) ? node.line : [node.line]; delete node.line }
        node.image = node.image ?? null
        for (const choice of node.choices) {
          if (choice.reply != null) { choice.replies = Array.isArray(choice.reply) ? choice.reply : [choice.reply]; delete choice.reply }
          choice.replyImage = choice.replyImage ?? null
        }
      }
    }
  }
  return dialogue
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
  dialogue: normalizeDialogue(dialogue),
  // 房间事件直接使用最终消息形状，每个事件仅含第 1~7 天。
  events: [
    {
      id: 'beach-rising-tide', roomId: 'beach-1024', title: '涨潮时分', icon: '🌊',
      scripts: [
        { messages: [
          { speaker: { npcId: 'ache' }, lines: ['你看，浪快碰到那块浅色石头了。', '我想拍一组照片，记下这一周的潮水。'], image: null },
          { speaker: { name: '钓鱼大爷', avatar: '🎣' }, lines: ['就在步道上看吧，涨潮时别往下走。', '我收竿的时候，顺便给你们报个时。'], image: null },
          { speaker: { npcId: 'ache' }, lines: ['好，那第一张就在这里拍。', '今天的海，先替我们记住了。'], image: null },
        ] },
        { messages: [
          { speaker: { npcId: 'ache' }, lines: ['我带了昨天的照片。你看，石头旁边还是干的。'], image: null },
          { speaker: { name: '钓鱼大爷', avatar: '🎣' }, lines: ['今天浪来得早些。我的小凳子都往后挪了。'], image: null },
          { speaker: { npcId: 'ache' }, lines: ['那我们也往里站一点。', '同一个地方，原来每天都有新东西看。'], image: null },
        ] },
        { messages: [
          { speaker: { npcId: 'ache' }, lines: ['第三张了。今天想把等潮水的人也拍进去。'], image: null },
          { speaker: { name: '钓鱼大爷', avatar: '🎣' }, lines: ['拍我呀？那我把帽子戴正。你们想怎么拍？'], image: null },
          { choice: { options: [
            { label: '帮忙找个角度', effects: { stats: { explore: 2, social: 1 } }, reply: [
              { speaker: { npcId: 'ache' }, lines: ['从栏杆这边拍？嗯，帽檐刚好接住一点光。'], image: null },
              { speaker: { name: '钓鱼大爷', avatar: '🎣' }, lines: ['那我就坐稳了，今天当一回模特。'], image: null },
            ] },
            { label: '陪大爷聊两句', effects: { stats: { social: 2, mood: 1 } }, reply: [
              { speaker: { name: '钓鱼大爷', avatar: '🎣' }, lines: ['我年轻时也爱拍照。就是每回洗出来，总少半个脑袋。'], image: null },
            ] },
          ] } },
          { speaker: { npcId: 'ache' }, lines: ['拍好了，大爷笑得特别自然。', '今天这张，连等候都有了表情。'], image: null },
        ] },
        { messages: [
          { speaker: { name: '钓鱼大爷', avatar: '🎣' }, lines: ['哟，照片带来了？让我把眼镜找出来。'], image: null },
          { speaker: { npcId: 'ache' }, lines: ['这张送您。背面写了昨天的日期。'], image: null },
          { speaker: { name: '钓鱼大爷', avatar: '🎣' }, lines: ['拍得真精神。回去给家里人看看。', '今天没钓到鱼，也不算空手啦。'], image: null },
          { speaker: { npcId: 'ache' }, lines: ['那今天拍这把空凳子吧。您先回去，路上慢点。'], image: null },
        ] },
        { messages: [
          { speaker: { npcId: 'ache' }, lines: ['风有点大，我把相机带子绕紧了。', '今天就在步道内侧拍，不往海边靠。'], image: null },
          { speaker: { name: '钓鱼大爷', avatar: '🎣' }, lines: ['我也没带鱼竿，出来走两步。昨天那张照片，家里人很喜欢。'], image: null },
          { speaker: { npcId: 'ache' }, lines: ['那就好。你看，浪花把那块石头整个盖住了。', '第五张，是海精神十足的一天。'], image: null },
        ] },
        { messages: [
          { speaker: { npcId: 'ache' }, lines: ['已经攒了五张。明天拍完，就能装进小相册了。'], image: null },
          { speaker: { name: '钓鱼大爷', avatar: '🎣' }, lines: ['相册总得有个名字。要不你们一起想想？'], image: null },
          { choice: { options: [
            { label: '叫「等浪来的时候」', effects: { stats: { mood: 3 } }, reply: [
              { speaker: { npcId: 'ache' }, lines: ['喜欢这个。听起来不用赶时间。'], image: null },
            ] },
            { label: '叫「步道上的老朋友」', effects: { stats: { social: 3 } }, reply: [
              { speaker: { name: '钓鱼大爷', avatar: '🎣' }, lines: ['才几天就成老朋友了？哈哈，这名字亲切。'], image: null },
              { speaker: { npcId: 'ache' }, lines: ['那封面得给您的小凳子留个位置。'], image: null },
            ] },
          ] } },
          { speaker: { npcId: 'ache' }, lines: ['名字先记在纸上。来，今天这张还没拍呢。', '刚好，浪又到了。'], image: null },
        ] },
        { messages: [
          { speaker: { npcId: 'ache' }, lines: ['最后一张拍好了。七天的海，刚好装满这几页。'], image: null },
          { speaker: { name: '钓鱼大爷', avatar: '🎣' }, lines: ['第一天还站得远远的，现在都知道来这儿找我了。'], image: null },
          { speaker: { npcId: 'ache' }, lines: ['相册给您也留了一本。以后翻到它，就想起这周的风。'], image: null },
          { speaker: { name: '钓鱼大爷', avatar: '🎣' }, lines: ['好，我收着。哪天想看海了，就过来坐坐。', '不带相机也行。'], image: null },
        ] },
      ],
    },
    {
      id: 'cafe-counter-chat', roomId: 'cafe-1101', title: '柜台边的闲聊', icon: '☕',
      scripts: [
        { messages: [
          { speaker: { npcId: 'xiaomi' }, lines: ['练完舞过来，连推门都想跟着拍子。', '咦，柜台上多了一本小册子？'], image: null },
          { speaker: { name: '店主', avatar: '👩‍🍳' }, lines: ['刚放的留言本。想写点什么都可以，今天吃了什么也行。'], image: null },
          { speaker: { npcId: 'xiaomi' }, lines: ['那我写：今天的热牛奶，救活了一个练舞的人。'], image: null },
        ] },
        { messages: [
          { speaker: { name: '店主', avatar: '👩‍🍳' }, lines: ['你昨天那句话，下面有人画了个小太阳。'], image: null },
          { speaker: { npcId: 'xiaomi' }, lines: ['真的诶。还画了两条小短腿，像在跳舞。'], image: null },
          { speaker: { name: '店主', avatar: '👩‍🍳' }, lines: ['笔就在旁边。慢慢看，杯子还烫着呢。'], image: null },
        ] },
        { messages: [
          { speaker: { npcId: 'xiaomi' }, lines: ['今天腿酸，我就给小太阳画把椅子吧。'], image: null },
          { speaker: { name: '店主', avatar: '👩‍🍳' }, lines: ['也给自己挑把舒服的。靠窗那张刚擦好。'], image: null },
          { speaker: { npcId: 'xiaomi' }, lines: ['好。今天的留言就写，坐着也能听完一首歌。'], image: null },
        ] },
        { messages: [
          { speaker: { name: '店主', avatar: '👩‍🍳' }, lines: ['有人在椅子旁边画了张桌子。你看，还摆着一杯牛奶。'], image: null },
          { speaker: { npcId: 'xiaomi' }, lines: ['再画下去，这页要变成我们店里了。', '不过桌子有点歪，跟我刚学转圈时一样。'], image: null },
          { speaker: { name: '店主', avatar: '👩‍🍳' }, lines: ['歪一点也没事。看得出是张能坐下来聊天的桌子。'], image: null },
        ] },
        { messages: [
          { speaker: { npcId: 'xiaomi' }, lines: ['这页只剩一个小角落了。要不要一起添最后一笔？'], image: null },
          { speaker: { name: '店主', avatar: '👩‍🍳' }, lines: ['给，笔还有墨水。画画或者写句话，都好。'], image: null },
          { choice: { options: [
            { label: '画一只趴着的猫', effects: { stats: { mood: 2, explore: 1 } }, reply: [
              { speaker: { npcId: 'xiaomi' }, lines: ['尾巴圆圆的，好可爱。它比我还会找地方休息。'], image: null },
            ] },
            { label: '写「今天也辛苦啦」', effects: { stats: { mood: 1, social: 2 } }, reply: [
              { speaker: { name: '店主', avatar: '👩‍🍳' }, lines: ['这句话，我也收到了。谢谢你。'], image: null },
              { speaker: { npcId: 'xiaomi' }, lines: ['嗯，你也辛苦啦。今天就在这里多坐一会儿。'], image: null },
            ] },
          ] } },
          { speaker: { name: '店主', avatar: '👩‍🍳' }, lines: ['正好填满一页。先摊着，等墨干了再合上。'], image: null },
        ] },
        { messages: [
          { speaker: { name: '店主', avatar: '👩‍🍳' }, lines: ['昨天那页复印了一张，夹在柜台的小相框里了。原本还在册子里。'], image: null },
          { speaker: { npcId: 'xiaomi' }, lines: ['从一杯牛奶开始，居然画出了这么热闹的一角。'], image: null },
          { speaker: { name: '店主', avatar: '👩‍🍳' }, lines: ['有客人问是谁画的。我说，是来这里歇脚的人一起画的。'], image: null },
        ] },
        { messages: [
          { speaker: { npcId: 'xiaomi' }, lines: ['一周过得好快。现在推门进来，会先看看这个相框。'], image: null },
          { speaker: { name: '店主', avatar: '👩‍🍳' }, lines: ['本子翻到新的一页了。不过今天不想写，也没关系。'], image: null },
          { speaker: { npcId: 'xiaomi' }, lines: ['那今天先喝牛奶，听你们聊一会儿。', '有张熟悉的椅子等着，真好。'], image: null },
        ] },
      ],
    },
  ],
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
