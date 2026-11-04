<script setup>
import { computed, onMounted, ref } from 'vue'
import { Award, Lock } from '@lucide/vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'

const props = defineProps({ userId: { type: Number, default: null } })
const auth = useAuthStore()
const loading = ref(true)
const wall = ref({ unlocked: 0, total: 0, items: [] })

const isSelf = computed(() => !props.userId || props.userId === auth.user?.id)
const groups = computed(() => {
  const map = new Map()
  for (const item of wall.value.items) {
    if (!map.has(item.category)) map.set(item.category, [])
    map.get(item.category).push(item)
  }
  return [...map.entries()].map(([category, items]) => ({ category, items }))
})

async function load() {
  loading.value = true
  try {
    const url = isSelf.value ? '/achievements' : `/users/${props.userId}/achievements`
    wall.value = (await api.get(url)).data
  } catch {
    wall.value = { unlocked: 0, total: 0, items: [] }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="achievement-wall">
    <div v-if="loading" class="skeleton-block" />
    <template v-else>
      <p class="achievement-summary muted">已解锁 {{ wall.unlocked }} / {{ wall.total }}</p>
      <div v-for="group in groups" :key="group.category" class="achievement-group">
        <span class="achievement-category">{{ group.category }}</span>
        <ul>
          <li v-for="item in group.items" :key="item.key" :class="{ locked: !item.unlocked }">
            <component :is="item.unlocked ? Award : Lock" :size="16" />
            <div>
              <strong>{{ item.name }}</strong>
              <small>{{ item.description }}</small>
              <small v-if="isSelf && !item.unlocked" class="achievement-progress">{{ item.progress }} / {{ item.target }}</small>
            </div>
            <span class="achievement-reward">+{{ item.reward }}</span>
          </li>
        </ul>
      </div>
      <p v-if="!wall.items.length" class="muted">还没有解锁任何成就，完成第一份委托试试。</p>
    </template>
  </div>
</template>
