<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Moon, Palette, Sun } from '@lucide/vue'
import { api } from './api'
import { useAuthStore } from './stores/auth'
import { cycleTheme, mode, setModeSource, theme } from './composables/theme'
import AppHeader from './components/AppHeader.vue'
import ToastHost from './components/ToastHost.vue'
import KanbanNiang from './components/KanbanNiang.vue'
import EmailVerificationGate from './components/EmailVerificationGate.vue'

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

// 两个悬浮按钮与个人设置里的「外观」是同一份偏好：登录后一并落库，
// 换设备/清缓存后依然生效；未登录就只改本地（接口需要登录）。
async function persistTheme(partial) {
  if (!auth.isLoggedIn) return
  try {
    const { data } = await api.patch('/users/me/theme', partial)
    await auth.patchUser({ theme_mode: data.theme_mode, theme_style: data.theme_style })
  } catch { /* 保存失败不影响本次切换，仅下次登录回落到服务端的旧值 */ }
}

function switchTheme() {
  cycleTheme()
  persistTheme({ theme_style: theme.value })
}

function switchMode() {
  const next = mode.value === 'night' ? 'day' : 'night'
  setModeSource(next)
  persistTheme({ theme_mode: next })
}
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
    <!-- 风格切换:右上角悬浮,与左上角看板娘对称;全屏游戏页不显示 -->
    <button
      v-if="!route.meta.lifeOnly && !route.meta.lifeManager"
      class="theme-toggle"
      type="button"
      :aria-pressed="theme === 'pixel'"
      :title="`切换页面风格(当前:${theme === 'pixel' ? '像素风' : '经典风'})`"
      @click="switchTheme"
    >
      <Palette :size="16" />
      <span>{{ theme === 'pixel' ? '经典风' : '像素风' }}</span>
    </button>
    <!-- 明暗切换:与风格切换同列;「根据时间切换」等档位在个人设置的「外观」里选 -->
    <button
      v-if="!route.meta.lifeOnly && !route.meta.lifeManager"
      class="theme-toggle mode-toggle"
      type="button"
      :aria-pressed="mode === 'night'"
      :title="`切换深色模式(当前:${mode === 'night' ? '夜间' : '日间'})`"
      @click="switchMode"
    >
      <component :is="mode === 'night' ? Sun : Moon" :size="16" />
      <span>{{ mode === 'night' ? '日间' : '夜间' }}</span>
    </button>
    <!-- 未完成邮箱验证时的强制绑定浮层：/life、/life-admin 这类全屏页也要挡，故挂在根部 -->
    <EmailVerificationGate />
    <!-- 看板娘走付费大模型，后端要求登录；未登录时直接不渲染入口。 -->
    <KanbanNiang v-if="auth.isLoggedIn && !route.meta.lifeOnly && !route.meta.lifeManager" />
  </div>
</template>