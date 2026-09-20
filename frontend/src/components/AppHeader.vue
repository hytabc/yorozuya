<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BarChart3, BookOpen, BriefcaseBusiness, ChevronDown, Gamepad2, HeartHandshake, History, LogOut, Map, Megaphone, Menu, MessagesSquare, ShieldCheck, Snowflake, Sparkles, Store, UserPlus, UserRound, Users, X } from '@lucide/vue'
import { useAuthStore } from '../stores/auth'
import UserAvatar from './UserAvatar.vue'
import UserTitleTag from './UserTitleTag.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const open = ref(false)
const openMenu = ref(null) // 桌面下拉：'games' | 'social' | 'more'
const mobileGroup = ref(null) // 移动端折叠分组：'games' | 'social'

const MENU_PATHS = {
  games: ['/frost', '/life'],
  social: ['/board', '/stories', '/friends', '/sugar'],
  more: ['/announcements', '/versions', '/admin', '/operations'],
}

function menuActive(key) {
  return MENU_PATHS[key].includes(route.path)
}

function toggleMenu(key) {
  openMenu.value = openMenu.value === key ? null : key
}

function closeMenus() {
  openMenu.value = null
}

function logout() {
  auth.logout()
  open.value = false
  router.push('/')
}

// 切换页面时收起下拉与移动端面板。
watch(() => route.fullPath, () => {
  open.value = false
  openMenu.value = null
  mobileGroup.value = null
})

onMounted(() => document.addEventListener('click', closeMenus))
onBeforeUnmount(() => document.removeEventListener('click', closeMenus))
</script>

