<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, errorMessage } from '../api'
import LazyImage from '../components/LazyImage.vue'
import UserAvatar from '../components/UserAvatar.vue'
import UserTitleTag from '../components/UserTitleTag.vue'
import VoxelScene from '../house/VoxelScene.vue'
import '../house/house.css'
const route=useRoute(),data=ref(null),loading=ref(true),error=ref(''),page=ref(1),preview=ref(null)
const pages=computed(()=>Math.max(1,Math.ceil((data.value?.furniture.total || 0)/20)))
let generation=0
async function load(){const gen=++generation;loading.value=true;try{const result=await api.get(`/house/users/${route.params.userId}`,{params:{page:page.value}});if(gen!==generation)return;data.value=result.data;error.value=''}catch(e){if(gen===generation)error.value=errorMessage(e)}finally{if(gen===generation)loading.value=false}}
async function choose(f){try{preview.value=(await api.get(`/house/versions/${f.versionId}`)).data}catch(e){error.value=errorMessage(e)}}
watch(()=>route.params.userId,()=>{page.value=1;preview.value=null;load()});watch(page,load);onMounted(load)
</script>
<template>
  <div class="house-page page creator-page"><RouterLink to="/house">← 房屋与家具库</RouterLink><p v-if="error" class="house-notice is-error">{{ error }}</p><div v-if="loading" class="skeleton" style="height:400px" aria-busy="true" />
    <template v-else-if="data"><div class="house-heading"><div class="creator-heading"><UserAvatar :user="data.user" /><div><span class="eyebrow">家具创作者</span><h1>{{ data.user.nickname }}<UserTitleTag :title="data.user.title" /></h1><p>{{ data.user.bio }}</p></div></div><RouterLink v-if="data.shareId" :to="`/house/visit/${data.shareId}`" class="button">去小屋串门</RouterLink></div>
      <h2>公开的家具作品</h2><div class="creator-grid"><button v-for="f in data.furniture.items" :key="f.id" @click="choose(f)"><LazyImage v-if="f.thumbnail" :src="f.thumbnail" :alt="f.name" /><span>{{ f.name }}</span><small>{{ f.style }} · 点击预览</small></button></div><p v-if="!data.furniture.items.length" class="muted">这位创作者还没有公开家具。</p>
      <div class="creator-pagination"><button :disabled="page<=1" @click="page--">上一页</button>{{ page }} / {{ pages }}<button :disabled="page>=pages" @click="page++">下一页</button></div>
      <section v-if="preview" class="creator-preview"><h2>{{ preview.furniture.name }}</h2><VoxelScene :data="preview.data" readonly compact /><RouterLink class="button" :to="{path:'/house',query:{furniture:preview.furniture.versionId}}">在我的房屋中使用</RouterLink></section>
    </template>
  </div>
</template>
<style scoped>
.creator-page{max-width:1180px}.creator-heading{display:flex;align-items:center;gap:20px}.creator-heading h1{font-size:32px}.creator-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.creator-grid button{display:flex;flex-direction:column;gap:8px;background:var(--paper);color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:20px;text-align:left;min-height:110px}.creator-grid img{width:100%;height:130px;object-fit:contain}.creator-grid small{color:var(--muted)}.creator-pagination{display:flex;justify-content:center;gap:20px;padding:20px;font-size:12px}.creator-pagination button{background:transparent;color:var(--ink);border:0}.creator-preview{max-width:620px;margin:30px auto}.creator-preview .button{margin-top:14px}@media(max-width:700px){.creator-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.house-heading{flex-direction:column;align-items:flex-start;gap:20px}}
</style>
