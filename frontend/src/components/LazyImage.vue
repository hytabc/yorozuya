<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

// 图片懒加载：进入视口才真正请求图片，加载期间显示 shimmer 占位，加载完成后淡入。
// 单根 <img> 渲染，class/事件通过属性透传合并，保证既有 `.card > img` 等选择器继续生效。
const props = defineProps({
  src: { type: String, default: '' },
  alt: { type: String, default: '' },
})

// 提前 200px 开始加载，滚动到图片前通常已经就绪，避免看到占位闪烁。
const ROOT_MARGIN = '200px'

const el = ref(null)
const shown = ref(false)
const loaded = ref(false)
let observer = null

function disconnect() {
  if (observer) {
    observer.disconnect()
    observer = null
  }
}

onMounted(() => {
  if (typeof IntersectionObserver === 'undefined') {
    shown.value = true
    return
  }
  observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) {
      shown.value = true
      disconnect()
    }
  }, { rootMargin: ROOT_MARGIN })
  if (el.value) observer.observe(el.value)
})

// 换图（编辑已有照片）时重新走一次淡入，避免沿用上一张的已加载状态。
watch(() => props.src, () => { loaded.value = false })

onBeforeUnmount(disconnect)
</script>

<template>
  <img
    ref="el"
    class="lazy-img"
    :class="{ 'is-pending': !loaded, 'is-loaded': loaded }"
    :src="shown ? src : undefined"
    :alt="alt"
    loading="lazy"
    decoding="async"
    @load="loaded = true"
    @error="loaded = true"
  />
</template>
