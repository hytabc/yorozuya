<script setup>
// 右侧功能入口：世界探索 / 好友 / 人生手记。样式从 LifeSimulator.vue 迁出，行为不变。
const props = defineProps({ game: { type: Object, required: true } })
const { panel, unlockedWorlds, friends, diaryHistory } = props.game
</script>

<template>
  <aside class="menu-panel">
    <div class="section-title">02 功能入口</div>
    <button data-life-guide="worlds" class="menu-item world" @click="panel = 'worlds'">
      <div class="menu-icon">🌍</div>
      <div class="menu-text">
        <strong>世界探索</strong>
        <small>已发现地点 {{ unlockedWorlds }} / 30</small>
      </div>
      <span class="arrow">→</span>
    </button>
    <button class="menu-item friends" @click="panel = 'friends'">
      <div class="menu-icon">♡</div>
      <div class="menu-text"><strong>好友</strong><small>已添加 {{ friends.length }} 位好友</small></div>
      <span class="arrow">→</span>
    </button>
    <button class="menu-item diary" @click="panel = 'diary'">
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
  width: fit-content;
  padding: 4px 12px; border-radius: 999px;
  background: #e5f3eb;
  font-size: 12px; font-weight: 700; color: #237a57;
  margin-bottom: 12px; letter-spacing: 0.05em;
}
.menu-panel { display: flex; flex-direction: column; }
.menu-item {
  display: flex; align-items: center; gap: 12px;
  padding: 16px; background: #fff;
  border: 1px solid #e6eae6; border-radius: 14px;
  box-shadow: 0 3px 10px rgba(25, 38, 32, .04);
  margin-bottom: 12px; cursor: pointer;
  transition: all 0.2s; text-align: left;
}
.menu-item:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(25, 38, 32, .09); }
.menu-icon {
  width: 40px; height: 40px; border-radius: 12px;
  display: grid; place-items: center;
  font-size: 20px;
}
/* 三个模块各自的柔和主题色:探索=绿 / 好友=粉 / 手记=暖黄 */
.menu-item.world .menu-icon { background: #e5f3eb; }
.menu-item.friends .menu-icon { background: #fdeef1; }
.menu-item.diary .menu-icon { background: #fdf4e0; }
.menu-item.world:hover { border-color: #9ccbb2; }
.menu-item.friends:hover { border-color: #ecc3cd; }
.menu-item.diary:hover { border-color: #ecd9a8; }
.menu-text { flex: 1; }
.menu-text strong { display: block; font-size: 14px; margin-bottom: 2px; }
.menu-text small { color: #69736e; font-size: 11px; }
.arrow { color: #237a57; font-size: 16px; }
.menu-item.friends .arrow { color: #c26a7d; }
.menu-item.diary .arrow { color: #b98e2f; }
</style>
