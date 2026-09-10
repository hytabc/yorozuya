<script setup>
import { computed } from 'vue'
import { ENDING_LABEL } from '../engine/constants.js'

const props = defineProps({
  gallery: { type: Array, required: true },
  globalGallery: { type: Array, default: () => [] },
})

const seenCount = computed(() => {
  let count = 0
  for (const chapter of props.gallery) {
    for (const level of chapter.levels) count += level.endings.filter((e) => e.seen).length
  }
  return count
})

const totalCount = computed(() => {
  let count = 0
  for (const chapter of props.gallery) {
    for (const level of chapter.levels) count += level.endings.length
  }
  return count
})
</script>

<template>
  <div>
    <p class="frost-sub">已解锁 {{ seenCount }} / {{ totalCount }} 个设计结局。</p>

    <section v-for="chapter in gallery" :key="chapter.id" class="frost-chapter">
      <div class="frost-chapter-head">
        <span class="frost-chapter-no">CHAPTER {{ chapter.id }}</span>
        <h2>{{ chapter.title }}</h2>
      </div>
      <div v-for="level in chapter.levels" :key="level.id" class="frost-gallery-level">
        <h3>{{ level.id }} · {{ level.title }}</h3>
        <div class="frost-ending-grid">
          <article
            v-for="ending in level.endings"
            :key="ending.id"
            class="frost-ending-card"
            :class="[`is-type-${ending.type}`, { 'is-locked': !ending.seen }]"
          >
            <span class="frost-ending-type">{{ ENDING_LABEL[ending.type] }}</span>
            <h4>{{ ending.seen ? ending.title : '？？？' }}</h4>
            <p>{{ ending.seen ? ending.excerpt : '尚未解锁的结局。' }}</p>
          </article>
        </div>
      </div>
    </section>

    <section class="frost-chapter">
      <div class="frost-chapter-head">
        <span class="frost-chapter-no">FINALE</span>
        <h2>全局结局</h2>
      </div>
      <div class="frost-ending-grid" style="margin-top: 14px">
        <article
          v-for="ending in globalGallery"
          :key="ending.id"
          class="frost-ending-card"
          :class="[`is-type-${ending.type}`, { 'is-locked': !ending.seen }]"
        >
          <span class="frost-ending-type">{{ ENDING_LABEL[ending.type] }} · 全局</span>
          <h4>{{ ending.seen ? ending.title : '？？？' }}</h4>
          <p>{{ ending.seen ? ending.excerpt : '在终章结算后揭示。' }}</p>
        </article>
      </div>
    </section>
  </div>
</template>
