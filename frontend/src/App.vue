<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { useAuthStore } from './stores/auth'
import AppHeader from './components/AppHeader.vue'
import ToastHost from './components/ToastHost.vue'
import KanbanNiang from './components/KanbanNiang.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
// 备案号等私有信息保存在服务端 .env，前端运行时获取，不写进源码/构建产物。
const siteConfig = ref({ icp: '', icp_url: '' })

onMounted(async () => {
  auth.restore()
  try {
    siteConfig.value = (await api.get('/site-config')).data
  } catch { /* 未配置备案号或接口不可用时，页脚不展示该行 */ }
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
    <footer v-if="!route.meta.lifeOnly && !route.meta.lifeManager" class="app-version">
      <RouterLink to="/versions">V0.2-Beta</RouterLink>
      <template v-if="siteConfig.icp">
        <span class="footer-sep" aria-hidden="true">·</span>
        <a :href="siteConfig.icp_url" target="_blank" rel="noopener noreferrer">{{ siteConfig.icp }}</a>
      </template>
    </footer>
    <ToastHost />
    <KanbanNiang v-if="!route.meta.lifeOnly && !route.meta.lifeManager" />
  </div>
</template>