<template>
  <header class="topbar">
    <div class="topbar-inner">
      <RouterLink to="/" class="brand" aria-label="万事屋委托站首页">
        <span class="brand-mark">万</span>
        <span><strong>万事屋</strong><small>YOROZUYA BOARD</small></span>
      </RouterLink>

      <nav class="desktop-nav" aria-label="主导航">
        <RouterLink to="/">委托大厅</RouterLink>

        <div v-if="auth.isLoggedIn" class="nav-more-wrap">
          <button
            class="nav-more"
            :class="{ active: menuActive('games') }"
            type="button"
            aria-haspopup="menu"
            :aria-expanded="openMenu === 'games'"
            @click.stop="toggleMenu('games')"
          >游戏<ChevronDown :size="14" /></button>
          <div v-if="openMenu === 'games'" class="nav-more-menu" role="menu">
            <RouterLink role="menuitem" to="/frost" @click="closeMenus">糖霜世界</RouterLink>
            <RouterLink v-if="auth.ready && auth.canPlayLife" role="menuitem" to="/life" @click="closeMenus">虚拟人生</RouterLink>
          </div>
        </div>

        <div class="nav-more-wrap">
          <button
            class="nav-more"
            :class="{ active: menuActive('social') }"
            type="button"
            aria-haspopup="menu"
            :aria-expanded="openMenu === 'social'"
            @click.stop="toggleMenu('social')"
          >社交<ChevronDown :size="14" /></button>
          <div v-if="openMenu === 'social'" class="nav-more-menu" role="menu">
            <RouterLink role="menuitem" to="/board" @click="closeMenus">留言板</RouterLink>
            <RouterLink v-if="auth.isLoggedIn" role="menuitem" to="/stories" @click="closeMenus">故事会</RouterLink>
            <RouterLink role="menuitem" to="/friends" @click="closeMenus">交友厅</RouterLink>
            <RouterLink role="menuitem" to="/sugar" @click="closeMenus">砂糖社</RouterLink>
          </div>
        </div>

        <RouterLink to="/maps">地图推荐</RouterLink>
        <RouterLink v-if="auth.isLoggedIn" to="/mine">我的委托</RouterLink>
        <RouterLink to="/staff">成员名录</RouterLink>
        <div class="nav-more-wrap">
          <button
            class="nav-more"
            :class="{ active: menuActive('more') }"
            type="button"
            aria-haspopup="menu"
            :aria-expanded="openMenu === 'more'"
            @click.stop="toggleMenu('more')"
          >更多<ChevronDown :size="14" /></button>
          <div v-if="openMenu === 'more'" class="nav-more-menu" role="menu">
            <RouterLink role="menuitem" to="/announcements" @click="closeMenus">公告中心</RouterLink>
            <RouterLink role="menuitem" to="/versions" @click="closeMenus">版本更新</RouterLink>
            <RouterLink v-if="auth.canModerate" role="menuitem" to="/admin" @click="closeMenus">{{ auth.isAdmin ? '监管台' : auth.isDisciplinarian ? '审核台' : '权限管理' }}</RouterLink>
            <RouterLink v-if="auth.canOperate" role="menuitem" to="/operations" @click="closeMenus">运营台</RouterLink>
          </div>
        </div>
      </nav>

      <div class="header-actions">
        <template v-if="auth.isLoggedIn">
          <RouterLink to="/profile" class="user-chip">
            <UserAvatar :user="auth.user" :size="30" />
            <span>{{ auth.user?.nickname }}</span><UserTitleTag :title="auth.user?.title" />
          </RouterLink>
          <button class="icon-button desktop-only" title="退出登录" aria-label="退出登录" @click="logout">
            <LogOut :size="19" />
          </button>
        </template>
        <template v-else>
          <RouterLink class="text-link desktop-only" to="/login">登录</RouterLink>
          <RouterLink class="button small desktop-only" to="/register">加入万事屋</RouterLink>
        </template>
        <button class="icon-button mobile-menu" :aria-expanded="open" aria-label="打开菜单" @click="open = !open">
          <X v-if="open" :size="21" /><Menu v-else :size="21" />
        </button>
      </div>
    </div>
    <div v-if="open" class="mobile-panel">
      <RouterLink to="/" @click="open = false"><BriefcaseBusiness :size="18" />委托大厅</RouterLink>
      <button
        class="mobile-group-toggle"
        type="button"
        :aria-expanded="mobileGroup === 'games'"
        @click.stop="mobileGroup = mobileGroup === 'games' ? null : 'games'"
      >
        <Gamepad2 :size="18" />游戏<ChevronDown :size="16" class="mobile-group-caret" :class="{ open: mobileGroup === 'games' }" />
      </button>
      <div v-if="mobileGroup === 'games'" class="mobile-group">
        <RouterLink v-if="auth.isLoggedIn" to="/frost" @click="open = false"><Snowflake :size="18" />糖霜世界</RouterLink>
        <RouterLink v-if="auth.ready && auth.canPlayLife" to="/life" @click="open = false"><Sparkles :size="18" />虚拟人生</RouterLink>
      </div>
      <button
        class="mobile-group-toggle"
        type="button"
        :aria-expanded="mobileGroup === 'social'"
        @click.stop="mobileGroup = mobileGroup === 'social' ? null : 'social'"
      >
        <Users :size="18" />社交<ChevronDown :size="16" class="mobile-group-caret" :class="{ open: mobileGroup === 'social' }" />
      </button>
      <div v-if="mobileGroup === 'social'" class="mobile-group">
        <RouterLink to="/board" @click="open = false"><MessagesSquare :size="18" />留言板</RouterLink>
        <RouterLink v-if="auth.isLoggedIn" to="/stories" @click="open = false"><BookOpen :size="18" />故事会</RouterLink>
        <RouterLink to="/friends" @click="open = false"><UserPlus :size="18" />交友厅</RouterLink>
        <RouterLink to="/sugar" @click="open = false"><HeartHandshake :size="18" />砂糖社</RouterLink>
      </div>
      <RouterLink to="/maps" @click="open = false"><Map :size="18" />地图推荐</RouterLink>
      <RouterLink v-if="auth.isLoggedIn" to="/mine" @click="open = false"><BriefcaseBusiness :size="18" />我的委托</RouterLink>
      <RouterLink to="/staff" @click="open = false"><Store :size="18" />成员名录</RouterLink>
      <RouterLink to="/announcements" @click="open = false"><Megaphone :size="18" />公告中心</RouterLink>
      <RouterLink to="/versions" @click="open = false"><History :size="18" />版本更新</RouterLink>
      <RouterLink v-if="auth.canModerate" to="/admin" @click="open = false"><ShieldCheck :size="18" />{{ auth.isAdmin ? '监管台' : auth.isDisciplinarian ? '审核台' : '权限管理' }}</RouterLink>
      <RouterLink v-if="auth.canOperate" to="/operations" @click="open = false"><BarChart3 :size="18" />社区运营</RouterLink>
      <RouterLink v-if="auth.isLoggedIn" to="/profile" @click="open = false"><UserRound :size="18" />个人设置</RouterLink>
      <button v-if="auth.isLoggedIn" @click="logout"><LogOut :size="18" />退出登录</button>
      <RouterLink v-else to="/login" @click="open = false"><UserRound :size="18" />登录 / 注册</RouterLink>
    </div>
  </header>
</template>
