<script setup>
import { onMounted } from 'vue'
import { useAuthStore } from './stores/auth'
import AppHeader from './components/AppHeader.vue'
import ToastHost from './components/ToastHost.vue'
import KanbanNiang from './components/KanbanNiang.vue'

const auth = useAuthStore()
onMounted(auth.restore)
</script>

<template>
  <div class="app-frame">
    <AppHeader />
    <main>
      <RouterView />
    </main>
    <ToastHost />
    <KanbanNiang />
  </div>
</template>

