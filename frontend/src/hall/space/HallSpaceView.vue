<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { buildLayout, MAX_SPACE_NODES, STATUS_COLORS } from './layout'
import HallSpaceCanvas from './HallSpaceCanvas.vue'

const props = defineProps({
  tasks: { type: Array, default: () => [] },
  selected: { type: Object, default: null },
})
const emit = defineEmits(['select', 'open', 'fallback'])

const layout = computed(() => buildLayout(props.tasks))
const legend = [
  { label: '招募中', color: STATUS_COLORS.published },
  { label: '处理中', color: STATUS_COLORS.accepted },
  { label: '已完成', color: STATUS_COLORS.completed },
]

// Esc 只清空选中，不关闭页面；列表视图才是默认入口。
function onKey(event) {
  if (event.key === 'Escape') emit('select', null)
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <section class="hall-space" aria-label="星图视图">
    <div class="hall-space-toolbar">
      <span class="muted">拖拽平移 · 滚轮或双指缩放 · 单击查看 · 双击打开 · Tab 在卡片间移动</span>
      <span v-if="layout.truncated" class="muted">仅展示前 {{ MAX_SPACE_NODES }} 条，缩小筛选范围可看更多</span>
      <span class="hall-space-legend">
        <span v-for="item in legend" :key="item.label" class="hall-space-legend-item">
          <i :style="{ background: item.color }" />{{ item.label }}
        </span>
      </span>
    </div>

    <HallSpaceCanvas
      v-if="layout.nodes.length"
      :nodes="layout.nodes"
      :selected-id="selected?.id ?? null"
      @select="emit('select', $event)"
      @open="emit('open', $event)"
      @fallback="emit('fallback')"
    />
    <div v-else class="empty-state">
      <span>星</span>
      <h3>这片星域还是空的</h3>
      <p>切换回列表看看，或成为第一个在这里发布委托的人。</p>
    </div>

    <p v-if="selected" class="hall-space-selected">
      <span class="muted">已选中：</span>
      <strong>{{ selected.title }}</strong>
      <button type="button" class="text-link" @click="emit('open', selected)">查看委托详情</button>
    </p>
  </section>
</template>
