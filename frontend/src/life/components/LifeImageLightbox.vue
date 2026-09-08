<!-- // 全屏图片灯箱：点击遮罩或 ESC 关闭（阶段 8a）。 -->
<template>
  <div
    class="life-image-lightbox"
    role="dialog"
    aria-modal="true"
    :aria-label="alt"
    @click="emit('close')"
  >
    <img class="life-image-lightbox__image" :src="src" :alt="alt" />
    <button
      class="life-image-lightbox__close"
      type="button"
      aria-label="关闭图片灯箱"
      @click.stop="emit('close')"
    >
      ×
    </button>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'

defineProps({
  src: {
    type: String,
    required: true,
  },
  alt: {
    type: String,
    default: '图片',
  },
})

const emit = defineEmits(['close'])
let previousOverflow = ''

function handleKeydown(event) {
  if (event.key === 'Escape') {
    emit('close')
  }
}

onMounted(() => {
  previousOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.body.style.overflow = previousOverflow
})
</script>

<style scoped>
.life-image-lightbox {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, .75);
}

.life-image-lightbox__image {
  display: block;
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, .2);
}

.life-image-lightbox__close {
  position: absolute;
  top: 16px;
  right: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid #d9dedb;
  border-radius: 50%;
  background: #fff;
  color: #333;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
}
</style>
