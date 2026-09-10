<script setup>
import { computed } from 'vue'

const props = defineProps({
  list: { type: Array, required: true },
  unlocked: { type: Object, required: true },
  points: { type: Number, default: 0 },
  totalPoints: { type: Number, default: 0 },
})

const unlockedCount = computed(() => props.list.filter((a) => props.unlocked[a.id]).length)
</script>

<template>
  <div>
    <p class="frost-sub">已解锁 {{ unlockedCount }} / {{ list.length }} 项，累计 {{ points }} / {{ totalPoints }} 点。</p>
    <div class="frost-achievement-list">
      <article
        v-for="achievement in list"
        :key="achievement.id"
        class="frost-achievement"
        :class="{ 'is-locked': !unlocked[achievement.id] }"
      >
        <h4>
          <span>{{ unlocked[achievement.id] ? achievement.title : '？？？' }}</span>
          <span>{{ achievement.points }} pt</span>
        </h4>
        <p>{{ unlocked[achievement.id] ? achievement.desc : '尚未解锁。' }}</p>
      </article>
    </div>
  </div>
</template>
