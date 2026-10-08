<script setup>
import { onBeforeUnmount,onMounted,ref,watch,computed } from 'vue'
import { api,errorMessage } from '../api'
import UserTitleTag from '../components/UserTitleTag.vue'
const items=ref([]),page=ref(1),total=ref(0),loading=ref(true),error=ref('')
const pages=computed(()=>Math.max(1,Math.ceil(total.value/20)))
let generation=0
async function load(){const gen=++generation;loading.value=true;error.value='';try{const {data}=await api.get('/house/rooms',{params:{page:page.value}});if(gen!==generation)return;items.value=data.items;total.value=data.total}catch(e){if(gen===generation)error.value=errorMessage(e)}finally{if(gen===generation)loading.value=false}}
watch(page,load);onMounted(load);onBeforeUnmount(()=>generation++)
</script>
<template>
  <section class="visit-browser">
    <h2>参观朋友的小屋</h2><p class="muted">这里展示房主确认发布的布置。进入后可自由旋转、平移和缩放视角。</p>
    <p v-if="error" class="house-notice is-error" role="alert">{{error}}<button @click="load">重试</button></p>
    <div v-if="loading" class="visit-grid" aria-busy="true"><div v-for="n in 6" :key="n" class="skeleton" style="height:160px" /></div>
    <div v-else class="visit-grid"><article v-for="r in items" :key="r.shareId"><h3>{{r.name}}</h3><p>{{r.owner?.nickname || '房主'}}<UserTitleTag :title="r.owner?.title" /></p><small>发布于 {{new Date(r.publishedAt).toLocaleString()}}</small><RouterLink :to="`/house/visit/${r.shareId}`" class="button secondary small">参观</RouterLink></article></div>
    <p v-if="!loading && !error && !items.length" class="muted">还没有开放的小屋。在“我的房屋”中开放参观后，你的小屋就会出现在这里。</p>
    <div class="visit-pages"><button class="button secondary small" :disabled="page<=1 || loading" @click="page--">上一页</button><span>{{page}} / {{pages}}</span><button class="button secondary small" :disabled="page>=pages || loading" @click="page++">下一页</button></div>
  </section>
</template>
<style scoped>
.visit-browser>h2{font-size:22px}.visit-browser>.muted{font-size:13px;line-height:1.8}.visit-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px;margin:20px 0}.visit-grid article{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:20px;display:flex;flex-direction:column;gap:10px;overflow-wrap:anywhere}.visit-grid h3,.visit-grid p{margin:0}.visit-grid small{color:var(--muted);font-size:11px}.visit-grid a{align-self:flex-start}.visit-pages{display:flex;gap:16px;justify-content:center;align-items:center;font-size:12px}
</style>
