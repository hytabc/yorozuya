<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Check, Copy, Download, Share2, X } from '@lucide/vue'
import QRCode from 'qrcode'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'
import { POSTER_FORMATS, posterModel } from '../sharePoster'

const props = defineProps({ task: { type: Object, required: true } })
const emit = defineEmits(['close'])
const auth = useAuthStore()
const toast = useToast()
const canvasRef = ref(null)
const format = ref('portrait')
const copied = ref(false)
const drawing = ref(false)
const model = computed(() => posterModel(props.task, url.value))
const formats = Object.values(POSTER_FORMATS)

const url = computed(() => {
  const ref = auth.user?.invite_code
  const suffix = ref ? `?ref=${encodeURIComponent(ref)}` : ''
  return `${window.location.origin}/share/task/${props.task.id}${suffix}`
})
const canNativeShare = computed(() => typeof navigator !== 'undefined' && Boolean(navigator.share))

const C = {
  paper: '#f6f1e7',
  paper2: '#fffdf7',
  ink: '#1e2a24',
  muted: '#6f7b74',
  green: '#2f6b4f',
  greenSoft: '#e6eee8',
  red: '#b5492e',
  redSoft: '#f6e4df',
  gold: '#a8791b',
  goldSoft: '#f7efd9',
  line: '#d8d0c0',
  white: '#fffdf7',
}
const BODY_FONT = '"Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
const TITLE_FONT = 'Georgia, "Songti SC", serif'

let drawToken = 0
let logoPromise = null

function loadLogo() {
  if (!logoPromise) {
    logoPromise = new Promise((resolve) => {
      const image = new Image()
      image.onload = () => resolve(image)
      image.onerror = () => resolve(null)
      image.src = '/brand/logo-horizontal.png'
    })
  }
  return logoPromise
}

function roundRect(ctx, x, y, width, height, radius) {
  ctx.beginPath()
  if (typeof ctx.roundRect === 'function') {
    ctx.roundRect(x, y, width, height, radius)
    return
  }
  ctx.moveTo(x + radius, y)
  ctx.arcTo(x + width, y, x + width, y + height, radius)
  ctx.arcTo(x + width, y + height, x, y + height, radius)
  ctx.arcTo(x, y + height, x, y, radius)
  ctx.arcTo(x, y, x + width, y, radius)
  ctx.closePath()
}

function wrapLines(ctx, text, maxWidth, maxLines) {
  const source = String(text || '')
  if (!source) return []
  const lines = []
  let line = ''
  for (const char of source) {
    const next = line + char
    if (ctx.measureText(next).width > maxWidth && line) {
      lines.push(line)
      line = char
      if (lines.length === maxLines) break
    } else {
      line = next
    }
  }
  if (lines.length < maxLines && line) lines.push(line)
  if (lines.length === maxLines) {
    const consumed = lines.join('').length
    if (consumed < source.length) {
      let last = lines[lines.length - 1]
      while (last && ctx.measureText(`${last}…`).width > maxWidth) last = last.slice(0, -1)
      lines[lines.length - 1] = `${last}…`
    }
  }
  return lines
}

function statusColors(modelValue) {
  if (modelValue.status === '已完成') return { bg: C.greenSoft, fg: C.green }
  if (modelValue.status === '已取消' || modelValue.status === '已过期') return { bg: C.redSoft, fg: C.red }
  if (modelValue.status === '待确认' || modelValue.status === '取消确认中') return { bg: C.goldSoft, fg: C.gold }
  return { bg: C.greenSoft, fg: C.green }
}

function drawChip(ctx, x, y, text, { bg, fg, size = 25, height = 44, padX = 16 }) {
  ctx.font = `600 ${size}px ${BODY_FONT}`
  const width = Math.ceil(ctx.measureText(text).width) + padX * 2
  ctx.fillStyle = bg
  roundRect(ctx, x, y, width, height, height / 2)
  ctx.fill()
  ctx.fillStyle = fg
  ctx.textBaseline = 'middle'
  ctx.fillText(text, x + padX, y + height / 2 + 1)
  ctx.textBaseline = 'alphabetic'
  return width
}

