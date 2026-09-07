<script setup>
import { computed, ref } from 'vue'

// 迷你剧本:二游界面演示数据(纯前端,以后接后端/真实剧本)
const script = [
  {
    who: '??', mood: '', text: '……夜里的世界,人比白天少。远处有个人举着相机,对着落地窗外的灯火。',
  },
  {
    who: '陌生玩家', mood: 'mild', text: '啊……抱歉,是不是吓到你了?我、我只是觉得这个角度的灯很好看。',
    choices: [
      { label: '“没事,我也觉得这里很好看。”', effect: '表达 +1', stats: { social: 2 } },
      { label: '“你在拍什么?我也想看看。”', effect: '好感 +2 · 探索 +1', stats: { social: 3, explore: 2 } },
      { label: '“我不太擅长和陌生人说话……”', effect: '心情 安稳', stats: { mood: 2 } },
    ],
  },
  {
    who: '阿澈', mood: 'bright', text: '我叫阿澈,平时喜欢到处拍世界。VRChat 里有好多只有这个点才会亮灯的地方,错过就可惜了。',
    choices: [
      { label: '“那你一定去过很多世界吧。”', effect: '探索 +2', stats: { social: 2, explore: 3 } },
      { label: '“明天……还能一起去看吗?”', effect: '好感 +3 · 关系加深', stats: { social: 4, mood: 2 } },
    ],
  },
  {
    who: '阿澈', mood: 'soft', text: '好啊。明天晚上九点,还是这里见。我带你去看一个像海一样的世界。',
    choices: [
      { label: '“嗯,说好了。”', effect: '约定成立 · 认识 阿澈', stats: { mood: 3, social: 2 } },
    ],
  },
  {
    who: '旁白', text: '夜色安静地落在你们之间。你忽然觉得,这个陌生的世界,好像也没有那么难靠近。', end: true },
]

const stage = ref(0)
const stats = ref({ mood: 72, energy: 66, social: 34, explore: 28 })
const picked = ref(false)
const lastGain = ref('')
const fade = ref(false)

const cur = computed(() => script[stage.value])
const hasChoices = computed(() => Boolean(cur.value.choices))

function pick(choice) {
  if (picked.value) return
  picked.value = true
  lastGain.value = choice.effect || ''
  const d = choice.stats || {}
  for (const k of Object.keys(d)) stats.value[k] = Math.min(100, Math.max(0, stats.value[k] + d[k]))
}

function advance() {
  fade.value = true
  setTimeout(() => {
    if (stage.value >= script.length - 1) {
      stage.value = 0
      stats.value = { mood: 72, energy: 66, social: 34, explore: 28 }
    } else {
      stage.value += 1
    }
    picked.value = false
    lastGain.value = ''
    fade.value = false
  }, 300)
}
</script>

<template>
  <div class="shell">
    <!-- 全屏场景 -->
    <div class="scene">
      <div class="sky" />
      <div class="window-glow" />
      <div class="arch" />
      <div class="floor" />
      <div class="lamp l1" /><div class="lamp l2" />
      <div class="dust" />
      <div class="vig" />
    </div>

    <!-- HUD -->
    <div class="hud">
      <button class="pill icon" aria-label="返回" @click="$router.back()">←</button>
      <span class="pill day">第 7 夜 · 21:40</span>
      <div class="pill stats">
        <i><b style="width: 72%">心情 {{ stats.mood }}</b></i>
        <i><b style="width: 66%">精力 {{ stats.energy }}</b></i>
        <i><b style="width: 34%">社交 {{ stats.social }}</b></i>
      </div>
    </div>

    <!-- 立绘 -->
    <transition name="pop">
      <div v-if="cur.who && cur.who !== '??' && cur.who !== '旁白'" class="sprite-wrap">
        <div class="sprite" :class="cur.mood">
          <div class="halo" />
          <div class="hair" /><div class="face"><span class="eye e1" /><span class="eye e2" /><span class="mouth" /></div>
          <div class="body" />
        </div>
        <span class="nameplate">{{ cur.who }}</span>
      </div>
    </transition>

    <!-- 对话层 -->
    <div class="stage">
      <transition name="msg">
        <div :key="stage + String(picked)" class="dialog" :class="{ silent: fade }">
          <div class="who" :class="{ note: cur.who === '旁白' || cur.who === '??' }">
            <span v-if="cur.who !== '旁白' && cur.who !== '??'">{{ cur.who }}</span>
            <span v-else>✦</span>
          </div>
          <p class="text">{{ cur.text }}</p>

          <div v-if="hasChoices && !picked" class="choices">
            <button v-for="(c, i) in cur.choices" :key="i" class="choice" @click="pick(c)">
              <span>{{ c.label }}</span>
              <em>{{ c.effect }}</em>
            </button>
          </div>

          <div v-else-if="picked" class="result">
            <transition name="gain"><span v-if="lastGain" class="gain">✦ {{ lastGain }}</span></transition>
            <button class="next" @click="advance">继续 →</button>
          </div>

          <button v-else-if="cur.end" class="next" @click="advance">再看一次这个夜晚 →</button>
        </div>
      </transition>
    </div>
  </div>
