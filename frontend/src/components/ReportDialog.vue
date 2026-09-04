<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Flag, X } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'

const props = defineProps({ task: { type: Object, required: true } })
const emit = defineEmits(['close', 'reported'])
const toast = useToast()
const reason = ref('')
const busy = ref(false)

async function submit() {
  if (reason.value.trim().length < 2) return toast.error('请填写至少 2 个字符的举报原因')
  busy.value = true
  try {
    await api.post(`/tasks/${props.task.id}/report`, { reason: reason.value.trim() })
    toast.success('举报已提交，店员/管理员会尽快处理')
    emit('reported')
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
    <section class="dialog report-dialog" role="dialog" aria-modal="true" aria-label="举报委托">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>
      <div class="dialog-heading"><span class="eyebrow"><Flag :size="14" /> REPORT</span><h2>举报委托</h2><p>该委托将暂时移出大厅，由店员/管理员核实处理。</p></div>
      <form class="form-stack" @submit.prevent="submit">
        <label>举报原因<textarea v-model.trim="reason" required minlength="2" maxlength="200" rows="5" placeholder="如：疑似诈骗 / 违规内容 / 恶意行为"></textarea><small>{{ reason.length }}/200</small></label>
        <div class="dialog-footer"><button type="button" class="button secondary" :disabled="busy" @click="$emit('close')">取消</button><button class="button" :disabled="busy"><Flag :size="16" />{{ busy ? '提交中…' : '提交举报' }}</button></div>
      </form>
    </section>
  </div>
</template>
