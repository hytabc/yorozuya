<script setup>
// 虚拟人生内容管理（/life-admin，阶段 4d）。
// 站长在此组装全站活动内容包:人物/世界与房间/动作/剧本/初始状态,
// 以及包列表(复制/激活/删除)。保存经后端全量校验,活动包即时生效。
import { onMounted } from 'vue'
import {
  adminState, loadPacks, selectPack, savePack, activatePack, duplicatePack, deletePack,
} from '../life/admin/useLifeAdmin'
import AdminNpcs from '../life/admin/AdminNpcs.vue'
import AdminWorlds from '../life/admin/AdminWorlds.vue'
import AdminActions from '../life/admin/AdminActions.vue'
import AdminDialogue from '../life/admin/AdminDialogue.vue'
import AdminInitial from '../life/admin/AdminInitial.vue'

const sections = [
  { id: 'npcs', label: '人物' },
  { id: 'worlds', label: '世界与房间' },
  { id: 'actions', label: '动作' },
  { id: 'dialogue', label: '剧本' },
  { id: 'initial', label: '初始状态' },
]

onMounted(() => loadPacks())
</script>

<template>
  <div class="la-page">
    <header class="la-header">
      <div>
        <h1>虚拟人生 · 内容管理</h1>
        <p>全站共享一个活动内容包；修改活动包并保存后，玩家端与存档校验立即生效。</p>
      </div>
      <router-link to="/life" class="la-back">← 返回游戏</router-link>
    </header>

    <!-- 内容包列表 -->
    <section class="la-packs">
      <div v-for="p in adminState.packs" :key="p.id"
           :class="['la-pack-row', { selected: p.id === adminState.selectedId }]">
        <button class="la-pack-select" @click="selectPack(p.id)">
          <strong>{{ p.name }}</strong>
          <small>{{ p.id }} · v{{ p.version }}<em v-if="p.active" class="la-active-tag">活动中</em></small>
        </button>
        <span class="la-pack-ops">
          <button v-if="!p.active" @click="activatePack(p.id)">激活</button>
          <button @click="duplicatePack(p.id)">复制</button>
          <button v-if="!p.active" class="la-danger" @click="deletePack(p.id)">删除</button>
        </span>
      </div>
      <p v-if="!adminState.packs.length && !adminState.loading" class="la-hint">暂无内容包</p>
    </section>

    <!-- 编辑区 -->
    <template v-if="adminState.content">
      <div class="la-toolbar">
        <label class="la-name-edit">包名称
          <input v-model="adminState.detail.name" @input="adminState.dirty = true" />
        </label>
        <nav class="la-tabs">
          <button v-for="s in sections" :key="s.id"
                  :class="{ active: adminState.section === s.id }"
                  @click="adminState.section = s.id">{{ s.label }}</button>
        </nav>
        <span class="la-save-box">
          <small v-if="adminState.dirty" class="la-dirty">有未保存修改</small>
          <small v-else>已保存 · v{{ adminState.detail.version }}</small>
          <button class="la-save" :disabled="!adminState.dirty || adminState.saving" @click="savePack">
            {{ adminState.saving ? '保存中…' : '保存修改' }}
          </button>
        </span>
      </div>
      <p v-if="adminState.error" class="la-error" role="alert">{{ adminState.error }}</p>

      <AdminNpcs v-if="adminState.section === 'npcs'" />
      <AdminWorlds v-else-if="adminState.section === 'worlds'" />
      <AdminActions v-else-if="adminState.section === 'actions'" />
      <AdminDialogue v-else-if="adminState.section === 'dialogue'" />
      <AdminInitial v-else-if="adminState.section === 'initial'" />
    </template>
    <p v-else-if="adminState.loading" class="la-hint">载入中…</p>
    <p v-if="adminState.error && !adminState.content" class="la-error" role="alert">{{ adminState.error }}</p>

    <transition name="la-fade">
      <div v-if="adminState.toast" class="la-toast" role="status">{{ adminState.toast }}</div>
    </transition>
  </div>
</template>

