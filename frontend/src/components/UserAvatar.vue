<script setup>
defineProps({
  user: { type: Object, required: true },
  size: { type: Number, default: 36 },
})
</script>

<template>
  <span
    class="u-avatar"
    :style="{ width: `${size}px`, height: `${size}px`, fontSize: `${Math.round(size * 0.42)}px` }"
  >
    <img v-if="user.avatar_url" :src="user.avatar_url" :alt="`${user.nickname} 的头像`" />
    <template v-else>{{ user.nickname?.slice(0, 1) || '?' }}</template>
    <span v-if="user.avatar_url && !user.avatar_visible" class="u-avatar-pending">审核中</span>
  </span>
</template>

<style scoped>
.u-avatar {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 50%;
  overflow: hidden;
  background: var(--blue);
  color: #fff;
  font-weight: 700;
  font-family: Georgia, serif;
}

.u-avatar img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.u-avatar-pending {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1;
  font-family: inherit;
  font-size: 10px;
  font-weight: 600;
  line-height: 1.5;
  text-align: center;
  background: rgba(24, 32, 29, 0.72);
  color: #fff;
}
</style>
