<script setup>
/**
 * 750×1334 分享卡片：Canvas 2D 绘制 + PNG 下载。
 */
import { ref, onMounted, watch, nextTick } from 'vue';
import { clamp, shorten } from '../utils/format.js';

const props = defineProps({
  ending: { type: Object, default: () => ({}) },
  stats: { type: Object, default: () => ({}) },
  radar: { type: Array, default: () => [50, 50, 50, 50, 50, 50] },
  labels: { type: Array, default: () => ['社交', '技能', '声望', '情感', '心态', '投入'] },
  seed: { type: [String, Number], default: '' },
  summary: { type: String, default: '' },
});

const W = 750;
const H = 1334;
const FONT = '"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", system-ui, sans-serif';

const canvasRef = ref(null);
const downloading = ref(false);

function hexToRgba(hex, alpha) {
  const s = String(hex || '').replace('#', '');
  if (s.length !== 6) return hex || '#7c3aed';
  const n = parseInt(s, 16);
  if (Number.isNaN(n)) return '#7c3aed';
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  if (typeof ctx.roundRect === 'function') {
    ctx.roundRect(x, y, w, h, r);
    return;
  }
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
  const chars = String(text == null ? '' : text).split('');
  let line = '';
  const lines = [];
  for (const ch of chars) {
    const test = line + ch;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = ch;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  const shown = lines.slice(0, 4);
  shown.forEach((l, i) => ctx.fillText(l, x, y + i * lineHeight));
  return y + (shown.length - 1) * lineHeight;
}

function drawRadar(ctx, cx, cy, r, values, labels, accent) {
  const n = 6;
  const angle = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / n;

  ctx.strokeStyle = 'rgba(124,58,237,0.35)';
  ctx.lineWidth = 2;
  for (let level = 1; level <= 4; level += 1) {
    ctx.beginPath();
    for (let i = 0; i < n; i += 1) {
      const rr = (r * level) / 4;
      const x = cx + Math.cos(angle(i)) * rr;
      const y = cy + Math.sin(angle(i)) * rr;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.stroke();
  }

  ctx.beginPath();
  for (let i = 0; i < n; i += 1) {
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(angle(i)) * r, cy + Math.sin(angle(i)) * r);
  }
  ctx.stroke();

  ctx.beginPath();
  for (let i = 0; i < n; i += 1) {
    const v = clamp(values[i] || 0, 0, 100) / 100;
    const x = cx + Math.cos(angle(i)) * r * v;
    const y = cy + Math.sin(angle(i)) * r * v;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.fillStyle = 'rgba(6,182,212,0.32)';
  ctx.fill();
  ctx.strokeStyle = accent;
  ctx.lineWidth = 3;
  ctx.stroke();

  ctx.fillStyle = '#8b7fa8';
  ctx.font = `22px ${FONT}`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (let i = 0; i < n; i += 1) {
    const x = cx + Math.cos(angle(i)) * (r + 34);
    const y = cy + Math.sin(angle(i)) * (r + 34);
    ctx.fillText(labels[i] || '', x, y);
  }
  ctx.textBaseline = 'alphabetic';
}

function draw() {
  const canvas = canvasRef.value;
  if (!canvas || typeof canvas.getContext !== 'function') return;

  const accent = (props.ending && props.ending.color) || '#7c3aed';
  const title = (props.ending && props.ending.title) || '普通玩家';
  const desc = (props.ending && props.ending.desc) || '';
  const seed = props.seed === undefined || props.seed === null ? '' : String(props.seed);
  const stats = props.stats || {};

  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // 背景
  const bg = ctx.createLinearGradient(0, 0, W, H);
  bg.addColorStop(0, '#0F0A1E');
  bg.addColorStop(1, '#1A1033');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  // 顶部光晕
  const glow = ctx.createRadialGradient(W / 2, 200, 0, W / 2, 200, 540);
  glow.addColorStop(0, hexToRgba(accent, 0.42));
  glow.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, W, 700);

  // 外框
  ctx.strokeStyle = hexToRgba(accent, 0.45);
  ctx.lineWidth = 3;
  roundRect(ctx, 26, 26, W - 52, H - 52, 40);
  ctx.stroke();

  ctx.textAlign = 'center';
  ctx.fillStyle = '#8b7fa8';
  ctx.font = `600 24px ${FONT}`;
  ctx.fillText('VRChat 玩家历程模拟器', W / 2, 128);

  ctx.fillStyle = accent;
  ctx.font = `bold 78px ${FONT}`;
  wrapText(ctx, title, W / 2, 250, W - 160, 92);

  if (desc) {
    ctx.fillStyle = '#b9aede';
    ctx.font = `28px ${FONT}`;
    wrapText(ctx, desc, W / 2, 372, W - 180, 44);
  }

  // 数值行
  const items = [
    { label: '总时长', value: `${Math.round(stats.hours || 0)}h` },
    { label: '好友', value: String(stats.friends || 0) },
    { label: '砂糖次数', value: String(stats.sugarCount || 0) },
  ];
  const colW = (W - 160) / items.length;
  items.forEach((it, i) => {
    const cx = 80 + colW * i + colW / 2;
    ctx.fillStyle = '#e9e4f5';
    ctx.font = `bold 44px ${FONT}`;
    ctx.fillText(it.value, cx, 520);
    ctx.fillStyle = '#8b7fa8';
    ctx.font = `22px ${FONT}`;
    ctx.fillText(it.label, cx, 558);
  });

  // 迷你雷达图
  drawRadar(ctx, W / 2, 800, 150, props.radar || [], props.labels || [], accent);

  // summary 第一句
  if (props.summary) {
    ctx.fillStyle = '#cfc6e8';
    ctx.font = `28px ${FONT}`;
    wrapText(ctx, `「${shorten(props.summary, 46)}」`, W / 2, 1060, W - 170, 46);
  }

  // 分隔线
  ctx.strokeStyle = hexToRgba(accent, 0.28);
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(110, 1180);
  ctx.lineTo(W - 110, 1180);
  ctx.stroke();

  // 底部种子
  ctx.fillStyle = '#8b7fa8';
  ctx.font = `24px ${FONT}`;
  ctx.fillText(`种子 ${seed}`, W / 2, 1232);
  ctx.fillStyle = hexToRgba(accent, 0.85);
  ctx.font = `22px ${FONT}`;
  ctx.fillText('vrclife · 虚拟人生', W / 2, 1276);
}

function download() {
  const canvas = canvasRef.value;
  if (!canvas || typeof canvas.toBlob !== 'function') return;
  downloading.value = true;
  canvas.toBlob((blob) => {
    downloading.value = false;
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const seed = props.seed === undefined ? '' : String(props.seed);
    a.download = `vrclife-${seed || 'share'}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 3000);
  }, 'image/png');
}

onMounted(() => {
  nextTick(draw);
});

watch(
  () => [
    props.ending && props.ending.id,
    props.ending && props.ending.title,
    props.summary,
    props.seed,
    (props.radar || []).join(','),
  ],
  () => { nextTick(draw); },
);
</script>

<template>
  <div class="vr-share">
    <canvas ref="canvasRef" class="share-canvas"></canvas>
    <img v-if="false" class="share-preview" alt="" />
    <button type="button" class="share-btn" :disabled="downloading" @click="download">
      {{ downloading ? '生成中…' : '下载图片' }}
    </button>
  </div>
</template>

<style scoped>
.vr-share {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  width: 100%;
}

.share-canvas {
  width: 100%;
  max-width: 340px;
  height: auto;
  display: block;
  border-radius: 16px;
  border: 1px solid rgba(124, 58, 237, 0.45);
  box-shadow: 0 8px 32px rgba(124, 58, 237, 0.25);
}

/* 若将来加入预览 img，自适应容器宽度 */
.share-preview {
  max-width: 100%;
  height: auto;
  display: block;
}

.share-btn {
  padding: 11px 26px;
  border-radius: 10px;
  border: 1px solid rgba(6, 182, 212, 0.5);
  background: rgba(6, 182, 212, 0.14);
  color: #a5f3fc;
  font-size: 15px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.18s ease;
}

.share-btn:hover:not(:disabled) {
  background: rgba(6, 182, 212, 0.28);
}

.share-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

/* =============== 窄屏（≤900px） =============== */
@media (max-width: 900px) {
  .share-canvas {
    max-width: 100%;
  }

  .share-btn {
    width: 100%;
    min-height: 46px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .share-btn {
    transition: none;
  }
}
</style>