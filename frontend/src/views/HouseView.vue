<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import '../house/house.css'
import { House, Armchair, Hammer, Save, Share2, Undo2, Redo2, Trash2, Copy } from '@lucide/vue'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'
import LazyImage from '../components/LazyImage.vue'
import FurnitureBrowser from '../house/FurnitureBrowser.vue'
import FurnitureWorkshop from '../house/FurnitureWorkshop.vue'
import VoxelScene from '../house/VoxelScene.vue'
import HouseHelp from '../house/HouseHelp.vue'
import VisitBrowser from '../house/VisitBrowser.vue'
import { anchorPosition, blankRoom, clone, createHistory, placementError, recoloredData } from '../house/engine'
import { draftOperation } from '../house/drafts'
import { ownedClient } from '../house/client'
import { createSaveController } from '../house/saveController'

const auth = useAuthStore(), toast = useToast(), route = useRoute()
const catalog = ref(null), room = ref(blankRoom()), assets = ref({}), loading = ref(true), error = ref(''), tab = ref('room')
const ownerId = ref(null), textures = ref([]), selectedId = ref(null), pending = ref(null), detail = ref(null), workshopSource = ref(null)
const scene = ref(), browser = ref(), history = createHistory(), shareId = ref(null), draft = ref(null), ready = ref(false), savingTexture = ref(false)
const saveStatus = ref({ dirty:false,saving:false,error:'',conflict:false }), preview = ref(null), invalidPreview = ref(''), tool = ref('select')
const libraryOpen=ref(true),propertiesOpen=ref(true),workshopOpened=ref(false)
const roomVisible=ref(true)
const publishing=ref(false),publishedAt=ref(null),copied=ref(false)
let client, ownerValid = () => false, saver, disposed = false, disposeClient
const selected = computed(() => room.value.placements.find((p)=>p.id===selectedId.value))
const chosen = computed(() => selected.value ? assets.value[selected.value.versionId] : pending.value)
const chosenData = computed(() => chosen.value?.data)
const locked = computed(() => !ready.value || auth.user?.id !== ownerId.value || !auth.isLoggedIn)
const textureUrls = computed(() => Object.fromEntries([...(catalog.value?.textures || []),...textures.value].filter((t)=>t.url).map((t)=>[t.id,t.url])))
const shareUrl = computed(() => shareId.value ? `${location.origin}/house/visit/${shareId.value}` : '')
const displayRoom = computed(() => preview.value || room.value)
function fail(e) { error.value = typeof e === 'string' ? e : errorMessage(e); toast.error(error.value) }
async function getAsset(f) {
  if (assets.value[f.versionId]) return assets.value[f.versionId]
  const {data}=await api.get(`/house/versions/${f.versionId}`)
  assets.value={...assets.value,[f.versionId]:data}; return data
}
async function choose(f) {
  try {
    const asset=await getAsset(f)
    detail.value=asset;copied.value=false
    if (tab.value==='room' && !locked.value) { pending.value=asset; selectedId.value=null; tool.value='select'; preview.value=null }
  } catch (e) { fail(e) }
}
function changed() { saver?.changed(); error.value='' }
function changeRoom(mutator) {
  if (locked.value) return
  if (!ownerValid()) {ready.value=false;fail('登录身份已变更，请重新进入房屋。草稿仍保留在原账号下。');return}
  const next=clone(room.value); mutator(next)
  const problem=placementError(next,assets.value)
  if (problem) { fail(problem); return false }
  history.push(room.value); room.value=next; changed(); return true
}
function placeAt(point) {
  if (!pending.value || locked.value) return
  const asset=pending.value
  const p={id:crypto.randomUUID(),versionId:asset.furniture.versionId,rotation:0,position:anchorPosition(asset.data,point),paletteOverrides:{}}
  if (changeRoom((r)=>r.placements.push(p))) {selectedId.value=p.id;pending.value=null}
}
function pick(point) {
  if (pending.value) { placeAt(point); return }
  selectedId.value=point.id || null; preview.value=null;if(point.id)tool.value='move'
}
function move(axis, value) {
  if (!selected.value) return
  changeRoom((r)=>{r.placements.find((p)=>p.id===selectedId.value).position[axis]=Number(value)})
}
function rotate() { if(selected.value) changeRoom((r)=>{const p=r.placements.find((p)=>p.id===selectedId.value);p.rotation=(p.rotation+90)%360}) }
function remove() { if(selected.value) {changeRoom((r)=>{r.placements=r.placements.filter((p)=>p.id!==selectedId.value)});selectedId.value=null} }
function historyAction(action) {
  if(locked.value) return
  const next=history[action](room.value)
  if(next){room.value=next;selectedId.value=null;changed()}
}
function recolor(overrides) { if(selected.value) changeRoom((r)=>{r.placements.find((p)=>p.id===selectedId.value).paletteOverrides=overrides}) }
function palette(p) {
  if (!chosenData.value || !selected.value) return
  recolor(Object.fromEntries(chosenData.value.palette.filter((s)=>s.editable && p.colors[s.key]).map((s)=>[s.key,p.colors[s.key]])))
}
function dragMove(point) {
  if(locked.value) return
  const next=clone(room.value), p=next.placements.find((p)=>p.id===point.id)
  if(!p) return
  p.position=point.position;preview.value=next;invalidPreview.value=placementError(next,assets.value)
}
function dragEnd() {
  if (preview.value && !invalidPreview.value && !locked.value && ownerValid()) {history.push(room.value);room.value=preview.value;changed()}
  else if(invalidPreview.value) toast.error(invalidPreview.value)
  preview.value=null;invalidPreview.value=''
}
function dragCancel(){preview.value=null;invalidPreview.value=''}
function scaleFurniture(value){if(selected.value)changeRoom((r)=>{r.placements.find((p)=>p.id===selectedId.value).scale=Number(value)})}
async function drop(event) {
  if(locked.value) return
  try { const f=JSON.parse(event.dataTransfer.getData('application/house-furniture')); await choose(f);scene.value?.pickAt(event) } catch(e) { fail(e) }
}
function materialChange(key, field, value) {changeRoom((r)=>{r[key][field]=value || null})}
async function uploadTexture(event) {
  const file=event.target.files[0];if(!file)return
  if(file.size>10*1024*1024){fail('纹理图片不能超过10 MB');return}
  const form=new FormData();form.append('file',file);savingTexture.value=true
  try { const {data}=await client.post('/house/textures',form);if(!ownerValid())return;textures.value.push(data);toast.success('纹理已上传，审核前仅你可见') } catch(e){fail(e)} finally {savingTexture.value=false;event.target.value=''}
}
async function removeTexture(t) {
  try {await client.delete(`/house/textures/${t.recordId}`);textures.value=textures.value.filter((s)=>s.id!==t.id);changeRoom((r)=>{for(const k of ['floor','wall'])if(r[k].textureId===t.id)r[k].textureId=null})}catch(e){fail(e)}
}
async function flush() { if(await saver?.flush()) toast.success('房屋已保存到云端') }
async function publishRoom(enabled) {
  if(locked.value || publishing.value)return
  publishing.value=true
  try {
    if(enabled && !(await saver.flush()))return
    const {data}=await client.patch('/house/room/share',{enabled,...(enabled?{revision:saver.revision}:{})});if(!ownerValid())return;shareId.value=data.shareId;publishedAt.value=data.publishedAt
    toast.success(enabled?'展示版本已发布；后续保存只修改私人草稿':'参观已关闭，旧链接已失效')
  }catch(e){fail(e)}finally{publishing.value=false}
}
async function copyLink(){try{await navigator.clipboard.writeText(`${location.origin}/house/visit/${shareId.value}`);toast.success('分享链接已复制')}catch{fail('复制失败，请复制下方链接')}}
function exportDraft(){const url=URL.createObjectURL(new Blob([JSON.stringify({state:room.value,assets:assets.value})],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='房屋草稿.json';a.click();URL.revokeObjectURL(url)}
async function restore() {
  try {
    const next=clone(draft.value.state)
    for(const p of next.placements)if(!assets.value[p.versionId]){const {data}=await client.get(`/house/versions/${p.versionId}`);assets.value[p.versionId]=data}
    const problem=placementError(next,assets.value);if(problem)throw new Error(problem)
    history.push(room.value);room.value=next;draft.value=null;changed()
  }catch(e){fail(e)}
}
async function loadRoom() {
  if(!client || !ownerValid() || saveStatus.value.saving)return
  ready.value=false
  try {
    const {data}=await client.get('/house/room');if(disposed || !ownerValid())return
    room.value=data.state;assets.value=data.assets;shareId.value=data.shareId;publishedAt.value=data.publishedAt;roomVisible.value=data.isVisible!==false;history.clear();saver.reset(data.revision);ready.value=true
    try {draft.value=await draftOperation(ownerId.value,'room','get')}catch(e){fail(e)}
    if(data.revision===0 && !draft.value)saver.changed()
  }catch(e){fail(e)}
}
function toWorkshop(asset) {
  if(locked.value)return
  const overrides=selected.value?.versionId===asset.furniture.versionId ? selected.value.paletteOverrides : {}
  workshopSource.value={...clone(asset),fork:true,data:recoloredData(asset.data,overrides)};tab.value='workshop'
}
async function furnitureSaved(f) {
  browser.value?.reload(); const asset=await getAsset(f); detail.value=asset;toast.success('家具已保存')
}
async function publish(f,enabled) {
  if(enabled && f.draftVersionId && f.versionId!==f.draftVersionId){try{detail.value=await getAsset({versionId:f.draftVersionId});toast.success('已载入最新私人草稿，请检查后点击更新分享')}catch(e){fail(e)}return}
  try{const {data}=await client.patch(`/house/furniture/${f.id}/publish`,{enabled,revision:f.revision});if(!ownerValid())return;detail.value.furniture=data;browser.value?.reload();toast.success(enabled?'家具分享版本已发布':'已取消公开')}catch(e){fail(e)}
}
async function editOriginal(){if(!detail.value || locked.value)return;try{const f=detail.value.furniture;workshopSource.value=await getAsset({versionId:f.draftVersionId || f.versionId});tab.value='workshop'}catch(e){fail(e)}}
async function favorite(){const f=detail.value?.furniture;if(!f || locked.value)return;try{const url=`/house/furniture/${f.id}/favorite`;const {data}=f.favorited?await client.delete(url):await client.put(url);if(!ownerValid())return;f.favorited=data.favorited;browser.value?.reload()}catch(e){fail(e)}}
async function copyFurniture(){const source=detail.value;if(!source || locked.value || copied.value)return;copied.value=true;try{const {data}=await client.post(`/house/furniture/${source.furniture.id}/copy`,{versionId:source.furniture.versionId});if(!ownerValid())return;await furnitureSaved(data);toast.success('独立副本已保存到我的作品，可以摆放或编辑')}catch(e){fail(e)}finally{copied.value=false}}
async function copyFurnitureLink(){if(!detail.value)return;try{await navigator.clipboard.writeText(`${location.origin}/house?furniture=${detail.value.furniture.publishedVersionId || detail.value.furniture.versionId}`);toast.success('家具分享链接已复制')}catch{fail('复制失败，请复制浏览器中的家具链接')}}
async function deleteFurniture(f) {
  if(!window.confirm('删除这件家具？已放进房屋的版本会保留。'))return
  try{await client.delete(`/house/furniture/${f.id}`);detail.value=null;browser.value?.reload()}catch(e){fail(e)}
}
function useDetail() {pending.value=detail.value;selectedId.value=null;tab.value='room';tool.value='select'}
async function useExample(event) {
  const index=Number(event.target.value);event.target.value='';if(!Number.isInteger(index) || !catalog.value.examples[index])return
  if(room.value.placements.length && !window.confirm('示例布置会替换当前家具摆放，可用撤销恢复。继续吗？'))return
  try {
    const next=clone(catalog.value.examples[index].state)
    for(const p of next.placements)await getAsset({versionId:p.versionId})
    const problem=placementError(next,assets.value);if(problem)throw new Error(problem)
    history.push(room.value);room.value=next;selectedId.value=null;changed()
  }catch(e){fail(e)}
}
watch(tab,(value)=>{if(value==='workshop')workshopOpened.value=true})
function beforeUnload(event){if(saver?.dirty){event.preventDefault();event.returnValue=''}}
onMounted(async()=>{
  try {
    catalog.value=(await api.get('/house/catalog')).data
    await auth.restore()
    if(auth.isLoggedIn && !auth.emailGateRequired){
      ownerId.value=auth.user.id;const owned=ownedClient();client=owned.client;ownerValid=owned.ownerValid;disposeClient=owned.dispose
      saver=createSaveController({ownerValid,snapshot:()=>clone(room.value),writeCloud:async(payload)=>(await client.put('/house/room',payload)).data,
        writeLocal:(value)=>draftOperation(ownerId.value,'room','put',value),removeLocal:()=>draftOperation(ownerId.value,'room','delete'),onStatus:(value)=>{saveStatus.value={...saveStatus.value,...value}}})
      await loadRoom();textures.value=(await client.get('/house/textures')).data
    }else tab.value='library'
    if(route.query.tab==='visit' && auth.isLoggedIn)tab.value='visit'
    if(route.query.furniture){const {data}=await api.get(`/house/versions/${route.query.furniture}`);assets.value[data.furniture.versionId]=data;detail.value=data;tab.value='library'}
  }catch(e){fail(e)}finally{loading.value=false}
  window.addEventListener('beforeunload',beforeUnload)
})
onBeforeRouteLeave(async()=>{
  if(saver?.dirty && !(await saver.flush()))return window.confirm('云端保存未完成，本地草稿已保留，仍要离开吗？')
})
onBeforeUnmount(()=>{disposed=true;saver?.dispose();disposeClient?.();window.removeEventListener('beforeunload',beforeUnload)})
</script>

<template>
  <div class="house-page page">
    <div class="house-heading"><div><span class="eyebrow"><House :size="14" />给生活留一个角落</span><h1>我的小屋</h1><p>一件家具，一点喜欢的颜色。慢慢布置属于你的空间。</p></div><div class="house-count"><strong>120<span>款</span></strong><small>家具 · 六套搭配色板</small></div></div>
    <div v-if="loading" class="skeleton" style="height:600px" aria-busy="true" />
    <template v-else>
      <div class="house-tabs" role="tablist" aria-label="房屋功能">
        <button v-for="[id,label,icon] in [['room','我的房屋',House],['workshop','家具工坊',Hammer],['library','家具库',Armchair],['visit','参观',House]]" :key="id" role="tab" :aria-selected="tab===id" :disabled="id!=='library' && locked" @click="tab=id"><component :is="icon" :size="16" />{{ label }}</button>
      </div>
      <HouseHelp :owner-id="ownerId" />
      <p v-if="locked" class="house-notice">{{ auth.isLoggedIn?'请重新进入房屋，或先完成邮箱验证。':'登录后可以布置房屋、制作家具和邀请朋友串门。' }}<RouterLink v-if="!auth.isLoggedIn" to="/login?redirect=/house">去登录</RouterLink></p>
      <p v-if="error || saveStatus.error" class="house-notice is-error" role="alert">{{ error || saveStatus.error }}</p>
      <p v-if="!roomVisible" class="house-notice is-error">房屋已被内容审核人员屏蔽，访客暂时无法进入。你仍可整理自己的布置。</p>
      <div v-if="draft && tab==='room'" class="house-notice">发现未同步的本地房屋草稿，恢复后将以当前云端版本保存。<button @click="restore">恢复草稿</button><button @click="draft=null">暂不恢复</button></div>
      <div v-if="saveStatus.conflict" class="house-notice"><button :disabled="saveStatus.saving" @click="loadRoom">重新载入云端</button><button @click="exportDraft">导出当前草稿</button></div>
      <FurnitureWorkshop v-show="tab==='workshop'" v-if="ownerId && ready && (workshopOpened || tab==='workshop')" :owner-id="ownerId" :catalog="catalog" :source="workshopSource" @saved="furnitureSaved" @error="fail" />
      <VisitBrowser v-if="tab==='visit' && !locked" />
      <div v-show="tab==='room' || tab==='library'" class="house-layout" :class="{library:tab==='library'}">
        <aside class="house-library-panel"><h2>{{ tab==='room'?'挑一件家具':'家具收藏' }}</h2><button class="mobile-panel-toggle" :aria-expanded="libraryOpen" @click="libraryOpen=!libraryOpen">{{ libraryOpen?'收起家具库':'展开家具库' }}</button><FurnitureBrowser v-show="libraryOpen" ref="browser" :class="{expanded:tab==='library'}" :catalog="catalog" :logged-in="auth.isLoggedIn" @choose="choose" @error="fail" /></aside>
        <section v-if="tab==='room'" class="house-room-panel">
          <div class="house-toolbar"><input :value="room.name" aria-label="房屋名称" maxlength="64" :disabled="locked" @change="changeRoom((r)=>r.name=$event.target.value)" /><select aria-label="使用示例布置" :disabled="locked" @change="useExample"><option value="">示例布置</option><option v-for="(example,i) in catalog?.examples" :key="example.name" :value="i">{{ example.name }}</option></select><button :disabled="locked" @click="historyAction('undo')" aria-label="撤销"><Undo2 :size="16" /></button><button :disabled="locked" @click="historyAction('redo')" aria-label="重做"><Redo2 :size="16" /></button><button :disabled="locked || saveStatus.saving || saveStatus.conflict" @click="flush"><Save :size="16" />保存草稿</button><button :disabled="locked || publishing || saveStatus.conflict" @click="publishRoom(true)"><Share2 :size="16" />{{ shareId?'更新展示':'开放参观' }}</button><button v-if="shareId" :disabled="locked || publishing" @click="publishRoom(false)">关闭参观</button></div>
          <div class="house-scene-drop" @dragover.prevent @drop.prevent="drop"><VoxelScene ref="scene" :room="displayRoom" :assets="assets" :selected="selectedId" :invalid-id="invalidPreview?selectedId:null" :texture-urls="textureUrls" :tool="tool" :readonly="locked" @pick="pick" @drag="dragMove" @drag-end="dragEnd" @drag-cancel="dragCancel" @error="fail" /></div>
          <div class="house-room-status"><span>{{ room.placements.length }} / 128 件 · {{ saveStatus.saving?'云端保存中':saveStatus.dirty?'本地草稿，等待同步':'草稿已同步' }}</span><button v-for="[id,label] in [['select','选择'],['move','移动'],['camera','视角']]" :key="id" :aria-pressed="tool===id" @click="pending=null;tool=id">{{label}}</button><button @click="exportDraft">导出草稿</button></div>
          <p v-if="shareId" class="muted">展示版本发布于 {{new Date(publishedAt).toLocaleString()}}。装修后的草稿需点击“更新展示”才会对访客生效。</p>
          <p v-if="pending" class="house-notice">已选择「{{ pending.furniture.name }}」，点击房间放置。<button @click="placeAt({x:128,y:128,z:0})">放在中央</button><button @click="pending=null">取消</button></p>
          <p v-if="invalidPreview" class="house-notice is-error">{{ invalidPreview }}</p>
          <div v-if="shareId" class="house-share"><RouterLink :to="`/house/visit/${shareId}`">查看访客页面</RouterLink><input readonly :value="shareUrl" aria-label="房屋分享链接" /><button @click="copyLink">复制链接</button></div>
          <details class="room-inventory"><summary>已放置家具（{{ room.placements.length }}）</summary><button v-for="p in room.placements" :key="p.id" :aria-pressed="selectedId===p.id" @click="selectedId=p.id;pending=null;tool='move'">{{ assets[p.versionId]?.furniture.name || '家具' }} · {{ p.position.x }},{{ p.position.y }},{{ p.position.z }}</button></details>
        </section>
        <aside v-if="tab==='room'" class="house-properties" :class="{collapsed:!propertiesOpen}">
          <button class="mobile-panel-toggle" :aria-expanded="propertiesOpen" @click="propertiesOpen=!propertiesOpen">{{ propertiesOpen?'收起家具属性与墙地面':'展开家具属性与墙地面' }}</button>
          <template v-if="selected && chosenData">
            <h2>{{ chosen.furniture.name }}</h2><p v-if="!chosen.furniture.isVisible" class="muted">已被下架，访客看不到此模型</p>
            <label v-for="axis in ['x','y','z']" :key="axis">{{ {x:'横向 X',y:'纵向 Y',z:'高度 Z'}[axis] }}<input type="number" :value="selected.position[axis]" min="0" :max="axis==='z'?127:255" @change="move(axis,$event.target.value)" /></label>
            <div class="property-actions"><button @click="rotate">旋转 {{ selected.rotation }}°</button><button @click="remove"><Trash2 :size="14" />移除</button></div>
            <label>家具大小<select :value="selected.scale ?? 1" aria-label="家具缩放比例" @change="scaleFurniture($event.target.value)"><option :value=".5">50%</option><option :value="1">100%</option><option :value="2">200%</option></select></label>
            <h3>材质改色</h3><label v-for="s in chosenData.palette.filter((s)=>s.editable)" :key="s.key">{{ s.label }}<input type="color" :value="selected.paletteOverrides[s.key] || s.color" @input="recolor({...selected.paletteOverrides,[s.key]:$event.target.value})" /></label>
            <button @click="recolor({})">恢复默认配色</button>
            <button v-for="p in catalog?.palettes" :key="p.id" class="house-palette" @click="palette(p)"><span><i v-for="key in ['wood','fabric','accent']" :key="key" :style="{background:p.colors[key]}" /></span>{{ p.name }}</button>
            <button @click="toWorkshop(chosen)"><Copy :size="14" />复制到工坊</button>
          </template>
          <p v-else class="muted">选中家具后可移动、旋转，并为每个材质部位改色。</p>
          <h2>墙面与地面</h2>
          <template v-for="key in ['floor','wall']" :key="key">
            <h3>{{ key==='floor'?'地面':'墙面' }}</h3><label>底色<input type="color" :value="room[key].color" @input="materialChange(key,'color',$event.target.value)" /></label>
            <select :value="room[key].textureId || ''" :aria-label="`${key==='floor'?'地面':'墙面'}纹理`" @change="materialChange(key,'textureId',$event.target.value)"><option value="">纯色</option><optgroup label="预置纹理"><option v-for="t in catalog?.textures" :key="t.id" :value="t.id">{{ t.name }}</option></optgroup><optgroup label="我的纹理"><option v-for="t in textures" :key="t.id" :value="t.id">{{ t.name }}{{t.isVisible?'':'（仅自己可见）'}}</option></optgroup></select>
            <select :value="room[key].mode" aria-label="纹理铺贴方式" @change="materialChange(key,'mode',$event.target.value)"><option value="repeat">重复铺贴</option><option value="stretch">拉伸填满</option></select>
          </template>
          <label class="texture-upload">{{ savingTexture?'上传中…':'上传 PNG/JPEG（≤10MB）' }}<input type="file" accept="image/png,image/jpeg" :disabled="savingTexture || locked" @change="uploadTexture" /></label>
          <div v-for="t in textures" :key="t.id" class="texture-row"><LazyImage :src="t.url" :alt="t.name" /><span>{{ t.name }}<small>{{ t.isVisible?'已公开':t.moderated?'未通过审核':'待审核' }}</small></span><button @click="removeTexture(t)" aria-label="删除纹理">×</button></div>
        </aside>
        <aside v-if="tab==='library' && detail" class="house-detail">
          <h2>{{ detail.furniture.name }}</h2><VoxelScene :data="detail.data" readonly compact /><p class="muted">{{ detail.furniture.style }} · {{ detail.data.gridSize }}³ · {{ detail.data.voxels.length.toLocaleString() }}个体素</p>
          <RouterLink v-if="detail.furniture.creatorId" :to="`/house/users/${detail.furniture.creatorId}`">查看创作者主页</RouterLink>
          <p v-if="detail.creator" class="muted">作者：{{detail.creator.nickname}}</p>
          <template v-if="!locked"><button class="button" @click="useDetail">放入房屋</button><button v-if="detail.furniture.isPublic" class="button secondary" :aria-pressed="!!detail.furniture.favorited" @click="favorite">{{detail.furniture.favorited?'取消收藏':'收藏家具'}}</button><button class="button secondary" :disabled="copied" @click="copyFurniture">{{copied?'复制中…':'复制到我的家具库'}}</button><button class="button secondary" @click="toWorkshop(detail)">复制到工坊修改</button><template v-if="detail.furniture.creatorId===ownerId"><button class="button secondary" @click="editOriginal">编辑原作品</button><button class="button secondary" @click="publish(detail.furniture,true)">{{ detail.furniture.isPublic?'更新分享':'发布到家具库' }}</button><button v-if="detail.furniture.isPublic" class="button secondary" @click="publish(detail.furniture,false)">取消公开</button><button class="button danger" @click="deleteFurniture(detail.furniture)">删除家具</button></template></template>
          <button v-if="detail.furniture.isPublic" class="button secondary" @click="copyFurnitureLink">复制家具分享链接</button>
        </aside>
      </div>
    </template>
  </div>
</template>
