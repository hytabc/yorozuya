<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Sparkles, X } from 'lucide-vue-next'
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
    const { data } = await api.post('/beta-applications', { reason: reason.value.trim() })
    toast.success('内测申请已提交，请等待审核')
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
    <section class="dialog report-dialog" role="dialog" aria-modal="true" aria-label="申请虚拟人生内测资格">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>
      <div class="dialog-heading"><span class="eyebrow"><Sparkles :size="14" /> BETA ACCESS</span><h2>申请虚拟人生内测</h2><p>告诉我们你想如何体验虚拟人生，审核通过后即可进入内测功能。</p></div>
      <form class="form-stack" @submit.prevent="submit">
        <label>申请理由<textarea v-model.trim="reason" required minlength="10" maxlength="500" rows="5" placeholder="如：希望体验并反馈剧情、交互和稳定性…"></textarea><small>{{ reason.length }}/500</small></label>
        <div class="dialog-footer"><button type="button" class="button secondary" :disabled="busy" @click="$emit('close')">取消</button><button class="button" :disabled="busy"><Sparkles :size="16" />{{ busy ? '提交中…' : '提交申请' }}</button></div>
      </form>
    </section>
  </div>
</template>
