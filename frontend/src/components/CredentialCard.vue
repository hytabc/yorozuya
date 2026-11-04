<script setup>
import { computed } from 'vue'
import { Download, ShieldAlert } from '@lucide/vue'
import { credentialMeta, formatIssued } from '../credential'

const props = defineProps({
  credential: { type: Object, required: true },
  compact: Boolean,
  downloadable: { type: Boolean, default: true },
})

const meta = computed(() => credentialMeta(props.credential))
const revoked = computed(() => Boolean(props.credential.revoked))
const issued = computed(() => formatIssued(props.credential))

function wrap(ctx, text, maxWidth) {
  const lines = []
  let line = ''
  for (const char of String(text || '')) {
    const next = line + char
    if (ctx.measureText(next).width > maxWidth && line) {
      lines.push(line)
      line = char
    } else {
      line = next
    }
  }
  if (line) lines.push(line)
  return lines
}

// 前端 Canvas 2D 绘制 1200×1600 PNG：不落盘、不依赖服务端图片生成，也不渲染任何用户上传素材。
function download() {
  const canvas = document.createElement('canvas')
  canvas.width = 1200
  canvas.height = 1600
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.fillStyle = '#f7f5ef'
  ctx.fillRect(0, 0, 1200, 1600)
  ctx.strokeStyle = '#2c5c47'
  ctx.lineWidth = 5
  ctx.strokeRect(46, 46, 1108, 1508)

  ctx.fillStyle = '#2c5c47'
  ctx.font = '600 26px Georgia, serif'
  ctx.fillText('YOROZUYA REQUEST CREDENTIAL', 96, 140)

  ctx.fillStyle = '#1d2621'
  ctx.font = '700 52px Georgia, "Songti SC", serif'
  const titleLines = wrap(ctx, props.credential.title, 980).slice(0, 3)
  titleLines.forEach((line, index) => ctx.fillText(line, 96, 230 + index * 72))

  let y = 230 + titleLines.length * 72 + 50
  ctx.font = '400 26px "PingFang SC", "Songti SC", sans-serif'
  for (const row of meta.value) {
    ctx.fillStyle = '#7a837e'
    ctx.fillText(row.label, 96, y)
    ctx.fillStyle = '#1d2621'
    const values = wrap(ctx, row.value, 700).slice(0, 2)
    values.forEach((line, index) => ctx.fillText(line, 340, y + index * 34))
    y += 34 * Math.max(1, values.length) + 26
  }

  y += 20
  ctx.strokeStyle = '#d8ddd8'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(96, y)
  ctx.lineTo(1104, y)
  ctx.stroke()

  ctx.fillStyle = '#2c5c47'
  ctx.font = '700 34px Georgia, serif'
  ctx.fillText(props.credential.serial || '', 96, y + 76)
  if (revoked.value) {
    ctx.fillStyle = '#b23a3a'
    ctx.font = '700 30px "PingFang SC", sans-serif'
    ctx.fillText('此凭证已失效（被撤销）', 96, y + 126)
  }

  ctx.fillStyle = '#6d7772'
  ctx.font = '400 22px "PingFang SC", "Songti SC", sans-serif'
  const note = wrap(ctx, props.credential.verify_note, 980)
  note.forEach((line, index) => ctx.fillText(line, 96, 1330 + index * 34))
  ctx.fillStyle = '#9aa39e'
  ctx.fillText(`签发于 ${issued.value || props.credential.issued_at || ''}`, 96, 1440)

  canvas.toBlob((blob) => {
    if (!blob) return
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${props.credential.serial || 'credential'}.png`
    link.click()
    URL.revokeObjectURL(url)
  }, 'image/png')
}
</script>

<template>
  <article class="credential-card" :class="{ compact, revoked }">
    <header class="credential-head">
      <span class="eyebrow">YOROZUYA CREDENTIAL</span>
      <h3>{{ credential.title }}</h3>
      <div class="task-tags">
        <span v-if="credential.category" class="category-tag">{{ credential.category }}</span>
        <span v-for="skill in credential.skills" :key="skill" class="facet-chip static">{{ skill }}</span>
        <span v-for="platform in credential.platforms" :key="platform" class="facet-chip static">{{ platform }}</span>
      </div>
    </header>
    <dl class="credential-meta">
      <div v-for="row in meta" :key="row.label"><dt>{{ row.label }}</dt><dd>{{ row.value }}</dd></div>
    </dl>
    <p class="credential-serial">{{ credential.serial }}</p>
    <p v-if="revoked" class="notice error-notice"><ShieldAlert :size="15" />该凭证已被撤销，仅保留历史记录，不再作为有效履历展示。</p>
    <p class="field-hint">{{ credential.verify_note }}</p>
    <div v-if="!compact" class="credential-actions">
      <button v-if="downloadable && !revoked" type="button" class="button small" @click="download"><Download :size="14" />下载 PNG</button>
      <RouterLink v-if="credential.taker_id" class="text-link" :to="`/creators/${credential.taker_id}`">查看接单人作品集</RouterLink>
    </div>
  </article>
</template>
