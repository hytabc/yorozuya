<script setup>
import { computed, ref } from 'vue'
import { FileImage, ImagePlus, X } from 'lucide-vue-next'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  maxFiles: { type: Number, required: true },
  maxBytes: { type: Number, required: true },
  maxTotalBytes: { type: Number, default: 0 },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'error'])

const input = ref(null)
const dragging = ref(false)
let dragDepth = 0

const maxMegabytes = computed(() => Math.round(props.maxBytes / 1024 / 1024))
const totalMegabytes = computed(() => Math.round(props.maxTotalBytes / 1024 / 1024))

const formatSize = (bytes) => bytes >= 1024 * 1024
  ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
  : `${Math.max(1, Math.round(bytes / 1024))} KB`

function openPicker() {
  if (!props.disabled && props.maxFiles > 0) input.value?.click()
}

function isSupported(file) {
  return ['image/png', 'image/jpeg'].includes(file.type) || /\.(png|jpe?g)$/i.test(file.name)
}

function addFiles(fileList) {
  if (props.disabled) return
  const incoming = Array.from(fileList || [])
  if (!incoming.length) return
  const next = [...props.modelValue, ...incoming]
  if (next.length > props.maxFiles) return emit('error', `最多选择 ${props.maxFiles} 张图片`)
  if (incoming.some((file) => !isSupported(file))) return emit('error', '仅支持 PNG 或 JPG 格式的图片')
  if (incoming.some((file) => file.size > props.maxBytes)) return emit('error', `单张图片不能超过 ${maxMegabytes.value} MB`)
  if (props.maxTotalBytes && next.reduce((sum, file) => sum + file.size, 0) > props.maxTotalBytes) {
    return emit('error', `所选图片合计不能超过 ${totalMegabytes.value} MB`)
  }
  emit('update:modelValue', next)
}

function onInput(event) {
  addFiles(event.target.files)
  event.target.value = ''
}

function onDragEnter() {
  if (props.disabled) return
  dragDepth += 1
  dragging.value = true
}

function onDragLeave() {
  dragDepth = Math.max(0, dragDepth - 1)
  if (!dragDepth) dragging.value = false
}

function onDrop(event) {
  dragDepth = 0
  dragging.value = false
  addFiles(event.dataTransfer?.files)
}

function removeFile(index) {
  if (props.disabled) return
  emit('update:modelValue', props.modelValue.filter((_, current) => current !== index))
}
</script>

<template>
  <div class="image-dropzone">
    <input ref="input" class="image-dropzone-input" type="file" accept="image/png,image/jpeg,.png,.jpg,.jpeg" multiple :disabled="disabled" @change="onInput" />
    <div
      class="image-dropzone-area"
      :class="{ dragging, disabled }"
      role="button"
      :tabindex="disabled || maxFiles <= 0 ? -1 : 0"
      :aria-disabled="disabled || maxFiles <= 0"
      @click="openPicker"
      @keydown.enter.prevent="openPicker"
      @keydown.space.prevent="openPicker"
      @dragenter.prevent="onDragEnter"
      @dragover.prevent
      @dragleave.prevent="onDragLeave"
      @drop.prevent="onDrop"
    >
      <ImagePlus :size="22" />
      <span><strong>{{ dragging ? '松开即可添加图片' : '选择图片或拖放到这里' }}</strong><small>PNG / JPG · 最多 {{ maxFiles }} 张 · 单张不超过 {{ maxMegabytes }} MB</small></span>
    </div>

    <ul v-if="modelValue.length" class="image-dropzone-files" aria-label="已选择的图片">
      <li v-for="(file, index) in modelValue" :key="`${file.name}-${file.size}-${file.lastModified}-${index}`">
        <FileImage :size="15" />
        <span><strong>{{ file.name }}</strong><small>{{ formatSize(file.size) }}</small></span>
        <button type="button" title="移除图片" :aria-label="`移除 ${file.name}`" :disabled="disabled" @click="removeFile(index)"><X :size="15" /></button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.image-dropzone { display: grid; gap: 8px; }
.image-dropzone-input { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.image-dropzone-area { min-height: 112px; display: flex; align-items: center; justify-content: center; gap: 12px; padding: 18px; border: 1px dashed #b8c1bc; border-radius: 6px; color: #59645f; background: #fafbfa; cursor: pointer; transition: border-color .15s, background .15s; }
.image-dropzone-area:hover, .image-dropzone-area:focus-visible, .image-dropzone-area.dragging { border-color: var(--green); background: var(--green-soft); outline: none; }
.image-dropzone-area.disabled { opacity: .58; cursor: not-allowed; }
.image-dropzone-area > svg { flex: 0 0 auto; color: var(--green); }
.image-dropzone-area span { min-width: 0; display: grid; gap: 5px; }
.image-dropzone-area strong { overflow-wrap: anywhere; color: var(--ink); font-size: 13px; }
.image-dropzone-area small { color: var(--muted); font-size: 11px; font-weight: 400; }
.image-dropzone-files { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; }
.image-dropzone-files li { min-height: 40px; display: grid; grid-template-columns: auto minmax(0, 1fr) 30px; align-items: center; gap: 9px; padding: 5px 6px 5px 10px; border: 1px solid var(--line); border-radius: 4px; background: white; }
.image-dropzone-files li > svg { color: var(--muted); }
.image-dropzone-files span { min-width: 0; display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.image-dropzone-files strong { overflow: hidden; color: var(--ink); font-size: 11px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.image-dropzone-files small { flex: 0 0 auto; color: var(--muted); font-size: 10px; }
.image-dropzone-files button { width: 30px; height: 30px; display: grid; place-items: center; padding: 0; border: 0; border-radius: 4px; color: var(--muted); background: transparent; cursor: pointer; }
.image-dropzone-files button:hover:not(:disabled), .image-dropzone-files button:focus-visible { color: var(--red); background: var(--red-soft); outline: none; }

@media (max-width: 480px) {
  .image-dropzone-area { min-height: 104px; align-items: flex-start; flex-direction: column; }
  .image-dropzone-files span { align-items: flex-start; flex-direction: column; gap: 2px; }
}
</style>
