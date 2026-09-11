import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'
import TaskHall from './views/TaskHall.vue'
import LoginView from './views/LoginView.vue'
import MyTasks from './views/MyTasks.vue'
import ProfileView from './views/ProfileView.vue'
import AdminView from './views/AdminView.vue'
import StaffView from './views/StaffView.vue'
import BoardView from './views/BoardView.vue'
import VrMaps from './views/VrMaps.vue'
import SugarClub from './views/SugarClub.vue'
import FriendHall from './views/FriendHall.vue'
import AnnouncementsView from './views/AnnouncementsView.vue'
import OperationsView from './views/OperationsView.vue'
import VersionsView from './views/VersionsView.vue'
import { api } from './api'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: '/', component: TaskHall, meta: { analyticsKey: 'hall' } },
    { path: '/login', component: LoginView, meta: { guestOnly: true, analyticsKey: 'login' } },
    { path: '/register', component: LoginView, props: { initialMode: 'register' }, meta: { guestOnly: true, analyticsKey: 'login' } },
    { path: '/mine', component: MyTasks, meta: { auth: true, analyticsKey: 'mine' } },
    { path: '/profile', component: ProfileView, meta: { auth: true, analyticsKey: 'profile' } },
    { path: '/staff', component: StaffView, meta: { analyticsKey: 'staff' } },
    { path: '/board', component: BoardView, meta: { analyticsKey: 'board' } },
    { path: '/maps', component: VrMaps, meta: { analyticsKey: 'maps' } },
    { path: '/friends', component: FriendHall, meta: { auth: true, analyticsKey: 'friends' } },
    { path: '/sugar', component: SugarClub, meta: { auth: true, analyticsKey: 'sugar' } },
    { path: '/announcements', component: AnnouncementsView, meta: { analyticsKey: 'announcements' } },
    { path: '/versions', component: VersionsView, meta: { analyticsKey: 'versions' } },
    { path: '/operations', component: OperationsView, meta: { operations: true } },
    { path: '/frost', component: () => import('./views/SugarFrost.vue'), meta: { auth: true, analyticsKey: 'frost' } },
    { path: '/life', component: () => import('./views/VrLife.vue'), meta: { lifeOnly: true } },
    { path: '/life-admin', component: () => import('./views/LifeAdmin.vue'), meta: { lifeManager: true } },
    { path: '/admin', component: AdminView, meta: { moderator: true } },
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