import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// 深色模式的可读性守卫：直接解析两套 CSS 的变量块，断言关键前景/背景色对
// 满足 WCAG AA。改了夜间配色却忘了配对时，这里会先失败。
const src = join(dirname(fileURLToPath(import.meta.url)), '..', 'src')
const stylesCss = readFileSync(join(src, 'styles.css'), 'utf8')
const nightCss = readFileSync(join(src, 'night.css'), 'utf8')

function blocksOf(source, selector) {
  const bodies = []
  let from = 0
  for (;;) {
    const at = source.indexOf(selector, from)
    if (at === -1) break
    const open = source.indexOf('{', at)
    const close = source.indexOf('}', open)
    if (open === -1 || close === -1) break
    bodies.push(source.slice(open + 1, close))
    from = close + 1
  }
  return bodies
}

// 合并同一选择器出现的所有块（pixel.css 的变量分在两段里声明）。
function variablesOf(source, selector) {
  const vars = {}
  for (const body of blocksOf(source, selector)) {
    for (const match of body.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) vars[match[1]] = match[2].trim()
  }
  return vars
}

function rgbOf(hex) {
  const value = hex.replace('#', '')
  const full = value.length === 3 ? value.split('').map((char) => char + char).join('') : value
  return [0, 2, 4].map((index) => parseInt(full.slice(index, index + 2), 16) / 255)
}

function channel(value) {
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
}

function luminance(hex) {
  const [r, g, b] = rgbOf(hex).map(channel)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const AA = 4.5
const night = variablesOf(nightCss, "html[data-mode='night']")
const pixelNight = variablesOf(nightCss, "html[data-theme='pixel'][data-mode='night']")
const day = variablesOf(stylesCss, ':root')

test('夜间语义色对在深色纸面与面板上都达到 AA', () => {
  assert.ok(night.ink && night.muted && night.paper, '夜间变量块缺少 --ink/--muted/--paper')
  const pairs = [
    [night.ink, night.paper, '正文 / 纸面'],
    [night.ink, '#19211e', '正文 / 卡片面板'],
    [night.muted, night.paper, '次要文字 / 纸面'],
    [night.muted, '#19211e', '次要文字 / 卡片面板'],
    [night.green, night['green-soft'], '强调绿 / 浅绿底'],
    [night.yellow, night['yellow-soft'], '强调黄 / 浅黄底'],
    [night.red, night['red-soft'], '强调红 / 浅红底'],
    [night.blue, night['blue-soft'], '强调蓝 / 浅蓝底'],
  ]
  for (const [foreground, background, label] of pairs) {
    const ratio = contrast(foreground, background)
    assert.ok(ratio >= AA, `${label} 只有 ${ratio.toFixed(2)}:1，低于 ${AA}:1`)
  }
})

test('夜间 accent 底上的文字改为深色后足够清晰', () => {
  for (const [name, background] of [['--blue', night.blue], ['--green', night.green], ['--red', night.red]]) {
    const ratio = contrast('#101614', background)
    assert.ok(ratio >= AA, `${name} 上的深色文字只有 ${ratio.toFixed(2)}:1`)
  }
  // 品牌方块：固定深底 + 浅字（night.css 的 .brand-mark）
  assert.ok(contrast('#f2f6f4', '#2f3a36') >= AA)
  // 顶栏次级文字与图标
  assert.ok(contrast('#b9c6c0', '#121916') >= AA)
  // 成功/提示类文字压在深绿面上
  assert.ok(contrast('#8fd7b0', '#16261e') >= AA)
})

test('像素风夜间：奶油字在压深后的主色与纸面上仍可读', () => {
  assert.ok(pixelNight.ink && pixelNight.paper && pixelNight['px-primary'], '像素风夜间变量块不完整')
  assert.ok(contrast(pixelNight.ink, pixelNight.paper) >= AA, '奶油字压在暗木纸面上')
  assert.ok(contrast(pixelNight.muted, pixelNight.paper) >= AA, '次要木色字压在暗木纸面上')
  // KanbanNiang 的发送按钮是 var(--ink) 压 var(--px-primary)
  const ratio = contrast(pixelNight.ink, pixelNight['px-primary'])
  assert.ok(ratio >= AA, `主色按钮上的奶油字只有 ${ratio.toFixed(2)}:1`)
})

test('日间语义色对没有被夜间改动带坏', () => {
  assert.ok(contrast(day.ink, day.paper) >= AA)
  assert.ok(contrast(day.muted, day.paper) >= AA)
})

test('原生控件跟随昼夜切换 color-scheme', () => {
  assert.match(stylesCss, /color-scheme:\s*light/)
  assert.match(nightCss, /html\[data-mode='night'\]\s*\{[^}]*color-scheme:\s*dark/)
})

test('night.css 覆盖了已知会"深字压深底"的选择器', () => {
  // 这些在 styles.css 里是写死的日间深色文字，必须各有夜间覆盖。
  const selectors = [
    '.brand-mark',
    '.nav-more-menu a',
    '.mobile-panel a',
    '.icon-button',
    '.group-chat-chip',
    '.notification-list li.unread button',
    '.facet-chip',
    '.hall-view-switch',
    '.disclosure-row',
    '.my-credential-list a',
    '.atmosphere-line',
    '.form-stack label',
    '.tutorial-card',
  ]
  for (const selector of selectors) {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    assert.match(nightCss, new RegExp(escaped), `night.css 缺少 ${selector} 的夜间覆盖`)
  }
})
