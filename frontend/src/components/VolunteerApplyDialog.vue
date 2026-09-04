<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { HeartHandshake, X } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'

const emit = defineEmits(['close', 'submitted'])
const toast = useToast()
const reason = ref('')
const busy = ref(false)

async function submit() {
  if (reason.value.trim().length < 10) return toast.error('申请理由请至少填写 10 个字符')
  busy.value = true
  try {
    const { data } = await api.post('/volunteer-applications', { reason: reason.value.trim() })
    toast.success('申请已提交，请等待管理员审核')
    emit('submitted', data)
    emit('close')
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    busy.value = false
  }
}

function onKey(event) { if (event.key === 'Escape') emit('close') }
onMounted(() => { document.body.classList.add('modal-open'); window.addEventListener('keydown', onKey) })
onBeforeUnmount(() => { document.body.classList.remove('modal-open'); window.removeEventListener('keydown', onKey) })
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="dialog report-dialog" role="dialog" aria-modal="true" aria-label="申请成为志愿者">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>
      <div class="dialog-heading"><span class="eyebrow"><HeartHandshake :size="14" /> VOLUNTEER</span><h2>申请成为志愿者</h2><p>说说你为什么想加入志愿者，管理员会尽快审核你的申请。</p></div>
      <form class="form-stack" @submit.prevent="submit">
        <label>申请理由<textarea v-model.trim="reason" required minlength="10" maxlength="500" rows="5" placeholder="如：日常在线时间长，熟悉社区规则，愿意协助处理委托…"></textarea><small>{{ reason.length }}/500</small></label>
        <div class="dialog-footer"><button type="button" class="button secondary" :disabled="busy" @click="$emit('close')">取消</button><button class="button" :disabled="busy"><HeartHandshake :size="16" />{{ busy ? '提交中…' : '提交申请' }}</button></div>
      </form>
    </section>
  </div>
</template>
