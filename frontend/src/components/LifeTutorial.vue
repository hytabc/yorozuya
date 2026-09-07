<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import { LIFE_TUTORIAL_STEPS as steps, lifeTutorialKey, spotlightRect } from '../composables/lifeTutorialSteps'
const props = defineProps({ ready: Boolean, userId: [Number, String] })
const emit = defineEmits(['prepare','close'])
const active = ref(false), index = ref(0), rect = ref(null), viewport = ref({ width: 1, height: 1 }), experienced = ref(false)
let preparation = 0
const step = computed(() => steps[index.value])
let frame, originalFocus, originalScroll, autoKey, activeKey
const cardEl = ref(null)
function measure() {
  viewport.value = { width: window.innerWidth, height: window.innerHeight }
  const actionView = experienced.value ? { history:'.history-drawer', worlds:'.drawer-body', roster:'.npc-avatars' }[step.value.action] : null
  const target = document.querySelector(actionView || step.value.target)
  rect.value = spotlightRect(target?.getBoundingClientRect(), viewport.value.width, viewport.value.height)
}
async function prepare() {
  if (!active.value) return
  const own = ++preparation
  experienced.value = false
  emit('prepare', step.value.prepare || 'main')
  await nextTick()
  if (!active.value || own !== preparation) return
  const target = document.querySelector(step.value.target)
  target?.scrollIntoView({ block:'nearest', inline:'nearest', behavior:'instant' })
  measure()
  cardEl.value?.focus({ preventScroll:true })
}
function tick() { if (!active.value) return; measure(); frame = requestAnimationFrame(tick) }
function start() {
  if (active.value || !props.ready || !lifeTutorialKey(props.userId)) return
  activeKey = lifeTutorialKey(props.userId)
  originalFocus = document.activeElement; originalScroll = window.scrollY
  active.value = true; index.value = 0
  prepare(); frame = requestAnimationFrame(tick)
  document.addEventListener('keydown', keydown, true)
}
function close(mark = true) {
  if (mark) { try { localStorage.setItem(activeKey, 'done') } catch {} }
  active.value = false; cancelAnimationFrame(frame)
  document.removeEventListener('keydown', keydown, true)
  emit('close')
  nextTick(() => { window.scrollTo({ top:originalScroll || 0, behavior:'instant' }); originalFocus?.focus?.({ preventScroll:true }) })
}
function next() { if (index.value === steps.length - 1) close(); else { index.value++; prepare() } }
function prev() { if (index.value > 0) { index.value--; prepare() } }
function targetClick() {
  if (step.value.action && !experienced.value) {
    emit('prepare', step.value.action)
    experienced.value = true
    nextTick(measure)
  } else if (step.value.action) next()
}
function keydown(event) {
  if (!active.value) return
  // Prevent keyboard access to obscured game controls, including existing focus.
  if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); close(); return }
  if (event.key === 'Tab') {
    event.preventDefault(); event.stopImmediatePropagation()
    const buttons = [...cardEl.value.querySelectorAll('button:not(:disabled)')]
    const i = buttons.indexOf(document.activeElement), direction = event.shiftKey ? -1 : 1
    buttons[(i + direction + buttons.length) % buttons.length]?.focus()
  } else if (!cardEl.value?.contains(event.target)) { event.preventDefault(); event.stopImmediatePropagation() }
}
watch(() => [props.ready, props.userId], () => {
  const key = lifeTutorialKey(props.userId)
  if (active.value && (!props.ready || key !== autoKey)) close(false)
  if (!props.ready || !key || autoKey === key) return
  autoKey = key
  let seen = false; try { seen = localStorage.getItem(key) === 'done' } catch {}
  if (!seen) start()
}, { immediate:true, flush:'post' })
onBeforeUnmount(() => { if (active.value) close(false); cancelAnimationFrame(frame); document.removeEventListener('keydown', keydown, true) })
defineExpose({ start })
const holeStyle = computed(() => rect.value ? { left:rect.value.left+'px',top:rect.value.top+'px',width:rect.value.width+'px',height:rect.value.height+'px' } : {})
const panels = computed(() => {
  const r = rect.value, {width:w,height:h} = viewport.value
  return r ? [ {left:0,top:0,width:w,height:r.top}, {left:0,top:r.top,width:r.left,height:r.height}, {left:r.left+r.width,top:r.top,width:w-r.left-r.width,height:r.height}, {left:0,top:r.top+r.height,width:w,height:h-r.top-r.height} ] : [{left:0,top:0,width:w,height:h}]
})
const cardStyle = computed(() => {
  const r = rect.value, h = viewport.value.height
  const side = r && r.left + r.width/2 < viewport.value.width/2 ? { left:'auto', right:'18px' } : { left:'18px', right:'auto' }
  return { ...side, ...(r && r.top > h/2 ? { top:'18px' } : { bottom:'18px' }) }
})
</script>
<template>
  <Teleport to="body">
    <div v-if="active" class="life-tutorial" aria-label="小白新手指引">
      <div v-for="(p,i) in panels" :key="i" class="tutorial-mask" :style="Object.fromEntries(Object.entries(p).map(([k,v]) => [k,v+'px']))" @wheel.prevent @touchmove.prevent />
      <button v-if="rect" class="tutorial-hole" :class="{ actionable:step.action }" :style="holeStyle" :aria-label="step.action ? '体验：'+step.title : step.title" tabindex="-1" @click.stop.prevent="targetClick" @wheel.prevent />
      <section ref="cardEl" class="tutorial-card" :style="cardStyle" tabindex="-1" role="dialog" aria-modal="true" :aria-labelledby="'life-guide-title'">
        <div class="xiaobai-avatar" aria-label="小白">白</div>
        <div class="tutorial-copy"><small>小白 · 新手指引模板 {{ index+1 }}/{{ steps.length }}</small><h3 id="life-guide-title">{{ step.title }}</h3><p>{{ step.text }}</p>
          <small v-if="!rect">此位置暂不可见，仍可阅读说明并点击下一步。</small>
          <small v-else-if="step.action">{{ experienced ? '已展开教学位置，点击下一步继续。' : '可点击亮起的位置体验（仅教学，不执行游戏操作）。' }}</small>
          <div class="tutorial-controls"><button @click="close()">跳过</button><span></span><button :disabled="index===0" @click="prev">上一步</button><button class="primary" @click="next">{{ index===steps.length-1 ? '完成指引' : '下一步' }}</button></div>
        </div>
      </section>
    </div>
  </Teleport>
