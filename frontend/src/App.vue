<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { isLifeDesktop } from './lifeAccess'
import { useAuthStore } from './stores/auth'
import AppHeader from './components/AppHeader.vue'
import ToastHost from './components/ToastHost.vue'
import KanbanNiang from './components/KanbanNiang.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const lifeDesktop = ref(isLifeDesktop())
const checkViewport = () => { lifeDesktop.value = isLifeDesktop() }
onMounted(() => {
  auth.restore()
  window.addEventListener('resize', checkViewport)
})
onBeforeUnmount(() => window.removeEventListener('resize', checkViewport))
watch(() => [route.meta.lifeOnly, route.meta.lifeManager, auth.isLoggedIn, auth.canPlayLife, auth.canManageRoles, lifeDesktop.value], () => {
  if (route.meta.lifeOnly && (!auth.isLoggedIn || !auth.canPlayLife || !lifeDesktop.value)) router.replace('/')
  if (route.meta.lifeManager && (!auth.isLoggedIn || !auth.canManageRoles || !lifeDesktop.value)) router.replace('/')
})
</script>

<template>
  <div class="app-frame">
    <AppHeader />
    <main>
      <RouterView v-if="(!route.meta.lifeOnly || (auth.isLoggedIn && auth.canPlayLife && lifeDesktop)) && (!route.meta.lifeManager || (auth.isLoggedIn && auth.canManageRoles && lifeDesktop))" />
    </main>
    <footer v-if="!route.meta.lifeOnly && !route.meta.lifeManager" class="app-version"><RouterLink to="/versions">V0.2-Beta</RouterLink></footer>
    <ToastHost />
    <KanbanNiang v-if="!route.meta.lifeOnly && !route.meta.lifeManager" />
  </div>
</template>

