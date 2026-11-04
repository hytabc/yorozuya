<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Check, Copy, Download, Share2, X } from '@lucide/vue'
import QRCode from 'qrcode'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'

const props = defineProps({ task: { type: Object, required: true } })
const emit = defineEmits(['close'])
const auth = useAuthStore()
const toast = useToast()
const canvas = ref(null)
const copied = ref(false)
const url = computed(() => `${window.location.origin}/?task=${props.task.id}`)
const canNativeShare = computed(() => typeof navigator !== 'undefined' && Boolean(navigator.share))

async function record(channel) {
  if (!auth.isLoggedIn) return
  try { await api.post(`/tasks/${props.task.id}/share`, { channel }) } catch { /* 记录失败不影响分享 */ }
}

async function copyLink() {
  try {
    await navigator.clipboard.writeText(url.value)
    copied.value = true
    toast.success('链接已复制')
    await record('copy')
    setTimeout(() => { copied.value = false }, 1600)
  } catch {
    toast.error('复制失败，请手动选择链接复制')
  }
}

async function nativeShare() {
  try {
    await navigator.share({ title: props.task.title, text: `来自万事屋的委托：${props.task.title}`, url: url.value })
    await record('native')
  } catch { /* 用户取消分享 */ }
}

function download() {
  if (!canvas.value) return
  const link = document.createElement('a')
  link.href = canvas.value.toDataURL('image/png')
  link.download = `万事屋委托-${props.task.id}.png`
  link.click()
  record('qrcode')
}

function onKey(event) { if (event.key === 'Escape') emit('close') }

onMounted(async () => {
  document.body.classList.add('modal-open')
  window.addEventListener('keydown', onKey)
  try {
    await QRCode.toCanvas(canvas.value, url.value, {
      width: 240,
      margin: 2,
      color: { dark: '#18201d', light: '#ffffff' },
    })
  } catch (error) {
    toast.error(errorMessage(error, '二维码生成失败'))
  }
  if (auth.isLoggedIn) record('dialog')
})
onUnmounted(() => {
  document.body.classList.remove('modal-open')
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="dialog share-dialog" role="dialog" aria-modal="true" aria-label="分享委托">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>
      <div class="dialog-heading"><span class="eyebrow">SHARE</span><h2>分享这份委托</h2><p>把链接或二维码发给朋友，对方登录后可以直接打开详情。</p></div>
      <figure class="share-qr">
        <canvas ref="canvas" aria-label="委托二维码" />
        <figcaption class="muted">{{ task.title }}</figcaption>
      </figure>
      <label class="share-link-field">链接
        <input :value="url" readonly aria-label="分享链接" @focus="$event.target.select()" />
      </label>
      <div class="dialog-actions share-actions">
        <button type="button" class="button" @click="copyLink"><Check v-if="copied" :size="16" /><Copy v-else :size="16" />{{ copied ? '已复制' : '复制链接' }}</button>
        <button type="button" class="button secondary" @click="download"><Download :size="16" />保存二维码</button>
        <button v-if="canNativeShare" type="button" class="button secondary" @click="nativeShare"><Share2 :size="16" />系统分享</button>
      </div>
    </section>
  </div>
</template>
