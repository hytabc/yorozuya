<script setup>
// 默认七日结局展示当前结算;「重新开始」由父组件确认后重置整段人生。
defineProps({
  stats: { type: Object, required: true },
  npcs: { type: Array, required: true },
})
const emit = defineEmits(['close', 'restart'])
const statItems = [
  { key: 'mood', label: '心情' },
  { key: 'energy', label: '精力' },
  { key: 'social', label: '社交' },
  { key: 'explore', label: '探索' },
]
</script>

<template>
  <Teleport to="body">
    <div class="ending-overlay">
      <section class="ending-panel" role="dialog" aria-modal="true" aria-labelledby="life-ending-title">
        <header class="ending-header">
          <h2 id="life-ending-title">🌅 七日的旅程</h2>
        </header>
        <div class="ending-content">
          <p class="ending-story">晚风轻轻翻过手记，又一个七天落下帷幕。那些平凡的问候、偶然的相遇，已悄悄成为心底温暖的光。不必急着为这段时光寻找答案，你认真走过的每一步，都值得被温柔收藏。</p>
          <h3>此刻的你</h3>
          <dl class="stat-list">
            <div v-for="item in statItems" :key="item.key" class="stat-item">
              <dt>{{ item.label }}</dt>
              <dd>{{ stats[item.key] }}</dd>
            </div>
          </dl>
          <h3>相遇的温度</h3>
          <ul class="bond-list">
            <li v-for="npc in npcs" :key="npc.id">
              <div class="bond-label"><span>{{ npc.name }}</span><strong>{{ npc.bond }}</strong></div>
              <div class="bond-track" aria-hidden="true">
                <div class="bond-fill" :style="{ width: Math.max(0, Math.min(100, npc.bond)) + '%' }"></div>
              </div>
            </li>
          </ul>
        </div>
        <footer class="ending-footer">
          <button type="button" class="restart" @click="emit('restart')">重新开始</button>
          <button type="button" @click="emit('close')">收下这段回忆</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.ending-overlay {
  position: fixed; inset: 0; z-index: 9000;
  display: flex; align-items: center; justify-content: center;
  padding: 16px; box-sizing: border-box; background: rgba(0, 0, 0, .45);
}
.ending-panel {
  display: flex; flex-direction: column;
  width: 100%; max-width: 560px; max-height: 90vh;
  overflow: hidden; background: #fff; border-radius: 12px;
  box-shadow: 0 12px 40px rgba(25, 38, 32, .2); color: #69736e;
}
.ending-header { padding: 20px; border-bottom: 1px solid #d9dedb; }
.ending-header h2 { margin: 0; font-size: 20px; color: #237a57; }
.ending-content { padding: 20px; overflow-y: auto; min-height: 0; overscroll-behavior: contain; }
.ending-story { margin: 0 0 24px; font-size: 14px; line-height: 1.9; }
.ending-content h3 { margin: 0 0 12px; font-size: 14px; color: #237a57; }
.stat-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 0 0 24px; }
.stat-item { display: flex; justify-content: space-between; gap: 8px; padding: 12px; border-radius: 8px; background: #f5f6f4; font-size: 14px; }
.stat-item dd { margin: 0; font-weight: 600; color: #237a57; }
.bond-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 14px; }
.bond-label { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 6px; font-size: 13px; overflow-wrap: anywhere; }
.bond-label strong { color: #237a57; }
.bond-track { height: 4px; background: #d9dedb; border-radius: 999px; overflow: hidden; }
.bond-fill { height: 100%; background: #237a57; border-radius: inherit; }
.ending-footer { display: flex; gap: 10px; justify-content: center; padding: 16px 20px; border-top: 1px solid #d9dedb; }
.ending-footer button { padding: 10px 20px; border: 1px solid #237a57; border-radius: 8px; background: #237a57; color: #fff; font: inherit; font-size: 14px; cursor: pointer; }
.ending-footer .restart { background: #fff; color: #237a57; }
button:focus-visible { outline: 2px solid #237a57; outline-offset: 2px; }
</style>