</template>
<style scoped>
.life-tutorial { position:fixed; inset:0; z-index:2147483000; pointer-events:none; }
.tutorial-mask { position:fixed; background:rgba(7,15,12,.76); pointer-events:auto; }
.tutorial-hole { position:fixed; border:2px solid #b2edb4; border-radius:9px; padding:0; background:transparent; box-shadow:0 0 18px #a0e8ac80; pointer-events:auto; cursor:default; }
.tutorial-hole.actionable { cursor:pointer; }
.tutorial-card { position:fixed; left:18px; width:min(440px,calc(100vw - 36px)); max-height:calc(100vh - 36px); overflow:auto; box-sizing:border-box; display:flex; gap:12px; padding:18px; border-radius:16px; background:#fffdf4; border:1px solid #b5ceba; color:#263c2e; box-shadow:0 8px 40px #0005; pointer-events:auto; outline:none; }
.xiaobai-avatar { flex-shrink:0; display:grid; place-items:center; width:46px; height:46px; border-radius:50% 50% 40% 40%; color:#237a57; background:#e6f3e5; border:2px solid #fff; font-size:23px; }
.tutorial-copy { flex:1; min-width:0; }.tutorial-copy small { font-size:11px;color:#6a806e; }.tutorial-copy h3 { margin:6px 0;font-size:17px; }.tutorial-copy p { line-height:1.7;font-size:13px;margin:8px 0; }
.tutorial-controls { display:flex;align-items:center;gap:6px;margin-top:14px; }.tutorial-controls span {flex:1}.tutorial-controls button { padding:7px 9px; border:1px solid #cad8c9;border-radius:7px;background:#f5f8ef;color:#33553d;cursor:pointer; }.tutorial-controls .primary { background:#237a57;color:#fff;border-color:#237a57; }.tutorial-controls button:disabled {opacity:.4;cursor:default}.tutorial-controls button:focus-visible {outline:2px solid #237a57;outline-offset:2px}
</style>
