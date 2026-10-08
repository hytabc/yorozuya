<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { errorMessage } from '../api'
import { draftOperation } from './drafts'
import { ownedClient } from './client'
import { clone, createHistory, editVoxels, validateVoxelData } from './engine'
import VoxelScene from './VoxelScene.vue'

const props = defineProps({ source: Object, catalog: Object, ownerId: Number })
const emit = defineEmits(['saved', 'error'])
const { client, ownerValid, dispose:disposeClient } = ownedClient()
const data = ref({ gridSize: 16, mount: 'floor', palette: [{ key: 'wood', label: '木材', color: '#b58b63', editable: true }, { key: 'fabric', label: '布艺', color: '#e4d9c6', editable: true }, { key: 'accent', label: '装饰', color: '#879b87', editable: true }], voxels: [[7, 7, 0, 0]] })
const name = ref('新家具'), category = ref('deco'), style = ref('自制'), ident = ref(crypto.randomUUID()), revision = ref(0)
const tool = ref('add'), color = ref(0), mirrors = ref([]), sliceAxis = ref(2), slice = ref(0), sliced = ref(true)
const point = ref([7,7,0]), saving = ref(false), dirty = ref(false), restoreDraft = ref(null), history = createHistory(20), message = ref('')
const currentSlot = computed(() => data.value.palette[color.value])
const toolsOpen=ref(true),colorsOpen=ref(true)
let timer, queue = Promise.resolve(), disposed = false
function snapshot() { return clone({ id: ident.value, revision: revision.value, name: name.value, category: category.value, style: style.value, data: data.value }) }
function changed() {
  dirty.value = true; clearTimeout(timer)
  timer = setTimeout(() => {
    const state = snapshot()
    queue = queue.catch(() => {}).then(() => {
      if (!ownerValid() || disposed) return
      return draftOperation(props.ownerId, 'workshop', 'put', state)
    })
    queue.catch(() => emit('error','工坊本地草稿保存失败'))
  }, 400)
}
function hydrate(s) {
  ident.value = s.id; revision.value = s.revision; name.value = s.name; category.value = s.category; style.value = s.style; data.value = clone(s.data)
  history.clear(); color.value = 0; slice.value = 0; dirty.value = false
}
function loadSource(source) {
  if (!source) return
  const f = source.furniture, own = !source.fork && f?.creatorId === props.ownerId && !f.deleted
  hydrate({ id: own ? f.id : crypto.randomUUID(), revision: own ? f.revision : 0, name: own ? f.name : `${f?.name || '家具'} · 我的版本`, category: f?.category || 'deco', style: f?.style || '自制', data: source.data })
  sliced.value = false
  if (!own) changed()
}
watch(() => props.source, loadSource)
function historyChange(action) { const next = history[action](data.value); if (next) { data.value = next; changed() } }
function paint(p, record = false) { if (record) history.push(data.value); data.value = editVoxels(data.value, p, tool.value === 'camera' ? 'add' : tool.value, color.value, mirrors.value); changed() }
function resizeGrid(event) {
  const n = Number(event.target.value)
  if (data.value.voxels.some((p) => p.slice(0,3).some((a) => a >= n))) { emit('error','已有体素超出新网格，请先删除或选择更大的尺寸'); event.target.value = data.value.gridSize; return }
  history.push(data.value); data.value.gridSize = n; slice.value = Math.min(slice.value,n-1); changed()
}
function fresh() {
  if (dirty.value && !window.confirm('当前家具草稿尚未保存到云端，确认新建？')) return
  hydrate({id:crypto.randomUUID(),revision:0,name:'新家具',category:'deco',style:'自制',data:{gridSize:16,mount:'floor',palette:clone(data.value.palette),voxels:[[7,7,0,0]]}})
  changed()
}
async function save() {
  if (saving.value) return
  try {
    if (!ownerValid()) throw new Error('登录身份已变更，请重新进入房屋')
    validateVoxelData(data.value)
    saving.value = true
    const snap = snapshot()
    const { data: furniture } = await client.put(`/house/furniture/${ident.value}`, { revision: revision.value, name: name.value, category: category.value, style: style.value, data: snap.data })
    if (!ownerValid() || disposed) return
    revision.value = furniture.revision
    const unchanged = JSON.stringify({ ...snap, revision: revision.value }) === JSON.stringify(snapshot())
    if (unchanged) { dirty.value = false; clearTimeout(timer); await queue.catch(() => {}); await draftOperation(props.ownerId,'workshop','delete') }
    else changed()
    message.value = '家具已保存到账号，可放进房屋或发布到家具库'; emit('saved', furniture)
  } catch (e) { emit('error', errorMessage(e, '家具保存失败，草稿仍保留')) } finally { saving.value = false }
}
function exportJson() {
  const blob = new Blob([JSON.stringify({ schemaVersion:1, name:name.value, category:category.value, style:style.value, data:data.value })],{type:'application/json'})
  const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href=url; a.download='家具.json'; a.click(); URL.revokeObjectURL(url)
}
async function importJson(event) {
  const file = event.target.files[0]
  if (!file) return
  try {
    if (file.size>8*1024*1024) throw new Error('文件超过8 MiB')
    const model = JSON.parse(await file.text()); if(model.schemaVersion!==1)throw new Error('家具文件版本不受支持');validateVoxelData(model.data)
    if (dirty.value && !window.confirm('导入会替换当前工坊草稿，确认继续？')) return
    hydrate({id:crypto.randomUUID(),revision:0,name:String(model.name || '导入家具').slice(0,64),category:props.catalog.categories.some((c)=>c.id===model.category)?model.category:'deco',style:String(model.style || '自制').slice(0,32),data:model.data}); changed()
  } catch (e) { emit('error',e.message) } finally { event.target.value='' }
}
function newSlot() {
  if (data.value.palette.length >= 256) return
  history.push(data.value); data.value.palette.push({key:`part${data.value.palette.length}`,label:'新部位',color:'#c4a3a5',editable:true}); color.value=data.value.palette.length-1; changed()
}
function applyPalette(palette) {
  history.push(data.value)
  data.value.palette = data.value.palette.map((s)=>({...s,color:s.editable && palette.colors[s.key] || s.color})); changed()
}
onMounted(async()=>{
  if (props.source) loadSource(props.source)
  try { restoreDraft.value=await draftOperation(props.ownerId,'workshop','get') } catch (e) { emit('error',e.message) }
})
onBeforeUnmount(()=>{
  clearTimeout(timer)
  if (dirty.value && ownerValid()) draftOperation(props.ownerId,'workshop','put',snapshot()).catch(()=>{})
  disposed=true
  disposeClient()
})
</script>

