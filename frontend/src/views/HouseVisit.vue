<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Heart, House, MessageCircle } from '@lucide/vue'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'
import UserTitleTag from '../components/UserTitleTag.vue'
import UserAvatar from '../components/UserAvatar.vue'
import VoxelScene from '../house/VoxelScene.vue'
import '../house/house.css'
const route=useRoute(),auth=useAuthStore(),toast=useToast(),data=ref(null),loading=ref(true),error=ref(''),comments=ref([]),commentLoading=ref(false),page=ref(1),total=ref(0),text=ref(''),posting=ref(false),liking=ref(false)
const shareId=computed(()=>route.params.shareId),pages=computed(()=>Math.max(1,Math.ceil(total.value/20)))
let generation=0,commentGeneration=0
async function loadComments(){const gen=++commentGeneration,sid=shareId.value;commentLoading.value=true;try{const {data:res}=await api.get(`/house/visit/${sid}/comments`,{params:{page:page.value}});if(gen!==commentGeneration || sid!==shareId.value)return;comments.value=res.items;total.value=res.total}catch(e){if(gen===commentGeneration)toast.error(errorMessage(e))}finally{if(gen===commentGeneration)commentLoading.value=false}}
async function load(){const gen=++generation;loading.value=true;error.value='';try{const {data:res}=await api.get(`/house/visit/${shareId.value}`);if(gen!==generation)return;data.value=res;page.value=1;await loadComments()}catch(e){if(gen===generation)error.value=errorMessage(e)}finally{if(gen===generation)loading.value=false}}
async function like(){if(liking.value)return;liking.value=true;try{const url=`/house/visit/${shareId.value}/like`;const res=data.value.liked?await api.delete(url):await api.put(url);Object.assign(data.value,res.data)}catch(e){toast.error(errorMessage(e))}finally{liking.value=false}}
async function post(){if(posting.value || !text.value.trim())return;posting.value=true;try{await api.post(`/house/visit/${shareId.value}/comments`,{content:text.value});text.value='';page.value=1;await loadComments()}catch(e){toast.error(errorMessage(e))}finally{posting.value=false}}
async function remove(c){try{await api.delete(`/house/comments/${c.id}`);await loadComments()}catch(e){toast.error(errorMessage(e))}}
watch(shareId,load);watch(page,loadComments);onMounted(load)
</script>
<template>
  <div class="house-page page house-visit">
    <RouterLink to="/house" class="visit-back"><House :size="16" />回到房屋</RouterLink>
    <div v-if="loading" class="skeleton" style="height:600px" aria-busy="true" />
    <div v-else-if="error" class="house-notice is-error" role="alert">{{ error }}<button @click="load">重新加载</button></div>
    <template v-else-if="data">
      <div class="house-heading"><div><span class="eyebrow">欢迎来串门</span><h1>{{ data.state.name }}</h1><RouterLink :to="`/house/users/${data.owner.id}`">{{ data.owner.nickname }}<UserTitleTag :title="data.owner.title" />的小屋</RouterLink></div><button v-if="auth.isLoggedIn" class="button secondary" :disabled="liking" :aria-pressed="data.liked" @click="like"><Heart :size="16" :fill="data.liked?'currentColor':'none'" />{{ data.liked?'已喜欢':'喜欢这间小屋' }} · {{ data.likeCount }}</button><RouterLink v-else to="/login" class="button secondary">登录后点赞 · {{ data.likeCount }}</RouterLink></div>
      <VoxelScene :room="data.state" :assets="data.assets" :texture-urls="data.textureUrls" readonly />
      <p class="muted visit-note">这是房主最近保存的布置。你可以旋转、缩放与平移视角。</p>
      <section class="visit-comments"><h2><MessageCircle :size="18" />来访留言</h2>
        <form v-if="auth.isLoggedIn" @submit.prevent="post"><textarea v-model="text" maxlength="1000" rows="3" aria-label="串门留言" placeholder="给房主留一句话…" /><div><small>{{ text.length }} / 1000</small><button class="button small" :disabled="posting || !text.trim()">{{ posting?'发送中…':'留下留言' }}</button></div></form>
        <p v-else class="muted"><RouterLink :to="{path:'/login',query:{redirect:route.fullPath}}">登录后</RouterLink>给房主留言。</p>
        <div v-if="commentLoading" class="skeleton-list"><div v-for="n in 3" :key="n" class="skeleton" style="height:70px" /></div>
        <template v-else><article v-for="c in comments" :key="c.id" class="visit-comment"><UserAvatar :user="c.user" /><div><RouterLink :to="`/house/users/${c.user.id}`">{{ c.user.nickname }}<UserTitleTag :title="c.user.title" /></RouterLink><p>{{ c.content }}</p><small>{{ new Date(c.createdAt).toLocaleString() }}</small></div><button v-if="c.canDelete" @click="remove(c)">删除</button></article><p v-if="!comments.length" class="muted">还没有留言，成为第一位来访的朋友吧。</p></template>
        <div class="comment-pagination"><button :disabled="page<=1" @click="page--">上一页</button><span>{{ page }} / {{ pages }}</span><button :disabled="page>=pages" @click="page++">下一页</button></div>
      </section>
    </template>
  </div>
</template>
<style scoped>
.house-visit{max-width:1180px}.visit-back{display:inline-flex;gap:7px;align-items:center;color:var(--muted);font-size:13px}.visit-note{font-size:12px;margin-top:12px}.visit-comments{max-width:780px;margin:40px auto 0}.visit-comments h2{display:flex;align-items:center;gap:8px;font-size:20px}.visit-comments textarea{width:100%;resize:vertical;border:1px solid var(--line);border-radius:9px;padding:12px;background:var(--paper);color:var(--ink)}.visit-comments form>div{display:flex;align-items:center;justify-content:space-between;margin:8px 0 20px}.visit-comments small{color:var(--muted);font-size:10px}.visit-comment{display:flex;gap:12px;padding:18px 0;border-top:1px solid var(--line);font-size:13px}.visit-comment>div{flex:1}.visit-comment p{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8;margin:8px 0}.visit-comment button,.comment-pagination button{border:0;background:transparent;color:var(--muted);font-size:12px}.comment-pagination{display:flex;justify-content:center;gap:20px;font-size:12px;margin:20px 0}@media(max-width:600px){.house-heading{flex-direction:column;align-items:flex-start;gap:20px}}
</style>
