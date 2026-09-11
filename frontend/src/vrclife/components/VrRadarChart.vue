<script setup>
/**
 * 自绘 SVG 六轴雷达图。
 */
import { computed } from 'vue';
import { clamp } from '../utils/format.js';

const props = defineProps({
  values: { type: Array, default: () => [0, 0, 0, 0, 0, 0] },
  labels: { type: Array, default: () => ['', '', '', '', '', ''] },
  size: { type: Number, default: 260 },
  strokeColor: { type: String, default: '#7c3aed' },
  fillColor: { type: String, default: 'rgba(6, 182, 212, 0.24)' },
  gridColor: { type: String, default: 'rgba(124, 58, 237, 0.32)' },
});

const N = 6;

const center = computed(() => props.size / 2);
const radius = computed(() => Math.max(20, props.size / 2 - 42));

function pt(i, r) {
  const a = -Math.PI / 2 + (i * 2 * Math.PI) / N;
  return [center.value + Math.cos(a) * r, center.value + Math.sin(a) * r];
}

function ringPoints(r) {
  const arr = [];
  for (let i = 0; i < N; i += 1) arr.push(pt(i, r).join(','));
  return arr.join(' ');
}

const rings = computed(() => [0.25, 0.5, 0.75, 1].map((l) => ringPoints(radius.value * l)));

const axes = computed(() => {
  const arr = [];
  for (let i = 0; i < N; i += 1) {
    const [x, y] = pt(i, radius.value);
    arr.push({ x, y });
  }
  return arr;
});

const poly = computed(() => {
  const arr = [];
  for (let i = 0; i < N; i += 1) {
    const v = clamp(props.values[i] || 0, 0, 100) / 100;
    arr.push(pt(i, radius.value * v).join(','));
  }
  return arr.join(' ');
});

const dots = computed(() => {
  const arr = [];
  for (let i = 0; i < N; i += 1) {
    const v = clamp(props.values[i] || 0, 0, 100) / 100;
    const [x, y] = pt(i, radius.value * v);
    arr.push({ x, y });
  }
  return arr;
});

const labelPts = computed(() => {
  const arr = [];
  for (let i = 0; i < N; i += 1) {
    const [x, y] = pt(i, radius.value + 22);
    arr.push({ x, y, text: props.labels[i] || '' });
  }
  return arr;
});
</script>

<template>
  <svg
    class="vr-radar"
    :width="size"
    :height="size"
    :viewBox="`0 0 ${size} ${size}`"
    role="img"
    aria-label="能力雷达图"
  >
    <polygon
      v-for="(r, i) in rings"
      :key="`ring-${i}`"
      :points="r"
      fill="none"
      :stroke="gridColor"
      stroke-width="1"
    />

    <line
      v-for="(a, i) in axes"
      :key="`axis-${i}`"
      :x1="center"
      :y1="center"
      :x2="a.x"
      :y2="a.y"
      :stroke="gridColor"
      stroke-width="1"
    />

    <polygon :points="poly" :fill="fillColor" :stroke="strokeColor" stroke-width="2" />

    <circle
      v-for="(d, i) in dots"
      :key="`dot-${i}`"
      :cx="d.x"
      :cy="d.y"
      r="3.5"
      fill="#06b6d4"
      :stroke="strokeColor"
      stroke-width="1.5"
    />

    <text
      v-for="(l, i) in labelPts"
      :key="`label-${i}`"
      :x="l.x"
      :y="l.y"
      class="radar-label"
      text-anchor="middle"
      dominant-baseline="middle"
    >{{ l.text }}</text>
  </svg>
</template>

<style scoped>
.vr-radar {
  display: block;
  max-width: 100%;
  height: auto;
}

.radar-label {
  fill: #8b7fa8;
  font-size: 12px;
  font-family: inherit;
}
</style>