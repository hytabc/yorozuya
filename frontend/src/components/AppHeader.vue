<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BarChart3, BookOpen, BriefcaseBusiness, ChevronDown, CircleQuestionMark, Gamepad2, HeartHandshake, History, LogOut, Map, Megaphone, Menu, MessagesSquare, ShieldCheck, Snowflake, Sparkles, Store, UserPlus, UserRound, Users, X } from '@lucide/vue'
import { useAuthStore } from '../stores/auth'
import { HALLS, hallContainsPath, moreLinks, visibleItems } from '../navigation'
import UserAvatar from './UserAvatar.vue'
import UserTitleTag from './UserTitleTag.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const open = ref(false)
// 桌面展开的下拉 id（大厅 id 或 'more'）；同一时刻只开一个。
const openMenu = ref(null)
// 移动端折叠的分组 id。
const mobileGroup = ref(null)

// 图标名 → 组件：navigation.js 只存名字，保持那份配置可被 node:test 直接加载。
const ICONS = {
  BriefcaseBusiness, MessagesSquare, CircleQuestionMark, Gamepad2, Sparkles, Snowflake,
  BookOpen, Map, UserPlus, HeartHandshake, Users, Store, Megaphone, History,
  ShieldCheck, BarChart3,
}

// 六个大厅，按当前身份过滤条目；整组无可见条目时隐藏。
const halls = computed(() =>
  HALLS.map((hall) => ({ ...hall, items: visibleItems(hall, auth) })).filter((hall) => hall.items.length),
)
const manageLinks = computed(() => moreLinks(auth))
const moreActive = computed(() => manageLinks.value.some((link) => link.to === route.path))

const hallActive = (hall) => hallContainsPath(hall, route.path)

function toggleMenu(id) {
  openMenu.value = openMenu.value === id ? null : id
}
function toggleMobileGroup(id) {
  mobileGroup.value = mobileGroup.value === id ? null : id
}
function closeMenus() {
  openMenu.value = null
}
// 监管台在不同角色下叫法不同（超管=监管台，风纪委员=审核台，管理员=权限管理）。
function linkLabel(link) {
  if (link.to === '/admin') return auth.isAdmin ? '监管台' : auth.isDisciplinarian ? '审核台' : '权限管理'
  return link.label
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
        <template v-for="hall in halls" :key="hall.id">
          <RouterLink v-if="hall.items.length === 1" :to="hall.items[0].to">{{ hall.items[0].label }}</RouterLink>
          <div v-else class="nav-more-wrap">
            <button
              class="nav-more"
              :class="{ active: hallActive(hall) }"
              type="button"
              aria-haspopup="menu"
              :aria-expanded="openMenu === hall.id"
              @click.stop="toggleMenu(hall.id)"
            >{{ hall.label }}<ChevronDown :size="14" /></button>
            <div v-if="openMenu === hall.id" class="nav-more-menu" role="menu">
              <RouterLink v-for="item in hall.items" :key="item.to" role="menuitem" :to="item.to" @click="closeMenus">{{ item.label }}</RouterLink>
            </div>
          </div>
        </template>
        <div v-if="manageLinks.length" class="nav-more-wrap">
          <button
            class="nav-more"
            :class="{ active: moreActive }"
            type="button"
            aria-haspopup="menu"
            :aria-expanded="openMenu === 'more'"
            @click.stop="toggleMenu('more')"
          >更多<ChevronDown :size="14" /></button>
          <div v-if="openMenu === 'more'" class="nav-more-menu" role="menu">
            <RouterLink v-for="link in manageLinks" :key="link.to" role="menuitem" :to="link.to" @click="closeMenus">{{ linkLabel(link) }}</RouterLink>
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
      <template v-for="hall in halls" :key="hall.id">
        <RouterLink v-if="hall.items.length === 1" :to="hall.items[0].to" @click="open = false">
          <component :is="ICONS[hall.items[0].icon]" v-if="ICONS[hall.items[0].icon]" :size="18" />{{ hall.items[0].label }}
        </RouterLink>
        <template v-else>
          <button
            class="mobile-group-toggle"
            type="button"
            :aria-expanded="mobileGroup === hall.id"
            @click.stop="toggleMobileGroup(hall.id)"
          >
            <component :is="ICONS[hall.icon]" v-if="ICONS[hall.icon]" :size="18" />{{ hall.label }}<ChevronDown :size="16" class="mobile-group-caret" :class="{ open: mobileGroup === hall.id }" />
          </button>
          <div v-if="mobileGroup === hall.id" class="mobile-group">
            <RouterLink v-for="item in hall.items" :key="item.to" :to="item.to" @click="open = false">
              <component :is="ICONS[item.icon]" v-if="ICONS[item.icon]" :size="18" />{{ item.label }}
            </RouterLink>
          </div>
        </template>
      </template>
      <template v-if="manageLinks.length">
        <button
          class="mobile-group-toggle"
          type="button"
          :aria-expanded="mobileGroup === 'more'"
          @click.stop="toggleMobileGroup('more')"
        >
          <ShieldCheck :size="18" />更多<ChevronDown :size="16" class="mobile-group-caret" :class="{ open: mobileGroup === 'more' }" />
        </button>
        <div v-if="mobileGroup === 'more'" class="mobile-group">
          <RouterLink v-for="link in manageLinks" :key="link.to" :to="link.to" @click="open = false">
            <component :is="ICONS[link.icon]" v-if="ICONS[link.icon]" :size="18" />{{ linkLabel(link) }}
          </RouterLink>
        </div>
      </template>
      <RouterLink v-if="auth.isLoggedIn" to="/profile" @click="open = false"><UserRound :size="18" />个人设置</RouterLink>
      <button v-if="auth.isLoggedIn" @click="logout"><LogOut :size="18" />退出登录</button>
      <RouterLink v-else to="/login" @click="open = false"><UserRound :size="18" />登录 / 注册</RouterLink>
    </div>
  </header>
</template>
