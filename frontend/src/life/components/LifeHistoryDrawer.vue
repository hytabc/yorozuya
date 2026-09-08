<script setup>
// 对话历史抽屉内容：NPC 分页 + 气泡记录。外壳(.drawer/.drawer-content)留在 LifeSimulator.vue。
const props = defineProps({ game: { type: Object, required: true } })
const { npcs, historyNpcId, historyConversation } = props.game
</script>

<template>
  <h2>对话历史</h2>
  <div class="history-npc-tabs">
    <button v-for="npc in npcs" :key="npc.id"
            :class="['history-tab', { active: npc.id === historyNpcId }]"
            @click="historyNpcId = npc.id">
      {{ npc.name }}
    </button>
  </div>
  <div class="history-messages">
    <div v-for="(msg, i) in historyConversation" :key="i"
         :class="['history-bubble', msg.from]">
      <div class="bubble-text">{{ msg.text }}</div>
      <div class="bubble-time">第 {{ msg.day }} 天 · {{ msg.time }}</div>
    </div>
  </div>
</template>

<style scoped>
.history-drawer h2 { margin-bottom: 20px; font-size: 18px; }
.history-npc-tabs {
  display: flex; gap: 8px;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f2f0;
}
.history-tab {
  padding: 8px 16px;
  background: #fff; border: 1px solid #d9dedb;
  border-radius: 6px; color: #69736e;
  font-size: 13px; cursor: pointer;
  transition: all 0.2s;
}
.history-tab:hover { border-color: #237a57; }
.history-tab.active {
  background: #237a57; color: #fff;
  border-color: #237a57;
}
.history-messages {
  display: flex; flex-direction: column; gap: 12px;
}
.history-bubble {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px; line-height: 1.6;
}
.history-bubble.npc {
  background: #f5f6f4;
  border: 1px solid #e5e8e5;
  align-self: flex-start;
}
.history-bubble.player {
  background: #237a57; color: #fff;
  align-self: flex-end;
}
.bubble-text {
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 14px; line-height: 1.6;
  word-break: break-word;
  box-shadow: 0 2px 8px rgba(25, 38, 32, 0.08);
}
.history-bubble .bubble-time {
  margin-top: 4px;
  font-size: 9px; color: #9a9fa0;
}
</style>
