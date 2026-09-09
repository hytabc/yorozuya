<script setup>
// 左侧角色面板：角色卡 + 属性条 + 主操作(存档/重置当天/下一天)。
const props = defineProps({ game: { type: Object, required: true } })
const emit = defineEmits(['reset-today', 'show-ending'])
const { stats, tags, day, saveReady, saveBusy, saveConflict, save, nextDay } = props.game
const labels = { mood: '心情', energy: '精力', social: '社交', explore: '探索' }
</script>

<template>
  <aside class="char-panel">
    <div class="section-title">01 角色</div>
    <div class="char-card">
      <div class="avatar">☺</div>
      <div class="char-info">
        <h2>白昼梦</h2>
        <p>新人探索者</p>
        <div class="tags">
          <span v-for="t in tags" :key="t">{{ t }}</span>
        </div>
      </div>
    </div>
    <div class="stats-bars">
      <div v-for="(val, key) in stats" :key="key" class="stat-row">
        <span>{{ labels[key] }}</span>
        <div class="bar"><b :style="{ width: val + '%' }"></b></div>
        <strong>{{ val }}</strong>
      </div>
    </div>
    <div class="panel-actions">
      <button class="pa-primary" @click="save" :disabled="!saveReady || saveConflict || saveBusy">存档</button>
      <button class="pa-ghost" @click="day >= 7 ? emit('show-ending') : nextDay()" :disabled="!saveReady || saveConflict">{{ day >= 7 ? '🌅 查看结局' : '下一天' }}</button>
      <button class="pa-warm" @click="emit('reset-today')" :disabled="!saveReady || saveConflict"
              title="清空今天的对话、事件与动作进度（测试用）">↺ 重置当天</button>
      <small>对话将写入今天的手记</small>
    </div>
    <div class="prompt-text">今天，想去哪里看看？</div>
  </aside>
</template>

<style scoped>
.section-title {
  width: fit-content;
  padding: 4px 12px; border-radius: 999px;
  background: #e5f3eb;
  font-size: 12px; font-weight: 700; color: #237a57;
  margin-bottom: 12px; letter-spacing: 0.05em;
}
.char-panel { display: flex; flex-direction: column; }
.char-card {
  display: flex; align-items: center; gap: 16px;
  padding: 20px; background: #fff;
  border: 1px solid #e6eae6; border-radius: 14px;
  box-shadow: 0 4px 14px rgba(25, 38, 32, .05);
  margin-bottom: 20px;
}
.avatar {
  width: 64px; height: 64px; border-radius: 50%;
  background: linear-gradient(145deg, #e5f3eb, #c8e6d4);
  display: grid; place-items: center;
  font-size: 28px; border: 2px solid #fff;
  box-shadow: 0 2px 8px rgba(25, 38, 32, 0.08), 0 0 0 3px #eef6f0;
}
.char-info h2 { margin: 0 0 4px; font-size: 20px; font-family: Georgia, serif; }
.char-info p { margin: 0 0 8px; color: #69736e; font-size: 12px; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; }
.tags span {
  padding: 4px 8px; border-radius: 999px;
  background: #e5f3eb; color: #237a57;
  font-size: 10px; font-weight: 600;
}
.stats-bars {
  background: #fff; border: 1px solid #e6eae6;
  border-radius: 14px; padding: 20px; margin-bottom: 16px;
  box-shadow: 0 4px 14px rgba(25, 38, 32, .05);
}
.stat-row {
  display: grid; grid-template-columns: 40px 1fr 32px;
  align-items: center; gap: 12px; margin-bottom: 12px;
}
.stat-row:last-child { margin-bottom: 0; }
.stat-row span { font-size: 12px; color: #69736e; }
.stat-row strong { font-size: 13px; color: #18201d; text-align: right; }
.bar { height: 8px; border-radius: 999px; background: #edf1ed; overflow: hidden; }
.bar b { display: block; height: 100%; background: linear-gradient(90deg, #6cc49b, #237a57); border-radius: inherit; transition: width 0.3s ease; }
.prompt-text {
  padding: 16px 20px;
  background: linear-gradient(135deg, #e5f3eb, #f0f8f2);
  border: 1px solid #dcebe1; border-radius: 14px;
  color: #237a57; font-size: 13px; font-style: italic;
}
/* 面板内主操作:与全局三级按钮同风格,纵向排列更醒目 */
.panel-actions {
  display: flex; flex-direction: column; gap: 8px;
  padding: 14px 16px; margin-bottom: 16px;
  background: #fff; border: 1px solid #e6eae6; border-radius: 14px;
  box-shadow: 0 4px 14px rgba(25, 38, 32, .05);
}
.panel-actions button {
  width: 100%; padding: 9px 16px; border-radius: 999px;
  font-size: 13px; cursor: pointer; transition: all 0.2s;
}
.pa-primary {
  border: 0; background: #237a57; color: #fff;
  box-shadow: 0 3px 10px rgba(35, 122, 87, .28);
}
.pa-primary:hover:not(:disabled) { background: #1e6b4c; transform: translateY(-1px); }
.pa-ghost { border: 1px solid #cfe0d4; background: #fff; color: #237a57; }
.pa-ghost:hover:not(:disabled) { background: #e5f3eb; border-color: #237a57; }
.pa-warm { border: 1px solid #eadfc2; background: #fdf7ea; color: #a67c2e; }
.pa-warm:hover:not(:disabled) { background: #f8edd6; border-color: #d9b96a; }
.panel-actions button:disabled { opacity: .5; cursor: not-allowed; }
.panel-actions small { text-align: center; color: #9a9fa0; font-size: 11px; }
</style>
