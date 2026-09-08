<script setup>
// 图片字段:预览 + URL 输入 + 本地上传(POST /api/virtual-life/assets)。
import { ref } from 'vue'
import { uploadAsset, showAdminToast } from './useLifeAdmin'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '图片 URL 或上传' },
})
const emit = defineEmits(['update:modelValue'])
const uploading = ref(false)
const fileInput = ref(null)

async function pick(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || uploading.value) return
  uploading.value = true
  try {
    emit('update:modelValue', await uploadAsset(file))
    showAdminToast('图片已上传')
  } catch (e) {
    showAdminToast('上传失败：' + (e.response?.data?.detail || e.message))
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <span class="la-img-cell">
    <img v-if="modelValue" :src="modelValue" alt="预览" />
    <span v-else class="la-missing">未设置</span>
    <input type="text" :value="modelValue" :placeholder="placeholder"
           @input="emit('update:modelValue', $event.target.value)" />
    <button type="button" class="la-mini" :disabled="uploading" @click="fileInput.click()">
      {{ uploading ? '上传中…' : '上传' }}
    </button>
    <input ref="fileInput" type="file" accept="image/*" hidden @change="pick" />
  </span>
</template>