<style>
/* 管理页共享样式(la- 前缀,非 scoped 以覆盖子组件) */
.la-page { min-height: 100vh; background: #f4f6f4; color: #18201d; padding: 24px clamp(16px, 4vw, 48px) 80px; font-size: 13px; }
.la-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 18px; }
.la-header h1 { margin: 0 0 6px; font-size: 20px; }
.la-header p { margin: 0; color: #69736e; font-size: 12px; }
.la-back { color: #237a57; text-decoration: none; font-size: 13px; white-space: nowrap; padding-top: 4px; }

.la-packs { display: grid; gap: 8px; margin-bottom: 18px; }
.la-pack-row { display: flex; align-items: center; gap: 10px; padding: 10px 12px; background: #fff; border: 1px solid #d9dedb; border-radius: 10px; }
.la-pack-row.selected { border-color: #237a57; box-shadow: 0 0 0 2px rgba(35,122,87,.12); }
.la-pack-select { flex: 1; display: flex; justify-content: space-between; align-items: baseline; gap: 10px; border: 0; background: transparent; cursor: pointer; text-align: left; padding: 0; color: inherit; }
.la-pack-select small { color: #69736e; font-size: 11px; }
.la-active-tag { margin-left: 6px; padding: 1px 7px; border-radius: 999px; background: #e5f3eb; color: #237a57; font-size: 10px; font-style: normal; }
.la-pack-ops { display: flex; gap: 6px; }
.la-pack-ops button { padding: 5px 10px; border: 1px solid #237a57; border-radius: 7px; background: #fff; color: #237a57; font-size: 12px; cursor: pointer; }
.la-pack-ops button:hover { background: #eaf3e9; }
.la-pack-ops .la-danger { border-color: #b84949; color: #b84949; }

.la-toolbar { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; padding: 10px 12px; background: #fff; border: 1px solid #d9dedb; border-radius: 10px; margin-bottom: 14px; }
.la-name-edit { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #69736e; }
.la-name-edit input { padding: 6px 9px; border: 1px solid #d9dedb; border-radius: 7px; font-size: 13px; min-width: 160px; }
.la-tabs { display: flex; gap: 4px; flex: 1; }
.la-tabs button { padding: 7px 14px; border: 0; border-radius: 7px; background: transparent; color: #69736e; font-size: 12px; cursor: pointer; }
.la-tabs button.active { background: #237a57; color: #fff; }
.la-save-box { display: flex; align-items: center; gap: 10px; }
.la-save-box small { color: #69736e; font-size: 11px; }
.la-dirty { color: #b77427 !important; }
.la-save { padding: 8px 18px; border: 0; border-radius: 8px; background: #237a57; color: #fff; font-size: 13px; cursor: pointer; }
.la-save:disabled { background: #dce2dc; color: #788576; cursor: not-allowed; }

.la-error { padding: 10px 14px; border: 1px solid #e3b7b7; border-radius: 8px; background: #fdf2f2; color: #b84949; font-size: 12px; }
.la-hint { color: #788576; font-size: 12px; }

.la-section { background: #fff; border: 1px solid #d9dedb; border-radius: 10px; padding: 16px; }
.la-section h2 { margin: 0 0 4px; font-size: 15px; }
.la-section > p { margin: 0 0 14px; color: #69736e; font-size: 11px; }
.la-table { width: 100%; border-collapse: collapse; }
.la-table th { text-align: left; font-size: 11px; color: #69736e; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #e7ebe5; }
.la-table td { padding: 8px; border-bottom: 1px solid #f0f2f0; vertical-align: middle; }
.la-table input[type=text], .la-table input[type=number], .la-table select, .la-table textarea,
.la-form input[type=text], .la-form input[type=number], .la-form select, .la-form textarea {
  padding: 5px 8px; border: 1px solid #d9dedb; border-radius: 6px; font-size: 12px; font-family: inherit; background: #fffefa; max-width: 100%;
}
.la-table input[type=number] { width: 64px; }
.la-mini { padding: 4px 9px; border: 1px solid #237a57; border-radius: 6px; background: #fff; color: #237a57; font-size: 11px; cursor: pointer; white-space: nowrap; }
.la-mini:hover { background: #eaf3e9; }
.la-mini.la-danger { border-color: #b84949; color: #b84949; }
.la-mini:disabled { border-color: #d9dedb; color: #9aa39d; cursor: not-allowed; background: transparent; }
.la-add-row { display: flex; gap: 8px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
.la-add-row input { padding: 6px 9px; border: 1px solid #d9dedb; border-radius: 7px; font-size: 12px; }
.la-img-cell { display: flex; align-items: center; gap: 8px; }
.la-img-cell img { width: 40px; height: 40px; object-fit: cover; border-radius: 8px; border: 1px solid #d9dedb; background: #f0f2f0; }
.la-img-cell input[type=text] { width: 180px; }
.la-missing { color: #b84949; font-size: 10px; }
.la-sub { margin: 18px 0 8px; font-size: 13px; font-weight: 600; }
.la-node { border: 1px solid #e0e6de; border-radius: 9px; padding: 12px; margin-bottom: 12px; background: #fffefa; }
.la-node-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.la-node-head code { background: #edf3ee; padding: 2px 8px; border-radius: 6px; font-size: 11px; }
.la-node textarea { width: 100%; min-height: 44px; margin-bottom: 8px; }
.la-choice { display: grid; grid-template-columns: 1.2fr 1.4fr 64px repeat(4, 56px) 110px 32px; gap: 6px; align-items: center; margin-bottom: 6px; }
.la-choice-head { font-size: 10px; color: #69736e; }
.la-grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px 20px; }
.la-form label { display: grid; gap: 4px; font-size: 11px; color: #69736e; }
.la-diary-row { display: grid; grid-template-columns: 72px 1fr 100px 32px; gap: 8px; margin-bottom: 8px; align-items: center; }
.la-npc-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
.la-npc-tabs button { padding: 6px 12px; border: 1px solid #d9dedb; border-radius: 999px; background: #fff; font-size: 12px; cursor: pointer; }
.la-npc-tabs button.active { border-color: #237a57; background: #e5f3eb; color: #237a57; }

.la-toast { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); padding: 10px 18px; border-radius: 999px; background: rgba(24,32,29,.92); color: #fff; font-size: 12px; z-index: 50; }
.la-fade-enter-active, .la-fade-leave-active { transition: opacity .25s; }
.la-fade-enter-from, .la-fade-leave-to { opacity: 0; }
.la-page button:focus-visible, .la-page input:focus-visible, .la-page select:focus-visible, .la-page textarea:focus-visible { outline: 2px solid #237a57; outline-offset: 1px; }
</style>
