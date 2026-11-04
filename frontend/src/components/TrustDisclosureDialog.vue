<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { X } from '@lucide/vue'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import { DISCLOSURE_DEFAULT, TRUST_DISCLOSURE, disclosurePatch } from '../trust'

const props = defineProps({
  disclosure: { type: Object, default: () => ({ ...DISCLOSURE_DEFAULT }) },
})
const emit = defineEmits(['close', 'saved'])
const toast = useToast()
const local = ref({ ...DISCLOSURE_DEFAULT, ...props.disclosure })
const busy = ref(false)
const enabledCount = computed(() => TRUST_DISCLOSURE.filter((item) => local.value[item.key]).length)

async function save() {
  busy.value = true
  try {
    const { data } = await api.patch('/vrchat/disclosure', disclosurePatch(local.value))
    toast.success('披露设置已保存')
    emit('saved', data)
    emit('close')
  } catch (error) {
    toast.error(errorMessage(error, '保存失败，请稍后重试'))
  } finally {
    busy.value = false
  }
}

function onKey(event) {
  if (event.key === 'Escape') emit('close')
}
onMounted(() => {
  document.body.classList.add('modal-open')
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => {
  document.body.classList.remove('modal-open')
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="dialog" role="dialog" aria-modal="true" aria-label="VRChat 信息披露设置">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>
      <div class="dialog-heading">
        <span class="eyebrow">WHO CAN SEE WHAT</span>
        <h2>别人可以看到什么？</h2>
        <p>每一项都由你单独控制，随时可以关闭；关闭后其他人看不到该项，你自己仍然可以在设置里查看。</p>
      </div>

      <div class="disclosure-list">
        <label v-for="item in TRUST_DISCLOSURE" :key="item.key" class="disclosure-row" :class="{ disabled: !item.available }">
          <input v-model="local[item.key]" type="checkbox" :disabled="!item.available" />
          <span>
            <strong>{{ item.label }}</strong>
            <small class="field-hint">{{ item.hint }}</small>
          </span>
          <em v-if="!item.available" class="muted">尚未接入</em>
        </label>
      </div>

      <p class="field-hint">
        当前已开启 {{ enabledCount }} 项。数据由你手动填写并标注为「未验证」；当前尚未接入 VRChat 自动同步。
      </p>

      <div class="dialog-footer">
        <span class="muted">由本人手动填写，可能滞后，不构成平台担保。</span>
        <div class="dialog-actions">
          <button type="button" class="button secondary" @click="$emit('close')">取消</button>
          <button type="button" class="button" :disabled="busy" @click="save">{{ busy ? '保存中…' : '保存设置' }}</button>
        </div>
      </div>
    </section>
  </div>
</template>
