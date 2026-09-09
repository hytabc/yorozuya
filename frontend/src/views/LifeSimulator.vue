<script setup>
// 虚拟人生外壳：顶栏/存档状态/三栏布局/底部操作/抽屉外壳/引导/Toast。
// 游戏状态与业务逻辑在 life/useLifeGame.js；内容数据在 life/content/；展示组件在 life/components/。
import { ref } from 'vue'
import LifeTutorial from '../components/LifeTutorial.vue'
import { useAuthStore } from '../stores/auth'
import { useLifeGame } from '../life/useLifeGame'
import LifeCharPanel from '../life/components/LifeCharPanel.vue'
import LifeScene from '../life/components/LifeScene.vue'
import LifeMenuPanel from '../life/components/LifeMenuPanel.vue'
import LifeHistoryDrawer from '../life/components/LifeHistoryDrawer.vue'
import LifeFeatureDrawer from '../life/components/LifeFeatureDrawer.vue'
import LifeEndingModal from '../life/components/LifeEndingModal.vue'

const endingOpen = ref(false)

const tutorial = ref(null)
const auth = useAuthStore()
const game = useLifeGame()
const {
  day, stats, npcs, toast, showHistory, panel,
  saveReady, saveBusy, saveDirty, saveError, saveConflict, savedAt,
  save, nextDay, resetToday, restartJourney, reloadConfirmed, prepareTutorial, closeTutorial,
} = game

function resetTodayConfirmed() {
  if (!saveReady.value || saveConflict.value) return
  if (window.confirm('重置今天？今天的对话完成度、房间事件与动作奖励进度都会清零（属性与好感不回滚）。')) resetToday()
}

function restartConfirmed() {
  if (!saveReady.value || saveConflict.value) return
  if (window.confirm('重新开始？当前七天的属性、好感、对话与手记都会回到初始状态。')) {
    endingOpen.value = false
    restartJourney()
  }
}
</script>

<template>
  <div class="life-page">
    <!-- 顶部信息栏 -->
    <header class="life-header">
      <div class="brand">
        <span class="brand-mark">万</span>
        <div class="brand-text">
          <strong>万事屋 · 虚拟人生</strong>
          <small>在另一个世界，慢慢成为自己。</small>
        </div>
      </div>
      <div class="status-pills">
        <span>📅 第 {{ day }} 天</span>
        <span>⏰ 18:20</span>
        <span>♥ 心情 {{ stats.mood }}</span>
        <span>⚡ 精力 {{ stats.energy }}</span>
      </div>
      <div class="header-actions">
        <button v-if="day < 7" :disabled="!saveReady || saveConflict" @click="nextDay">下一天 ▶</button>
        <button v-else :disabled="!saveReady || saveConflict" @click="endingOpen = true">🌅 查看结局</button>
        <button :disabled="!saveReady || saveConflict" @click="tutorial?.start()">新手指引</button>
        <button v-if="auth.canManageRoles" title="内容管理" @click="$router.push('/life-admin')">内容管理</button>
        <button class="icon-btn" title="设置">⚙</button>
        <button class="icon-btn" title="返回" @click="$router.back()">↩</button>
      </div>
    </header>

    <div class="save-status" role="status" aria-live="polite">
      <span v-if="saveError">{{ saveError }}</span>
      <span v-else>{{ !saveReady ? '正在读取个人存档…' : saveBusy ? '正在保存…' : saveDirty ? '有修改尚未保存' : savedAt ? '个人存档已同步' : '尚无存档，请开始游戏或手动保存' }}</span>
      <button v-if="saveError && saveReady && !saveConflict" @click="save" :disabled="saveBusy">重试保存</button>
      <button v-if="saveError" @click="reloadConfirmed" :disabled="saveBusy">重新载入</button>
    </div>
    <!-- 主内容三栏 -->
    <div class="life-layout" :inert="!saveReady || saveConflict">
      <!-- 左侧角色 -->
      <LifeCharPanel :game="game" />

      <!-- 中央场景(大空间,UI 浮在上面) -->
      <LifeScene :game="game" />

      <!-- 右侧功能入口 -->
      <LifeMenuPanel :game="game" />
    </div>

    <!-- 底部操作 -->
    <footer class="life-footer">
      <button @click="save" :disabled="!saveReady || saveConflict || saveBusy">存档</button>
      <button @click="resetTodayConfirmed" :disabled="!saveReady || saveConflict"
              title="清空今天的对话、事件与动作进度（测试用）">↺ 重置当天</button>
      <button @click="day >= 7 ? endingOpen = true : nextDay()" :disabled="!saveReady || saveConflict">下一天</button>
      <small>对话将写入今天的手记</small>
    </footer>

    <!-- 对话历史抽屉 -->
    <transition name="slide">
      <div v-if="showHistory" class="drawer" @click.self="showHistory = false">
        <div class="drawer-content history-drawer">
          <button class="drawer-close" @click="showHistory = false">✕</button>
          <LifeHistoryDrawer :game="game" />
        </div>
      </div>
    </transition>

    <!-- 功能抽屉 -->
    <transition name="slide">
      <div v-if="panel" class="drawer" @click.self="panel = ''">
        <div class="drawer-content">
          <button class="drawer-close" @click="panel = ''">✕</button>
          <LifeFeatureDrawer :game="game" />
        </div>
      </div>
    </transition>

    <LifeTutorial ref="tutorial" :ready="saveReady && !saveConflict" :user-id="auth.user?.id" @prepare="prepareTutorial" @close="closeTutorial" />
    <LifeEndingModal v-if="endingOpen" :stats="stats" :npcs="npcs" @close="endingOpen = false" @restart="restartConfirmed" />
    <!-- Toast 提示 -->
    <transition name="fade">
      <div v-if="toast" class="toast">{{ toast }}</div>
    </transition>
  </div>