function drawLabelValue(ctx, label, value, x, y, maxWidth) {
  ctx.fillStyle = C.muted
  ctx.font = `22px ${BODY_FONT}`
  ctx.fillText(label, x, y)
  ctx.fillStyle = C.ink
  ctx.font = `600 29px ${BODY_FONT}`
  ctx.fillText(value, x, y + 36, maxWidth)
}

async function makeQr(target, size) {
  const canvas = document.createElement('canvas')
  await QRCode.toCanvas(canvas, target, {
    width: size,
    margin: 1,
    color: { dark: C.ink, light: C.paper2 },
  })
  return canvas
}

async function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const spec = POSTER_FORMATS[format.value] || POSTER_FORMATS.portrait
  const token = ++drawToken
  drawing.value = true
  try {
    const [logo, qrSize] = [await loadLogo(), spec.key === 'story' ? 340 : 280]
    const qr = await makeQr(url.value, qrSize)
    if (token !== drawToken) return
    const W = spec.width
    const H = spec.height
    canvas.width = W
    canvas.height = H
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const m = model.value

    ctx.fillStyle = C.paper
    ctx.fillRect(0, 0, W, H)
    ctx.fillStyle = C.green
    ctx.fillRect(0, 0, W, 18)
    ctx.strokeStyle = C.line
    ctx.lineWidth = 3
    roundRect(ctx, 36, 36, W - 72, H - 72, 28)
    ctx.stroke()

    // 轻微纸纹：只做视觉分层，不干扰阅读。
    for (let lineY = 190; lineY < H - 90; lineY += 64) {
      ctx.strokeStyle = 'rgba(47, 107, 79, .045)'
      ctx.beginPath()
      ctx.moveTo(72, lineY)
      ctx.lineTo(W - 72, lineY)
      ctx.stroke()
    }

    if (logo) {
      const height = 62
      const width = logo.width * (height / logo.height)
      ctx.drawImage(logo, 72, 74, width, height)
    } else {
      ctx.fillStyle = C.ink
      ctx.font = `bold 52px ${TITLE_FONT}`
      ctx.fillText('万事屋', 72, 126)
    }
    ctx.fillStyle = C.muted
    ctx.font = `23px ${BODY_FONT}`
    ctx.textAlign = 'right'
    ctx.fillText('VRChat 委托站', W - 76, 112)
    ctx.textAlign = 'left'

    // 红色印章
    ctx.fillStyle = C.red
    roundRect(ctx, W - 136, 144, 62, 62, 10)
    ctx.fill()
    ctx.fillStyle = C.white
    ctx.font = `bold 34px ${TITLE_FONT}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('万', W - 105, 177)
    ctx.textAlign = 'left'
    ctx.textBaseline = 'alphabetic'

    if (m.ended) {
      const colors = statusColors(m)
      ctx.save()
      ctx.translate(W - 190, 260)
      ctx.rotate(-Math.PI / 4)
      ctx.fillStyle = colors.fg
      ctx.fillRect(-220, -28, 440, 56)
      ctx.fillStyle = C.white
      ctx.font = `bold 27px ${BODY_FONT}`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(m.status, 0, 1)
      ctx.restore()
      ctx.textAlign = 'left'
      ctx.textBaseline = 'alphabetic'
    }

    let y = 300
    ctx.fillStyle = C.ink
    ctx.font = `bold 78px ${TITLE_FONT}`
    const titleLines = wrapLines(ctx, m.title, W - 150, 2)
    for (const line of titleLines) {
      ctx.fillText(line, 72, y)
      y += 92
    }

    y += 14
    let x = 72
    const chipBase = { size: 25, height: 44, padX: 17 }
    x += drawChip(ctx, x, y, m.category, { ...chipBase, bg: C.greenSoft, fg: C.green }) + 12
    if (m.scale) x += drawChip(ctx, x, y, m.scale, { ...chipBase, bg: '#f1ece0', fg: C.ink }) + 12
    const statusColor = statusColors(m)
    drawChip(ctx, x, y, m.status, { ...chipBase, bg: statusColor.bg, fg: statusColor.fg })

    y += 86
    ctx.fillStyle = C.ink
    ctx.font = `30px ${BODY_FONT}`
    for (const line of wrapLines(ctx, m.description, W - 150, 4)) {
      ctx.fillText(line, 72, y)
      y += 46
    }

    const pointsY = Math.round(H * (spec.key === 'story' ? 0.48 : 0.515))
    ctx.fillStyle = C.paper2
    roundRect(ctx, 72, pointsY, W - 144, 164, 18)
    ctx.fill()
    ctx.strokeStyle = C.line
    ctx.lineWidth = 2
    ctx.stroke()
    ctx.fillStyle = C.green
    roundRect(ctx, 72, pointsY, 10, 164, 6)
    ctx.fill()
    ctx.fillStyle = C.muted
    ctx.font = `24px ${BODY_FONT}`
    ctx.fillText('预计积分', 116, pointsY + 48)
    ctx.fillStyle = C.green
    ctx.font = `bold 48px ${TITLE_FONT}`
    ctx.fillText(m.points, 116, pointsY + 118, W - 250)

    const infoY = pointsY + 230
    const leftWidth = W - 72 - qrSize - 140
    // 发布者：首字徽章，不加载头像，避免签名 URL / 跨域绘制问题。
    ctx.fillStyle = C.greenSoft
    ctx.beginPath()
    ctx.arc(104, infoY + 8, 30, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = C.green
    ctx.font = `bold 28px ${BODY_FONT}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(m.publisherInitial, 104, infoY + 9)
    ctx.textAlign = 'left'
    ctx.textBaseline = 'alphabetic'
    drawLabelValue(ctx, '发布者', m.publisher, 150, infoY + 4, leftWidth - 80)

    drawLabelValue(ctx, '需要人数', m.required, 72, infoY + 100, leftWidth)
    drawLabelValue(ctx, '截止时间', m.deadline, 72, infoY + 196, leftWidth)
    drawLabelValue(ctx, '委托编号', `#${m.taskId}`, 72, infoY + 292, leftWidth)

    const qrX = W - 72 - qrSize
    const qrY = H - 72 - qrSize - 120
    ctx.fillStyle = C.paper2
    roundRect(ctx, qrX - 18, qrY - 18, qrSize + 36, qrSize + 36, 18)
    ctx.fill()
    ctx.strokeStyle = C.line
    ctx.lineWidth = 2
    ctx.stroke()
    ctx.drawImage(qr, qrX, qrY, qrSize, qrSize)
    ctx.fillStyle = C.ink
    ctx.font = `600 26px ${BODY_FONT}`
    ctx.textAlign = 'center'
    ctx.fillText(m.copy, qrX + qrSize / 2, qrY + qrSize + 52)
    ctx.fillStyle = C.muted
    ctx.font = `20px ${BODY_FONT}`
    ctx.fillText(m.shortLink, qrX + qrSize / 2, qrY + qrSize + 82)
    ctx.textAlign = 'left'

    ctx.strokeStyle = C.line
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(72, H - 132)
    ctx.lineTo(W - 72, H - 132)
    ctx.stroke()
    ctx.fillStyle = C.muted
    ctx.font = `22px ${BODY_FONT}`
    ctx.fillText('万事屋 · VRChat 委托站', 72, H - 88)
    ctx.textAlign = 'right'
    ctx.fillText(m.official ? '官方委托' : `#${m.taskId}`, W - 72, H - 88)
    ctx.textAlign = 'left'
  } finally {
    if (token === drawToken) drawing.value = false
  }
}

