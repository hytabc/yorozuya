<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  DoughnutController,
  Legend,
  LinearScale,
  Tooltip,
} from 'chart.js'
import { theme } from '../composables/theme'

// 按需注册（当前只用到柱状图与环形图），避免把整个 chart.js 打进产物；
// 本组件只在 /operations 懒加载。
Chart.register(ArcElement, BarController, BarElement, CategoryScale, DoughnutController, Legend, LinearScale, Tooltip)

const props = defineProps({
  type: { type: String, default: 'bar' },
  data: { type: Object, required: true },
  indexAxis: { type: String, default: 'x' },
  stacked: { type: Boolean, default: false },
  height: { type: Number, default: 240 },
  // 将原始数值格式化为展示文案（例如秒 → 分秒）。
  valueFormatter: { type: Function, default: null },
})

const canvas = ref(null)
let chart = null

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

// 从主题 CSS 变量取色，使「经典风 / 像素风」都不用单独维护一套图表配色。
function palette() {
  return {
    green: cssVar('--green', '#237a57'),
    blue: cssVar('--blue', '#286c86'),
    muted: cssVar('--muted', '#69736e'),
    line: cssVar('--line', '#d9dedb'),
  }
}

function seriesColors() {
  const colors = palette()
  return [colors.green, colors.blue, '#c98b3b', '#8a6fbf', '#3f9d8f', colors.muted]
}

// 只在数据集没有自带颜色时补默认色，父组件仍可覆盖。
function withPalette(data) {
  const colors = seriesColors()
  const datasets = (data.datasets || []).map((dataset, index) => {
    if (props.type === 'doughnut') {
      if (dataset.backgroundColor) return dataset
      return { ...dataset, backgroundColor: colors, borderColor: 'transparent' }
    }
    const color = colors[index % colors.length]
    return {
      ...dataset,
      backgroundColor: dataset.backgroundColor || color,
      borderColor: dataset.borderColor || color,
    }
  })
  return { ...data, datasets }
}

function legendOptions(colors) {
  return {
    display: true,
    position: 'bottom',
    labels: { color: colors.muted, boxWidth: 10, boxHeight: 10, font: { size: 10 }, usePointStyle: true },
  }
}

function buildOptions() {
  const colors = palette()
  if (props.type === 'doughnut') {
    return {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      plugins: { legend: legendOptions(colors), tooltip: { callbacks: { label: tooltipLabel } } },
    }
  }
  const horizontal = props.indexAxis === 'y'
  const valueAxis = horizontal ? 'x' : 'y'
  const axis = (extra) => ({
    grid: { color: colors.line },
    ticks: { color: colors.muted, font: { size: 10 } },
    ...extra,
  })
  return {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: props.indexAxis,
    plugins: { legend: legendOptions(colors), tooltip: { intersect: false, callbacks: { label: tooltipLabel } } },
    scales: {
      x: axis(horizontal ? { beginAtZero: true, stacked: props.stacked } : { stacked: props.stacked }),
      y: axis(horizontal ? { stacked: props.stacked } : { beginAtZero: true, stacked: props.stacked }),
    },
  }
}

function formatValue(value) {
  return props.valueFormatter ? props.valueFormatter(value) : String(value)
}

function tooltipLabel(context) {
  if (props.type === 'doughnut') {
    const total = context.dataset.data.reduce((sum, item) => sum + Number(item || 0), 0)
    const share = total ? Math.round((Number(context.parsed || 0) / total) * 100) : 0
    return `${context.label}：${formatValue(context.parsed)}（${share}%）`
  }
  const raw = props.indexAxis === 'y' ? context.parsed.x : context.parsed.y
  const prefix = context.dataset.label ? `${context.dataset.label}：` : ''
  return `${prefix}${formatValue(raw)}`
}

function build() {
  if (!canvas.value) return
  if (chart) {
    chart.destroy()
    chart = null
  }
  chart = new Chart(canvas.value, {
    type: props.type,
    data: withPalette(props.data),
    options: buildOptions(),
  })
}

onMounted(build)
// 切换主题会改变 CSS 变量，直接重建以套用新配色。
watch(theme, () => build())
watch(
  () => props.data,
  (value) => {
    if (chart) {
      chart.data = withPalette(value)
      chart.update()
    }
  },
  { deep: true },
)
onBeforeUnmount(() => {
  if (chart) {
    chart.destroy()
    chart = null
  }
})
</script>

<template>
  <div class="chart-box" :style="{ height: `${height}px` }">
    <canvas ref="canvas" />
  </div>
</template>