<template>
  <div class="workshop">
    <div v-if="restoreDraft" class="house-notice">发现本地工坊草稿：{{ restoreDraft.name }}<button @click="hydrate(restoreDraft);restoreDraft=null;changed()">恢复草稿</button><button @click="restoreDraft=null">暂不恢复</button></div>
    <div class="workshop-tools">
      <input v-model="name" maxlength="64" aria-label="家具名称" @input="changed" />
      <select :value="data.gridSize" aria-label="网格尺寸" @change="resizeGrid"><option v-for="n in [16,32,64]" :key="n" :value="n">{{ n }}³ 网格</option></select>
      <select v-model="category" aria-label="家具分类" @change="changed"><option v-for="c in catalog?.categories" :key="c.id" :value="c.id">{{ c.label }}</option></select>
      <select v-model="style" aria-label="家具风格" @change="changed"><option v-for="s in ['自制','原木','奶油','北欧','复古','现代']" :key="s">{{ s }}</option></select>
      <button class="button secondary small" @click="fresh">新建</button><button class="button small" :disabled="saving" @click="save">{{ saving?'保存中…':'保存家具' }}</button>
    </div>
    <div class="workshop-layout">
      <aside class="workshop-panel" :class="{collapsed:!toolsOpen}">
        <button class="mobile-panel-toggle" :aria-expanded="toolsOpen" @click="toolsOpen=!toolsOpen">{{ toolsOpen?'收起绘制工具':'展开绘制工具' }}</button>
        <h3>绘制工具</h3>
        <div class="tool-buttons"><button v-for="[id,label] in [['add','放置'],['delete','删除'],['paint','着色'],['camera','视角']]" :key="id" :aria-pressed="tool===id" :class="{active:tool===id}" @click="tool=id">{{ label }}</button></div>
        <p class="muted">点击或滑动画布绘制；内部结构可用切片编辑。</p>
        <label>摆放方式<select v-model="data.mount" @change="changed"><option value="floor">落地</option><option value="surface">桌面</option><option value="wall">墙面</option><option value="ceiling">顶面</option></select></label>
        <h3>镜像绘制</h3><div class="tool-buttons"><label v-for="[axis,label] in [[0,'X'],[1,'Y'],[2,'Z']]" :key="axis"><input v-model="mirrors" type="checkbox" :value="axis" />{{ label }}</label></div>
        <label><input v-model="sliced" type="checkbox" />启用切片</label>
        <select v-model.number="sliceAxis" aria-label="切片方向"><option :value="0">X 横向</option><option :value="1">Y 纵向</option><option :value="2">Z 高度</option></select>
        <label>第 {{ slice+1 }} 层<input v-model.number="slice" type="range" :max="data.gridSize-1" min="0" /></label>
        <div class="tool-buttons"><button @click="slice=Math.max(0,slice-1)">上一层</button><button @click="slice=Math.min(data.gridSize-1,slice+1)">下一层</button></div>
        <h3>精确坐标</h3><div class="voxel-coords"><label v-for="(axis,i) in ['X','Y','Z']" :key="axis">{{ axis }}<input v-model.number="point[i]" type="number" min="0" :max="data.gridSize-1" /></label></div>
        <button class="button secondary small" @click="paint(point,true)">在此坐标执行工具</button>
        <div class="tool-buttons"><button @click="historyChange('undo')">撤销</button><button @click="historyChange('redo')">重做</button></div>
        <h3>数据</h3><button class="button secondary small" @click="exportJson">导出 JSON</button><label class="import-label">导入 JSON<input type="file" accept=".json,application/json" @change="importJson" /></label>
      </aside>
      <VoxelScene :data="data" :tool="tool" :slice-axis="sliceAxis" :slice="sliced?slice:-1" @voxel="paint($event)" @stroke-start="history.push(data)" @error="emit('error',$event)" />
      <aside class="workshop-panel" :class="{collapsed:!colorsOpen}">
        <button class="mobile-panel-toggle" :aria-expanded="colorsOpen" @click="colorsOpen=!colorsOpen">{{ colorsOpen?'收起材质与颜色':'展开材质与颜色' }}</button>
        <h3>材质与颜色</h3>
        <button v-for="(s,i) in data.palette" :key="s.key" class="slot-button" :class="{active:color===i}" @click="color=i"><span :style="{background:s.color}" />{{ s.label }}</button>
        <label v-if="currentSlot">部位名称<input v-model="currentSlot.label" maxlength="32" @input="changed" /></label>
        <label v-if="currentSlot">体素颜色<input v-model="currentSlot.color" type="color" @input="changed" /></label>
        <button class="button secondary small" @click="newSlot">新增部位</button>
        <h3>搭配色板</h3>
        <button v-for="p in catalog?.palettes" :key="p.id" class="palette-button" @click="applyPalette(p)"><span><i v-for="k in ['wood','fabric','accent']" :key="k" :style="{background:p.colors[k]}" /></span>{{ p.name }}</button>
        <p class="muted">{{ data.voxels.length.toLocaleString() }} 个体素 · {{ dirty?'本地草稿':'已保存' }}</p><p v-if="message" role="status">{{ message }}</p>
      </aside>
    </div>
  </div>
