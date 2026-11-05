<script setup>
import { onMounted, ref } from 'vue'
import { History } from '@lucide/vue'
import { loadVersionNotes } from '../versionNotes'

// 与页脚版本号、版本更新弹窗共用 public/versions/versions.json。
const entries = ref([])
const loading = ref(true)

onMounted(async () => {
  const notes = await loadVersionNotes()
  entries.value = notes?.entries || []
  loading.value = false
})
</script>

<template>
  <div class="page inner-page versions-page">
    <div class="page-title">
      <div><span class="eyebrow"><History :size="15" /> RELEASE NOTES</span><h1>版本更新</h1><p>万事屋委托站的版本记录与功能变更</p></div>
    </div>

    <div v-if="loading" class="skeleton-list" aria-hidden="true">
      <div v-for="n in 3" :key="n" class="skeleton skeleton-block" />
    </div>

    <article v-for="entry in entries" :key="entry.version" class="version-entry">
      <h2>{{ entry.version }}<template v-if="entry.label"> {{ entry.label }}</template></h2>
      <time :datetime="entry.date">{{ entry.date }}<template v-if="entry.tagline"> · {{ entry.tagline }}</template></time>

      <template v-if="entry.sections?.length">
        <template v-for="section in entry.sections" :key="section.title">
          <h3>{{ section.title }}</h3>
          <ul>
            <li v-for="item in section.items" :key="item">{{ item }}</li>
          </ul>
        </template>
      </template>
      <ul v-else>
        <li v-for="item in entry.summary" :key="item">{{ item }}</li>
      </ul>
    </article>
  </div>
</template>
