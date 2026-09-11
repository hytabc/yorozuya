<script setup>
/**
 * 自绘 SVG 折线图（好感度 / 心态曲线）。只读 points，不依赖任何运行时状态。
 */
import { computed } from 'vue';
import { clamp } from '../utils/format.js';

const props = defineProps({
  points: { type: Array, default: () => [] },
  color: { type: String, default: '#06b6d4' },
  width: { type: Number, default: 320 },
  height: { type: Number, default: 96 },
});

const PAD = { l: 8, r: 8, t: 12, b: 14 };

const innerW = computed(() => Math.max(1, props.width - PAD.l - PAD.r));
const innerH = computed(() => Math.max(1, props.height - PAD.t - PAD.b));

const maxX = computed(() => {
  let m = 0;
  for (const p of props.points) {
    const x = Number(p.x);
    if (Number.isFinite(x) && x > m) m = x;
  }
  return m || 1;
});

function sx(x) {
  return PAD.l + (clamp(Number(x) || 0, 0, maxX.value) / maxX.value) * innerW.value;
}

function sy(y) {
  return PAD.t + (1 - clamp(Number(y) || 0, 0, 100) / 100) * innerH.value;
}

const viewBox = computed(() => '0 0 ' + props.width + ' ' + props.height);
const hasData = computed(() => props.points.length > 0);

const linePath = computed(() => {
  const pts = props.points;
  let d = '';
  for (let i = 0; i < pts.length; i += 1) {
    d += (i === 0 ? 'M' : 'L') + sx(pts[i].x).toFixed(1) + ',' + sy(pts[i].y).toFixed(1);
  }
  return d;
});

const areaPath = computed(() => {
  const pts = props.points;
  if (!pts.length) return '';
  const baseY = (PAD.t + innerH.value).toFixed(1);
  const last = pts[pts.length - 1];
  return linePath.value + 'L' + sx(last.x).toFixed(1) + ',' + baseY + 'L' + sx(pts[0].x).toFixed(1) + ',' + baseY + 'Z';
});

const gridLines = computed(() => [0, 25, 50, 75, 100].map((v) => ({ v, y: sy(v) })));

const marks = computed(() => {
  const pts = props.points;
  if (!pts.length) return [];
  let hi = pts[0];
  let lo = pts[0];
  for (const p of pts) {
    if (p.y > hi.y) hi = p;
    if (p.y < lo.y) lo = p;
  }
  const out = [{ key: 'max', x: sx(hi.x), y: sy(hi.y), text: String(Math.round(hi.y)), yText: sy(hi.y) - 6 }];
  if (lo !== hi) out.push({ key: 'min', x: sx(lo.x), y: sy(lo.y), text: String(Math.round(lo.y)), yText: sy(lo.y) + 12 });
  return out;
});
</script>

<template>
  <svg class="vr-line" :viewBox="viewBox" role="img" aria-label="数值变化曲线">
    <line
      v-for="g in gridLines"
      :key="'g' + g.v"
      x1="0"
      :x2="width"
      :y1="g.y"
      :y2="g.y"
      class="line-grid"
    />
    <template v-if="hasData">
      <path :d="areaPath" :fill="color" opacity="0.14" />
      <path
        :d="linePath"
        fill="none"
        :stroke="color"
        stroke-width="2"
        stroke-linejoin="round"
        stroke-linecap="round"
      />
      <g v-for="m in marks" :key="m.key">
        <circle :cx="m.x" :cy="m.y" r="3" :fill="color" />
        <text :x="m.x" :y="m.yText" class="line-mark" text-anchor="middle">{{ m.text }}</text>
      </g>
    </template>
  </svg>
</template>

<style scoped>
.vr-line {
  display: block;
  width: 100%;
  height: auto;
}

.line-grid {
  stroke: rgba(124, 58, 237, 0.22);
  stroke-width: 1;
}

.line-mark {
  fill: #cbb8f5;
  font-size: 10px;
  font-family: inherit;
  font-variant-numeric: tabular-nums;
}
</style>