</template>
<style scoped>
.workshop-tools{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}.workshop-tools input,.workshop-tools select,.workshop-panel input:not([type=checkbox]),.workshop-panel select{min-height:38px;max-width:100%;border:1px solid var(--line);border-radius:6px;padding:5px 8px;background:var(--paper);color:var(--ink)}.workshop-tools>input{flex:1;min-width:160px}.workshop-layout{display:grid;grid-template-columns:185px minmax(0,1fr) 185px;gap:16px}.workshop-panel{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:10px;font-size:12px}.workshop-panel h3{font-size:13px;margin:14px 0 0}.workshop-panel label{display:flex;gap:6px;flex-wrap:wrap;align-items:center}.workshop-panel p{font-size:11px;line-height:1.7;margin:0}.tool-buttons{display:flex;flex-wrap:wrap;gap:5px}.tool-buttons button{padding:8px;border:1px solid var(--line);border-radius:6px;background:var(--paper);color:var(--ink)}.active{border-color:var(--green)!important;background:var(--green-soft)!important}.voxel-coords{display:flex;gap:4px}.voxel-coords label{width:30%}.voxel-coords input{width:100%}.slot-button{display:flex;align-items:center;gap:8px;padding:8px;border:1px solid var(--line);border-radius:6px;background:var(--paper);color:var(--ink)}.slot-button span{width:18px;height:18px;border-radius:4px}.palette-button{display:flex;align-items:center;gap:8px;border:0;background:transparent;color:var(--ink);font-size:11px;text-align:left;padding:5px}.palette-button>span{display:flex}.palette-button i{width:13px;height:22px}.import-label{margin-top:8px}.import-label input{font-size:10px}@media(max-width:1050px){.workshop-layout{grid-template-columns:165px minmax(0,1fr)}.workshop-panel:last-child{grid-column:1/-1;display:grid;grid-template-columns:repeat(3,1fr)}}@media(max-width:760px){.workshop-layout{display:flex;flex-direction:column}.workshop-layout>.house-scene-wrap{order:-1}.workshop-panel{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.workshop-panel:last-child{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