</template>

<style scoped>
.shell { position: fixed; inset: 0; z-index: 2000; overflow: hidden; color: #f1ede2; font-family: Inter, 'PingFang SC', 'Microsoft YaHei', sans-serif; user-select: none; }
/* 场景 */
.scene { position: absolute; inset: 0; }
.sky { position: absolute; inset: 0; background: linear-gradient(180deg, #141d31 0%, #20304a 38%, #39506b 70%, #587084 100%); }
.arch { position: absolute; left: 50%; bottom: 7%; width: 60vw; height: 74vh; transform: translateX(-50%); border-radius: 50% 50% 0 0 / 30% 30% 0 0; background: linear-gradient(180deg, rgba(158, 190, 200, .14), rgba(120, 150, 160, .26)); border: 1px solid rgba(222, 236, 230, .3); box-shadow: inset 0 0 130px rgba(170, 210, 220, .16); }
.arch::before { content: ''; position: absolute; left: 14%; right: 14%; bottom: -2px; height: 3px; border-radius: 3px; background: rgba(236, 220, 180, .6); filter: blur(2px); box-shadow: 0 0 30px 8px rgba(245, 225, 170, .3); }
.window-glow { position: absolute; left: 50%; bottom: 8%; width: 40vw; height: 44vh; transform: translateX(-50%); background: radial-gradient(closest-side, rgba(200, 220, 214, .2), transparent 72%); filter: blur(2px); }
.floor { position: absolute; left: 0; right: 0; bottom: 0; height: 15%; background: linear-gradient(180deg, #2c3b49, #1b2530); opacity: .94; }
.floor::before { content: ''; position: absolute; inset: 0; opacity: .25; background: repeating-linear-gradient(90deg, transparent 0 70px, rgba(200, 220, 220, .12) 70px 71px); }
.lamp { position: absolute; bottom: 14%; width: 8px; height: 86px; background: linear-gradient(#43505b, #242e38); }
.lamp.l1 { left: 15%; } .lamp.l2 { right: 15%; }
.lamp::after { content: ''; position: absolute; top: -13px; left: 50%; transform: translateX(-50%); width: 36px; height: 36px; border-radius: 50%; background: radial-gradient(circle, #ffe9ae, #dbb263); box-shadow: 0 0 32px 12px rgba(255, 214, 140, .4); }
.dust { position: absolute; inset: 0; background: radial-gradient(2px 2px at 18% 28%, #fff, transparent), radial-gradient(3px 3px at 72% 18%, #fff, transparent), radial-gradient(2px 2px at 42% 58%, #dfeae4, transparent), radial-gradient(2px 2px at 88% 52%, #ecd9ae, transparent); opacity: .55; animation: drift 8s ease-in-out infinite alternate; }
@keyframes drift { to { transform: translateY(-16px); } }
.vig { position: absolute; inset: 0; background: radial-gradient(130% 100% at 50% 42%, transparent 42%, rgba(7, 10, 16, .5) 90%, rgba(5, 8, 13, .78) 100%); }
/* HUD */
.hud { position: absolute; top: 0; left: 0; right: 0; z-index: 5; display: flex; align-items: center; gap: 10px; padding: max(16px, env(safe-area-inset-top)) 20px 0; }
.pill { display: inline-flex; align-items: center; border-radius: 999px; border: 1px solid rgba(255, 255, 255, .22); background: rgba(13, 18, 26, .38); backdrop-filter: blur(12px); }
.pill.icon { justify-content: center; width: 40px; height: 40px; font-size: 17px; color: rgba(255, 255, 255, .85); }
.pill.day { padding: 9px 16px; font-size: 12px; letter-spacing: .04em; color: rgba(240, 238, 226, .9); }
.pill.stats { gap: 14px; margin-left: auto; padding: 9px 16px; }
.pill.stats i { display: block; width: 64px; height: 5px; overflow: hidden; border-radius: 4px; background: rgba(255, 255, 255, .18); position: relative; }
.pill.stats i b { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #237a57, #57b98f); }
.pill.stats i:nth-child(1) b { background: linear-gradient(90deg, #d8a34e, #f0cf8c); }
.pill.stats i:nth-child(3) b { background: linear-gradient(90deg, #b56a77, #df9aa5); }
/* 立绘 */
.sprite-wrap { position: absolute; left: 50%; bottom: 14%; transform: translateX(-50%); z-index: 3; text-align: center; filter: drop-shadow(0 26px 40px rgba(0, 0, 0, .42)); }
.sprite { position: relative; width: 300px; height: 430px; }
.halo { position: absolute; left: 50%; top: 34px; width: 230px; height: 230px; transform: translateX(-50%); border-radius: 50%; background: radial-gradient(circle, rgba(255, 236, 200, .34), transparent 70%); }
.hair { position: absolute; left: 50%; top: 28px; width: 168px; height: 196px; transform: translateX(-50%) rotate(-6deg); border-radius: 52% 52% 44% 46%; background: linear-gradient(165deg, #4b5f54, #2b3b34); }
.hair::after { content: ''; position: absolute; left: -18px; top: 44px; width: 92px; height: 126px; border-radius: 60% 30% 55% 40%; background: #395049; transform: rotate(20deg); }
.face { position: absolute; left: 50%; top: 112px; width: 106px; height: 130px; transform: translateX(-50%); border-radius: 46% 46% 46% 46%; background: linear-gradient(180deg, #ffe4ce, #f5c9a6); }
.eye { position: absolute; top: 58px; width: 8px; height: 7px; border-radius: 50%; background: #46332e; }
.eye::after { content: ''; position: absolute; width: 3px; height: 3px; top: -4px; left: 1px; border-radius: 50%; background: #fff; opacity: .85; }
.eye.e1 { left: 26px; } .eye.e2 { right: 26px; }
.mouth { position: absolute; left: 50%; top: 92px; transform: translateX(-50%); width: 16px; height: 8px; border-bottom: 2px solid #b07a72; border-radius: 0 0 50% 50%; }
.body { position: absolute; left: 50%; bottom: -20px; width: 212px; height: 250px; transform: translateX(-50%); border-radius: 44% 44% 10% 10% / 26% 26% 8% 8%; background: linear-gradient(170deg, #4f7c6f, #33514b); box-shadow: inset 0 0 0 3px rgba(255, 255, 255, .13); }
.sprite.bright .hair { background: linear-gradient(165deg, #5d7466, #31463c); }
.sprite.mild .mouth { width: 12px; }
.nameplate { display: inline-block; margin-top: 4px; padding: 5px 16px; border-radius: 999px; background: rgba(10, 15, 22, .55); backdrop-filter: blur(8px); color: rgba(255, 255, 255, .9); font-size: 13px; letter-spacing: .18em; }
.pop-enter-active { transition: opacity .5s, transform .5s; } .pop-enter-from { opacity: 0; transform: translateX(-50%) translateY(16px); }
/* 对话层 */
.stage { position: absolute; left: 0; right: 0; bottom: 0; z-index: 6; padding: 0 max(22px, 5vw) max(26px, 4vw); }
.dialog { max-width: 1080px; margin: 0 auto; padding: 24px 30px 22px; border-radius: 18px 18px 0 0; border: 1px solid rgba(255, 255, 255, .2); border-bottom: 0; background: linear-gradient(180deg, rgba(13, 18, 26, .8), rgba(8, 12, 18, .92)); backdrop-filter: blur(16px); box-shadow: 0 -20px 70px rgba(0, 0, 0, .4); transition: opacity .3s; }
.dialog.silent { opacity: 0; }
.who { min-height: 30px; }
.who > span { display: inline-block; padding: 5px 13px; border-radius: 5px 5px 5px 0; background: #24463c; color: #ddf0e5; font-size: 12px; font-weight: 700; letter-spacing: .06em; }
.who.note > span { background: transparent; color: rgba(235, 226, 206, .75); font-size: 11px; letter-spacing: .3em; }
.text { margin: 8px 0 0; color: #f4efe3; font-size: clamp(15px, 1.9vw, 18px); line-height: 1.9; text-shadow: 0 1px 10px rgba(0, 0, 0, .5); }
.choices { display: flex; flex-direction: column; gap: 9px; margin-top: 18px; }
.choice { display: flex; align-items: center; gap: 12px; width: 100%; padding: 12px 16px; border-radius: 11px; border: 1px solid rgba(255, 255, 255, .3); color: #f6f0e4; background: rgba(255, 255, 255, .08); text-align: left; transition: .18s; cursor: pointer; }
.choice:hover { border-color: rgba(220, 236, 224, .95); background: rgba(255, 255, 255, .16); transform: translateX(4px); }
.choice span { flex: 1; font-size: 14.5px; }
.choice em { color: rgba(255, 255, 255, .6); font-size: 11px; font-style: normal; white-space: nowrap; }
.result { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
.gain { color: #ffe3a3; font-size: 12.5px; letter-spacing: .05em; }
.gain-enter-active { transition: all .5s ease; } .gain-enter-from { opacity: 0; transform: translateY(6px); }
.next { margin-left: auto; padding: 10px 20px; border-radius: 999px; border: 1px solid rgba(255, 255, 255, .45); color: #fff; background: rgba(255, 255, 255, .14); font-size: 13px; transition: .18s; cursor: pointer; }
.next:hover { background: rgba(255, 255, 255, .26); }
.msg-enter-active { transition: opacity .4s ease, transform .4s ease; } .msg-enter-from { opacity: 0; transform: translateY(12px); }
@media (max-width: 640px) {
  .sprite { transform: translateX(-50%) scale(.78); transform-origin: bottom center; bottom: 12%; }
  .sprite-wrap { bottom: 13%; }
  .pill.stats { gap: 8px; padding: 8px 11px; } .pill.stats i { width: 44px; }
  .dialog { padding: 18px 16px 18px; } .text { font-size: 15px; } .choice em { display: none; }
}
@media (prefers-reduced-motion: reduce) { * { animation-duration: .01ms !important; transition-duration: .01ms !important; } }
</style>
