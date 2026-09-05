<script setup>
import { onMounted, ref } from 'vue'
import { CalendarDays, EyeOff, Heart, KeyRound, MessageCircle, ShieldCheck, Store, UserRound, X } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { roleLabel } from '../constants'
import UserAvatar from './UserAvatar.vue'

const props = defineProps({
  userId: { type: Number, default: null },
  initialUser: { type: Object, default: null },
  // 留言板等公开场景：只展示个人资料，不展示联系方式
  hideContact: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])
const loading = ref(!props.initialUser)
const error = ref('')
const user = ref(props.initialUser)

const joined = (value) =>
  value
    ? new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long' }).format(new Date(value))
    : ''

onMounted(async () => {
  if (props.initialUser) return
  try {
    user.value = (await api.get(`/users/${props.userId}`)).data
  } catch (err) {
    error.value = errorMessage(err, '无法加载该用户资料')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="user-card" role="dialog" aria-label="用户资料">
    <button class="icon-button user-card-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="18" /></button>
    <div v-if="loading" class="user-card-body muted">正在加载资料…</div>
    <div v-else-if="error" class="user-card-body">{{ error }}</div>
    <template v-else-if="user">
      <div class="user-card-head">
        <UserAvatar :user="user" :size="54" />
        <div>
          <h4>{{ user.nickname }}<span v-if="user.is_admin" class="admin-tag"><ShieldCheck :size="13" />管理员</span><span v-else class="role-tag" :class="`role-${user.role}`"><Store v-if="user.role === 'staff'" :size="13" /><Heart v-else-if="user.role === 'volunteer'" :size="13" /><UserRound v-else :size="13" />{{ roleLabel(user) }}</span></h4>
          <span class="user-card-since muted"><CalendarDays :size="14" />{{ joined(user.created_at) }} 加入</span>
        </div>
      </div>
      <p v-if="user.bio" class="user-card-bio">{{ user.bio }}</p>
      <p v-else class="user-card-bio muted">这个人还没有填写简介。</p>
      <div v-if="user.photos?.length" class="user-profile-photos">
        <figure v-for="photo in user.photos" :key="photo.id" :class="{ blocked: !photo.is_visible }">
          <img :src="photo.image_url" :alt="`${user.nickname} 的介绍图片`" />
          <span v-if="!photo.is_visible"><EyeOff :size="13" />已屏蔽</span>
        </figure>
      </div>
      <div v-if="!hideContact && user.qq" class="user-card-qq"><MessageCircle :size="15" /><span><strong>QQ：{{ user.qq }}</strong><small>{{ user.role === 'staff' ? '管理员联系方式对所有人公开' : (user.qq_public ? '该志愿者已选择公开联系方式' : '你们已建立委托协作，联系方式已向你开放') }}</small></span></div>
      <div v-else-if="!hideContact" class="user-card-qq muted"><KeyRound :size="15" /><span><strong>暂无可见联系方式</strong><small>{{ user.role === 'volunteer' && !user.qq_public ? '该志愿者未在成员名录中公开 QQ' : '仅共同协作者可见对方 QQ' }}</small></span></div>
      <p v-else class="user-card-privacy muted"><MessageCircle :size="15" />联系方式不在公开资料中展示</p>
    </template>
  </section>
</template>
