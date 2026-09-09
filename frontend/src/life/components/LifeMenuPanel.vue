<script setup>
// 右侧功能入口：世界探索 / 好友 / 人生手记。样式从 LifeSimulator.vue 迁出，行为不变。
const props = defineProps({ game: { type: Object, required: true } })
const { panel, unlockedWorlds, friends, diaryHistory } = props.game
</script>

<template>
  <aside class="menu-panel">
    <div class="section-title">02 功能入口</div>
    <button data-life-guide="worlds" class="menu-item" @click="panel = 'worlds'">
      <div class="menu-icon">🌍</div>
      <div class="menu-text">
        <strong>世界探索</strong>
        <small>已发现地点 {{ unlockedWorlds }} / 30</small>
      </div>
      <span class="arrow">→</span>
    </button>
    <button class="menu-item" @click="panel = 'friends'">
      <div class="menu-icon">♡</div>
      <div class="menu-text"><strong>好友</strong><small>已添加 {{ friends.length }} 位好友</small></div>
      <span class="arrow">→</span>
    </button>
    <button class="menu-item" @click="panel = 'diary'">
      <div class="menu-icon">📖</div>
      <div class="menu-text">
        <strong>人生手记</strong>
        <small>{{ diaryHistory.length }} 篇记录</small>
      </div>
      <span class="arrow">→</span>
    </button>
  </aside>
</template>

<style scoped>
.section-title {
  font-size: 12px; font-weight: 700; color: #237a57;
  margin-bottom: 12px; letter-spacing: 0.05em;
}
.menu-panel { display: flex; flex-direction: column; }
.menu-item {
  display: flex; align-items: center; gap: 12px;
  padding: 16px; background: #fff;
  border: 1px solid #d9dedb; border-radius: 8px;
  margin-bottom: 12px; cursor: pointer;
  transition: all 0.2s; text-align: left;
}
.menu-item:hover { border-color: #237a57; box-shadow: 0 2px 8px rgba(35, 122, 87, 0.1); }
.menu-icon {
  width: 40px; height: 40px; border-radius: 8px;
  background: #e5f3eb;
  display: grid; place-items: center;
  font-size: 20px;
}
.menu-text { flex: 1; }
.menu-text strong { display: block; font-size: 14px; margin-bottom: 2px; }
.menu-text small { color: #69736e; font-size: 11px; }
.arrow { color: #237a57; font-size: 16px; }
</style>
