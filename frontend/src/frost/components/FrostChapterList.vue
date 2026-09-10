<script setup>
defineProps({
  chapters: { type: Array, required: true },
})

defineEmits(['enter'])
</script>

<template>
  <div>
    <section v-for="chapter in chapters" :key="chapter.id" class="frost-chapter">
      <div class="frost-chapter-head">
        <span class="frost-chapter-no">CHAPTER {{ chapter.id }}</span>
        <h2>{{ chapter.title }}</h2>
        <p>{{ chapter.theme }}</p>
      </div>
      <p class="frost-chapter-epigraph">{{ chapter.epigraph }}</p>

      <div class="frost-level-grid">
        <button
          v-for="level in chapter.levels"
          :key="level.id"
          type="button"
          class="frost-level-card"
          :class="{ 'is-cleared': level.cleared }"
          :disabled="!level.unlocked"
          @click="$emit('enter', level.id)"
        >
          <span class="frost-level-id">{{ level.id }}</span>
          <h3>{{ level.title }}</h3>
          <div class="frost-level-foot">
            <span v-if="!level.unlocked" class="frost-lock">未解锁</span>
            <span v-else-if="level.cleared">已通关</span>
            <span v-else>可游玩</span>
            <span class="frost-dots" aria-hidden="true">
              <span
                v-for="n in level.totalCount"
                :key="n"
                class="frost-dot"
                :class="{ 'is-seen': n <= level.seenCount }"
              />
            </span>
          </div>
          <div class="frost-level-foot" style="margin-top: 6px">
            <span>已见结局 {{ level.seenCount }} / {{ level.totalCount }}</span>
            <span v-if="level.isTutorial">教学</span>
            <span v-else-if="level.isFinale">终章</span>
          </div>
        </button>
      </div>
    </section>
  </div>
</template>
