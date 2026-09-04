<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { BriefcaseBusiness, HeartHandshake, LogOut, Map, Menu, MessagesSquare, ShieldCheck, Store, UserRound, X } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth'
import UserAvatar from './UserAvatar.vue'

const auth = useAuthStore()
const router = useRouter()
const open = ref(false)

function logout() {
  auth.logout()
  open.value = false
  router.push('/')
}
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
        <RouterLink to="/staff">成员名录</RouterLink>
        <RouterLink to="/board">留言板</RouterLink>
        <RouterLink to="/maps">地图推荐</RouterLink>
        <RouterLink to="/sugar">砂糖社</RouterLink>
        <RouterLink v-if="auth.isLoggedIn" to="/mine">我的委托</RouterLink>
        <RouterLink v-if="auth.canManageRoles" to="/admin">{{ auth.isAdmin ? '监管台' : '权限管理' }}</RouterLink>
      </nav>

      <div class="header-actions">
        <template v-if="auth.isLoggedIn">
          <RouterLink to="/profile" class="user-chip">
            <UserAvatar :user="auth.user" :size="30" />
            <span>{{ auth.user?.nickname }}</span>
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
      <RouterLink to="/staff" @click="open = false"><Store :size="18" />成员名录</RouterLink>
      <RouterLink to="/board" @click="open = false"><MessagesSquare :size="18" />留言板</RouterLink>
      <RouterLink to="/maps" @click="open = false"><Map :size="18" />地图推荐</RouterLink>
      <RouterLink to="/sugar" @click="open = false"><HeartHandshake :size="18" />砂糖社</RouterLink>
      <RouterLink v-if="auth.isLoggedIn" to="/mine" @click="open = false"><BriefcaseBusiness :size="18" />我的委托</RouterLink>
      <RouterLink v-if="auth.isLoggedIn" to="/profile" @click="open = false"><UserRound :size="18" />个人设置</RouterLink>
      <RouterLink v-if="auth.canManageRoles" to="/admin" @click="open = false"><ShieldCheck :size="18" />{{ auth.isAdmin ? '监管台' : '权限管理' }}</RouterLink>
      <button v-if="auth.isLoggedIn" @click="logout"><LogOut :size="18" />退出登录</button>
      <RouterLink v-else to="/login" @click="open = false"><UserRound :size="18" />登录 / 注册</RouterLink>
    </div>
  </header>
</template>