async function record(channel) {
  if (!auth.isLoggedIn) return
  try { await api.post(`/tasks/${props.task.id}/share`, { channel }) } catch { /* 记录失败不影响分享 */ }
}

async function copyLink() {
  try {
    await navigator.clipboard.writeText(url.value)
    copied.value = true
    toast.success('链接已复制')
    await record('copy')
    setTimeout(() => { copied.value = false }, 1600)
  } catch {
    toast.error('复制失败，请手动选择链接复制')
  }
}

async function canvasBlob() {
  const canvas = canvasRef.value
  if (!canvas) return null
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
}

async function download() {
  const blob = await canvasBlob()
  if (!blob) return
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = `万事屋委托-${props.task.id}-${format.value}.png`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  setTimeout(() => URL.revokeObjectURL(objectUrl), 3000)
  await record('poster')
}

async function nativeShare() {
  if (!canNativeShare.value) return
  try {
    const blob = await canvasBlob()
    if (blob) {
      const file = new File([blob], `万事屋委托-${props.task.id}.png`, { type: 'image/png' })
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title: props.task.title, text: `来自万事屋的委托：${props.task.title}` })
        await record('poster')
        return
      }
    }
    await navigator.share({ title: props.task.title, text: `来自万事屋的委托：${props.task.title}`, url: url.value })
    await record('native')
  } catch { /* 用户取消分享 */ }
}

