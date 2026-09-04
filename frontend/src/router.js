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

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: '/', component: TaskHall },
    { path: '/login', component: LoginView, meta: { guestOnly: true } },
    { path: '/register', component: LoginView, props: { initialMode: 'register' }, meta: { guestOnly: true } },
    { path: '/mine', component: MyTasks, meta: { auth: true } },
    { path: '/profile', component: ProfileView, meta: { auth: true } },
    { path: '/staff', component: StaffView },
    { path: '/board', component: BoardView },
    { path: '/maps', component: VrMaps },
    { path: '/sugar', component: SugarClub, meta: { auth: true } },
    { path: '/admin', component: AdminView, meta: { roleManager: true } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.auth && !auth.isLoggedIn) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.meta.roleManager && !auth.canManageRoles) return '/'
  if (to.meta.guestOnly && auth.isLoggedIn) return '/'
})

export default router
