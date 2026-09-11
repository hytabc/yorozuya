<script setup>
import { onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import AppHeader from './components/AppHeader.vue'
import ToastHost from './components/ToastHost.vue'
import KanbanNiang from './components/KanbanNiang.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

onMounted(() => {
  auth.restore()
})

watch(
  () => [route.meta.lifeOnly, route.meta.lifeManager, auth.isLoggedIn, auth.canPlayLife, auth.canManageRoles],
  () => {
    if (route.meta.lifeOnly && (!auth.isLoggedIn || !auth.canPlayLife)) router.replace('/')
    if (route.meta.lifeManager && (!auth.isLoggedIn || !auth.canManageRoles)) router.replace('/')
  },
)
</script>

<template>
  <div class="app-frame">
    <AppHeader />
    <main>
      <RouterView v-if="(!route.meta.lifeOnly || (auth.isLoggedIn && auth.canPlayLife)) && (!route.meta.lifeManager || (auth.isLoggedIn && auth.canManageRoles))" />
    </main>
    <footer v-if="!route.meta.lifeOnly && !route.meta.lifeManager" class="app-version"><RouterLink to="/versions">V0.2-Beta</RouterLink></footer>
    <ToastHost />
    <KanbanNiang v-if="!route.meta.lifeOnly && !route.meta.lifeManager" />
  </div>
</template>