function onKey(event) { if (event.key === 'Escape') emit('close') }

onMounted(async () => {
  document.body.classList.add('modal-open')
  window.addEventListener('keydown', onKey)
  try { await document.fonts?.ready } catch { /* 字体失败也能绘制 */ }
  await nextTick()
  await draw()
  if (auth.isLoggedIn) record('dialog')
})
onUnmounted(() => {
  document.body.classList.remove('modal-open')
  window.removeEventListener('keydown', onKey)
})
watch([format, () => props.task.id, url], () => nextTick(draw))
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="dialog share-dialog" role="dialog" aria-modal="true" aria-label="分享委托">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>
      <div class="dialog-heading"><span class="eyebrow">SHARE</span><h2>分享这份委托</h2><p>生成一张海报，二维码已嵌在右下角。</p></div>

      <div class="share-poster">
        <canvas ref="canvasRef" aria-label="委托分享海报" />
      </div>

      <div class="share-format" role="group" aria-label="海报比例">
        <button v-for="item in formats" :key="item.key" type="button" :class="{ active: format === item.key }" @click="format = item.key">{{ item.label }}</button>
      </div>

      <label class="share-link-field">链接
        <input :value="url" readonly aria-label="分享链接" @focus="$event.target.select()" />
      </label>

      <div class="dialog-actions share-actions">
        <button type="button" class="button" :disabled="drawing" @click="download"><Download :size="16" />保存海报</button>
        <button type="button" class="button secondary" @click="copyLink"><Check v-if="copied" :size="16" /><Copy v-else :size="16" />{{ copied ? '已复制' : '复制链接' }}</button>
        <button v-if="canNativeShare" type="button" class="button secondary" @click="nativeShare"><Share2 :size="16" />系统分享</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.share-dialog {
  display: grid;
  gap: 14px;
}

.share-poster {
  display: grid;
  place-items: center;
}

.share-poster canvas {
  width: 100%;
  max-width: 320px;
  max-height: 58vh;
  height: auto;
  display: block;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 10px 30px rgba(30, 42, 36, 0.12);
}

.share-format {
  display: flex;
  justify-content: center;
  gap: 8px;
}

.share-format button {
  min-height: 32px;
  padding: 0 16px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  background: var(--paper);
  font-size: 12px;
  cursor: pointer;
}

.share-format button.active {
  border-color: var(--green);
  color: var(--green);
  background: var(--green-soft);
  font-weight: 700;
}
</style>
