<script setup>
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { api, errorMessage } from '../api'
import LazyImage from '../components/LazyImage.vue'
const VoxelScene = defineAsyncComponent(() => import('./VoxelScene.vue'))
const props=defineProps({ textures: Boolean })
const emit=defineEmits(['moderated'])
const kind=ref(props.textures?'textures':'rooms'),items=ref([]),page=ref(1),total=ref(0),loading=ref(true),error=ref(''),preview=ref(null),busy=ref(null)
const pages=computed(()=>Math.max(1,Math.ceil(total.value/20)))
const ident=(item)=>kind.value==='textures'?item.recordId:item.id
let generation=0
async function load(){const gen=++generation;loading.value=true;try{const {data}=await api.get(`/admin/house/${kind.value}`,{params:{page:page.value}});if(gen!==generation)return;items.value=data.items;total.value=data.total;error.value=''}catch(e){if(gen===generation)error.value=errorMessage(e)}finally{if(gen===generation)loading.value=false}}
async function moderate(item,visible){busy.value=ident(item);try{await api.patch(`/admin/house/${kind.value}/${ident(item)}`,{is_visible:visible});item.isVisible=visible;item.moderated=true;emit('moderated')}catch(e){error.value=errorMessage(e)}finally{busy.value=null}}
async function inspect(item){try{const url=kind.value==='rooms'?`/admin/house/rooms/${item.id}/preview`:`/house/versions/${item.versionId}`;preview.value={kind:kind.value,...(await api.get(url)).data}}catch(e){error.value=errorMessage(e)}}
watch(kind,()=>{page.value=1;preview.value=null;load()});watch(page,load);onMounted(load)
</script>
<template>
  <section class="house-moderation"><h2>{{ textures?'房屋纹理':'房屋内容管理' }}</h2><div v-if="!textures" class="house-mod-tabs"><button :aria-pressed="kind==='rooms'" @click="kind='rooms'">房屋</button><button :aria-pressed="kind==='furniture'" @click="kind='furniture'">家具</button></div>
    <p v-if="error" role="alert">{{ error }}</p><div v-if="loading" class="skeleton-list"><div v-for="n in 4" :key="n" class="skeleton" style="height:80px" /></div>
    <template v-else><article v-for="item in items" :key="item.id" class="house-mod-item"><LazyImage v-if="item.url" :src="item.url" :alt="item.name" /><div><strong>{{ item.name }}</strong><small>用户 #{{ item.creatorId }} · {{ item.isVisible?'可见':textures && !item.moderated?'待审核':'已屏蔽' }}</small></div><button v-if="!textures" @click="inspect(item)">查看内容</button><button :disabled="busy===ident(item)" @click="moderate(item,!item.isVisible)">{{ item.isVisible?'屏蔽':textures?'通过':'恢复' }}</button><button v-if="textures && !item.moderated" :disabled="busy===ident(item)" @click="moderate(item,false)">驳回</button></article><p v-if="!items.length" class="muted">暂无{{ textures?'房屋纹理':'房屋内容' }}</p></template>
    <div class="house-mod-pages"><button :disabled="page<=1" @click="page--">上一页</button>{{ page }} / {{ pages }}<button :disabled="page>=pages" @click="page++">下一页</button></div>
    <div v-if="preview"><button @click="preview=null">收起预览</button><VoxelScene v-if="preview.kind==='rooms'" :room="preview.state" :assets="preview.assets" :texture-urls="preview.textureUrls" readonly compact /><VoxelScene v-else :data="preview.data" readonly compact /></div>
  </section>
</template>
<style scoped>
.house-moderation{margin:24px 0}.house-moderation h2{font-size:18px}.house-mod-tabs,.house-mod-pages{display:flex;gap:12px;align-items:center;margin:15px 0;font-size:12px}.house-moderation button{border:1px solid var(--line);border-radius:5px;color:var(--ink);background:var(--paper);padding:8px;font-size:12px}.house-mod-item{display:flex;gap:12px;align-items:center;padding:15px 0;border-bottom:1px solid var(--line)}.house-mod-item>img{width:100px;height:80px;object-fit:cover;border-radius:7px}.house-mod-item>div{flex:1}.house-mod-item small{display:block;font-size:11px;color:var(--muted);margin-top:6px}.house-mod-pages{justify-content:center}@media(max-width:600px){.house-mod-item{flex-wrap:wrap}.house-mod-item>img{width:70px;height:70px}}
</style>