</template>

<style scoped>
.life-page {
  min-height: calc(100vh - 72px);
  background: #f5f6f4;
  color: #18201d;
  padding: 24px 32px 40px;
  font-family: Inter, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ========== 顶部信息栏 ========== */
.life-header {
  display: flex; align-items: center; gap: 24px;
  margin-bottom: 28px; padding-bottom: 20px;
  border-bottom: 1px solid #d9dedb;
}
.brand { display: flex; align-items: center; gap: 12px; }
.brand-mark {
  display: grid; place-items: center;
  width: 44px; height: 44px;
  background: #18201d; color: white;
  font-family: Georgia, serif; font-size: 22px; font-weight: 700;
  transform: rotate(-3deg);
}
.brand-text strong { display: block; font-size: 18px; }
.brand-text small { display: block; margin-top: 2px; color: #69736e; font-size: 11px; }
.status-pills { display: flex; gap: 16px; margin-left: auto; }
.status-pills span {
  padding: 6px 12px; border-radius: 999px;
  background: #fff; border: 1px solid #d9dedb;
  font-size: 12px; color: #69736e;
}
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.header-actions button { white-space: nowrap; }
.icon-btn {
  width: 36px; height: 36px;
  border: 1px solid #d9dedb; border-radius: 6px;
  background: #fff; color: #69736e;
  cursor: pointer;
}

/* ========== 三栏布局 ========== */
.life-layout {
  display: grid;
  grid-template-columns: 280px 1fr 280px;
  gap: 24px;
  margin-bottom: 28px;
}

/* ========== 底部操作 ========== */
.life-footer {
  display: flex; align-items: center; gap: 24px;
  padding-top: 20px;
  border-top: 1px solid #d9dedb;
}
.life-footer button {
  padding: 8px 16px;
  background: transparent; border: 1px solid #d9dedb;
  border-radius: 6px; color: #69736e;
  font-size: 12px; cursor: pointer;
  transition: all 0.2s;
}
.life-footer button:hover { border-color: #237a57; color: #237a57; }
.life-footer small {
  margin-left: auto;
  color: #9a9fa0; font-size: 11px;
}

/* ========== 抽屉 ========== */
.drawer {
  position: fixed; inset: 0;
  background: rgba(24, 32, 29, 0.3);
  z-index: 1000;
  display: flex; justify-content: flex-end;
}
.drawer-content {
  position: relative;
  width: 400px; height: 100%;
  background: #fff;
  border-left: 1px solid #d9dedb;
  padding: 32px 24px;
  overflow-y: auto;
}
.drawer-close {
  position: absolute; top: 16px; right: 16px;
  width: 32px; height: 32px; border: 0;
  border-radius: 50%; background: #f0f2f0;
  color: #69736e; cursor: pointer;
}

/* 对话历史抽屉 */
.history-drawer { width: 450px; }

.slide-enter-active, .slide-leave-active { transition: opacity 0.3s; }
.slide-enter-from, .slide-leave-to { opacity: 0; }
.slide-enter-active .drawer-content { transition: transform 0.3s; }
.slide-enter-from .drawer-content { transform: translateX(100%); }

/* ========== Toast ========== */
.toast {
  position: fixed; top: 90px; left: 50%;
  transform: translateX(-50%);
  padding: 10px 20px;
  background: #18201d; color: #fff;
  border-radius: 999px; font-size: 13px;
  z-index: 2000;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* ========== 响应式 ========== */
@media (max-width: 1200px) {
  .life-layout { grid-template-columns: 260px 1fr 260px; gap: 16px; }
}
@media (max-width: 900px) {
  .life-page { padding: 16px 20px 32px; }
  .life-header { flex-wrap: wrap; gap: 12px; }
  .status-pills { order: 3; width: 100%; }
  .life-layout { grid-template-columns: 1fr; gap: 20px; }
  .drawer-content { width: min(340px, 90vw); }
  .history-drawer { width: min(400px, 90vw); }
}
</style>
