import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { api } from './api'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    // 全部页面按需动态导入：首屏只加载当前路由的 JS，减小首包体积。
    { path: '/', component: () => import('./views/TaskHall.vue'), meta: { analyticsKey: 'hall' } },
    { path: '/login', component: () => import('./views/LoginView.vue'), meta: { guestOnly: true, analyticsKey: 'login' } },
    { path: '/register', component: () => import('./views/LoginView.vue'), props: { initialMode: 'register' }, meta: { guestOnly: true, analyticsKey: 'login' } },
    // 邮箱相关：验证/重置链接可能从任意浏览器打开，因此都不要求登录态。
    { path: '/verify-email', component: () => import('./views/VerifyEmailView.vue') },
    { path: '/forgot-password', component: () => import('./views/ForgotPasswordView.vue') },
    { path: '/reset-password', component: () => import('./views/ResetPasswordView.vue') },
    { path: '/mine', component: () => import('./views/MyTasks.vue'), meta: { auth: true, analyticsKey: 'mine' } },
    { path: '/profile', component: () => import('./views/ProfileView.vue'), meta: { auth: true, analyticsKey: 'profile' } },
    { path: '/staff', component: () => import('./views/StaffView.vue'), meta: { analyticsKey: 'staff' } },
    { path: '/board', component: () => import('./views/BoardView.vue'), meta: { analyticsKey: 'board' } },
    { path: '/maps', component: () => import('./views/VrMaps.vue'), meta: { analyticsKey: 'maps' } },
    { path: '/stories', component: () => import('./views/StoryHall.vue'), meta: { auth: true, analyticsKey: 'stories' } },
    { path: '/friends', component: () => import('./views/FriendHall.vue'), meta: { auth: true, analyticsKey: 'friends' } },
    { path: '/sugar', component: () => import('./views/SugarClub.vue'), meta: { auth: true, analyticsKey: 'sugar' } },
    { path: '/announcements', component: () => import('./views/AnnouncementsView.vue'), meta: { analyticsKey: 'announcements' } },
    { path: '/versions', component: () => import('./views/VersionsView.vue'), meta: { analyticsKey: 'versions' } },
    { path: '/operations', component: () => import('./views/OperationsView.vue'), meta: { operations: true } },
    { path: '/frost', component: () => import('./views/SugarFrost.vue'), meta: { auth: true, analyticsKey: 'frost' } },
    { path: '/life', component: () => import('./views/VrLife.vue'), meta: { lifeOnly: true } },
    { path: '/life-admin', component: () => import('./views/LifeAdmin.vue'), meta: { lifeManager: true } },
    { path: '/admin', component: () => import('./views/AdminView.vue'), meta: { moderator: true } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

// 涉及权限的页面一律先向服务端核实身份：localStorage 中的 wsw_user 可被随意篡改，
// 绝不能用它作为管理员/运营权限的判定依据。
const SERVER_VERIFIED_META = ['lifeOnly', 'lifeManager', 'roleManager', 'moderator', 'operations']

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  // 凭证是加密存储的，先解密水合（幂等、不联网），之后 isLoggedIn 判定才准确。
  await auth.hydrate()
  if (SERVER_VERIFIED_META.some((key) => to.meta[key])) {
    if (!auth.token) return '/'
    await auth.restore()
    if (!auth.isLoggedIn) return '/'
  }
  if (to.meta.auth && !auth.isLoggedIn) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.meta.lifeOnly && !auth.canPlayLife) return '/'
  if (to.meta.lifeManager && !auth.canManageRoles) return '/'
  if (to.meta.roleManager && !auth.canManageRoles) return '/'
  if (to.meta.moderator && !auth.canModerate) return '/'
  if (to.meta.operations && !auth.canOperate) return '/'
  if (to.meta.guestOnly && auth.isLoggedIn) return '/'
})

function analyticsSessionId() {
  const key = 'wsw_analytics_session'
  let value = localStorage.getItem(key)
  if (!value) {
    value = globalThis.crypto?.randomUUID?.().replaceAll('-', '')
      || `${Date.now()}_${Math.random().toString(36).slice(2)}`
    localStorage.setItem(key, value)
  }
  return value
}

router.afterEach((to) => {
  if (!to.meta.analyticsKey) return
  api.post('/analytics/page-view', {
    page_key: to.meta.analyticsKey,
    session_id: analyticsSessionId(),
  }).catch(() => {})
})

export default router