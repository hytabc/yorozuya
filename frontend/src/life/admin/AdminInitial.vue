<script setup>
// 初始状态区块:新玩家的起始人生数据(天数/属性/标签/初始对话/手记)。
import { computed } from 'vue'
import { adminState, npcById } from './useLifeAdmin'

const content = computed(() => adminState.content)
const initial = computed(() => content.value?.initialState)

const tagsText = computed({
  get: () => (initial.value?.tags || []).join('，'),
  set: value => { initial.value.tags = value.split(/[,，]/).map(t => t.trim()).filter(Boolean) },
})

function greetingOf(npcId) {
  const list = initial.value.conversations[npcId]
  if (!list || !list.length) list && list.push({ from: 'npc', text: '', day: initial.value.day, time: '18:20' })
  return list?.[0]
}
function addDiary() {
  initial.value.diary.unshift({ day: initial.value.day, text: '', mood: '平静' })
}
function removeDiary(index) {
  initial.value.diary.splice(index, 1)
}
</script>

<template>
  <section class="la-section" v-if="initial">
    <h2>初始状态</h2>
    <p>新玩家（无存档）进入游戏时的起始数据。已有存档的玩家不受影响。</p>
    <div class="la-grid2 la-form">
      <label>起始天数（第几天开始）
        <input v-model.number="initial.day" type="number" min="1" />
      </label>
      <label>当前世界显示名
        <input v-model="initial.currentWorld" type="text" />
      </label>
      <label>已发现地点数
        <input v-model.number="initial.unlockedWorlds" type="number" min="0" />
      </label>
      <label>标签（逗号分隔）
        <input v-model="tagsText" type="text" />
      </label>
      <label>心情 mood（0-100）
        <input v-model.number="initial.stats.mood" type="number" min="0" max="100" />
      </label>
      <label>精力 energy（0-100）
        <input v-model.number="initial.stats.energy" type="number" min="0" max="100" />
      </label>
      <label>社交 social（0-100）
        <input v-model.number="initial.stats.social" type="number" min="0" max="100" />
      </label>
      <label>探索 explore（0-100）
        <input v-model.number="initial.stats.explore" type="number" min="0" max="100" />
      </label>
    </div>

    <h3 class="la-sub">各人物的第一句话（未交谈前的初始消息）</h3>
    <table class="la-table">
      <tbody>
        <tr v-for="id in content.npcIds" :key="id">
          <td style="width:100px">{{ npcById(id)?.name || id }}</td>
          <td><input v-model="greetingOf(id).text" type="text" style="width:100%" /></td>
        </tr>
      </tbody>
    </table>

    <h3 class="la-sub">初始手记</h3>
    <div v-for="(entry, i) in initial.diary" :key="i" class="la-diary-row">
      <input v-model.number="entry.day" type="number" min="1" placeholder="天" />
      <input v-model="entry.text" type="text" placeholder="手记内容" />
      <input v-model="entry.mood" type="text" placeholder="心情标签" />
      <button class="la-mini la-danger" @click="removeDiary(i)">删</button>
    </div>
    <button class="la-mini" @click="addDiary">+ 新增手记</button>
  </section>
</template>
