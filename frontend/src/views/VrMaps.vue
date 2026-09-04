<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Heart, Map as MapIcon, Plus, TriangleAlert, UserRound, X } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'
import { MAP_CATEGORIES } from '../constants'
import UserAvatar from '../components/UserAvatar.vue'
import VrMapDetailDialog from '../components/VrMapDetailDialog.vue'

const auth = useAuthStore()
const router = useRouter()
const toast = useToast()
const maps = ref([])
const loading = ref(true)
const error = ref('')
const selected = ref(null)
const showCreate = ref(false)
const creating = ref(false)
const form = reactive({ name: '', category: '休闲', description: '' })

const cover = (item) => item.photos.find((photo) => photo.is_visible)?.image_url

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/vr-maps')
    maps.value = data
  } catch (err) {
    error.value = errorMessage(err, '地图加载失败')
  } finally {
    loading.value = false
  }
}

function create() {
  if (!auth.isLoggedIn) return router.push({ path: '/login', query: { redirect: '/maps' } })
  showCreate.value = true
}

async function submitCreate() {
  if (!form.name.trim()) return toast.error('请填写地图名称')
  if (form.description.trim().length < 10) return toast.error('地图介绍请至少填写 10 个字符')
  creating.value = true
  try {
    await api.post('/vr-maps', { ...form })
    showCreate.value = false
    form.name = ''
    form.category = '休闲'
    form.description = ''
    toast.success('地图已提交，感谢推荐！')
    await load()
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    creating.value = false
  }
}

function onUpdated(updated) {
  selected.value = null
  load()
}

onMounted(load)
</script>

<template>
  <div class="page inner-page maps-page">
    <div class="page-title">
      <div><span class="eyebrow"><MapIcon :size="15" /> VRCHAT MAPS</span><h1>地图推荐</h1><p>发现好玩的 VRChat 世界：提交你心仪的地图，用点赞把它顶上榜。</p></div>
    </div>

    <section class="maps-toolbar">
      <span class="muted"><Heart :size="15" /> 按点赞数排序，点进卡片即可点赞、举报和分享实拍</span>
      <button class="button" type="button" @click="create"><Plus :size="17" />推荐地图</button>
    </section>

    <div v-if="loading" class="maps-grid"><div v-for="i in 6" :key="i" class="maps-card skeleton" /></div>
    <div v-else-if="error" class="maps-empty error-notice">{{ error }}</div>
    <div v-else-if="!maps.length" class="maps-empty"><MapIcon :size="26" /><strong>还没有地图推荐</strong><span>第一张地图由你来推荐。</span></div>
    <div v-else class="maps-grid">
      <button v-for="item in maps" :key="item.id" class="maps-card" type="button" @click="selected = item">
        <figure class="maps-cover">
          <img v-if="cover(item)" :src="cover(item)" :alt="`${item.name} 的照片`" />
          <span v-else class="maps-cover-fallback"><MapIcon :size="26" /></span>
          <span v-if="item.has_pending_report || !item.is_visible" class="maps-flag"><TriangleAlert :size="13" />{{ item.is_visible ? '举报待处理' : '已屏蔽' }}</span>
        </figure>
        <div class="maps-body">
          <h3>{{ item.name }}<span class="role-tag">{{ item.category }}</span></h3>
          <p>{{ item.description }}</p>
          <footer>
            <span class="maps-uploader"><UserAvatar :user="item.uploader" :size="20" />{{ item.uploader.nickname }}</span>
            <span class="maps-likes" :class="{ mine: item.liked_by_me }"><Heart :size="15" />{{ item.like_count }}</span>
          </footer>
        </div>
      </button>
    </div>

    <div v-if="showCreate" class="modal-backdrop" @mousedown.self="showCreate = false">
      <section class="dialog report-dialog" role="dialog" aria-modal="true" aria-label="推荐地图">
        <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="showCreate = false"><X :size="20" /></button>
        <div class="dialog-heading"><span class="eyebrow"><MapIcon :size="14" /> RECOMMEND</span><h2>推荐地图</h2><p>分享一张你喜欢的 VRChat 地图，让更多人发现它。</p></div>
        <form class="form-stack" @submit.prevent="submitCreate">
          <label>地图名称<input v-model.trim="form.name" required maxlength="80" placeholder="如：午夜天台" /></label>
          <label>地图类型<select v-model="form.category" aria-label="地图类型"><option v-for="item in MAP_CATEGORIES" :key="item" :value="item">{{ item }}</option></select></label>
          <label>地图介绍<textarea v-model.trim="form.description" required minlength="10" maxlength="2000" rows="5" placeholder="玩法、亮点、适合的场景……"></textarea><small>{{ form.description.length }}/2000</small></label>
          <div class="dialog-footer"><button type="button" class="button secondary" :disabled="creating" @click="showCreate = false">取消</button><button class="button" :disabled="creating"><MapIcon :size="16" />{{ creating ? '提交中…' : '提交推荐' }}</button></div>
        </form>
      </section>
    </div>

    <VrMapDetailDialog v-if="selected" :map="selected" @close="selected = null" @updated="onUpdated" />
  </div>
</template>

<style scoped>
.maps-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}

.maps-toolbar .muted {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.maps-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}

.maps-card {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: 14px;
  overflow: hidden;
  background: var(--paper);
  text-align: left;
  transition: box-shadow 0.15s ease;
}

.maps-card:hover {
  box-shadow: var(--shadow);
}

.maps-cover {
  position: relative;
  height: 130px;
  margin: 0;
  background: #eef1ef;
}

.maps-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.maps-cover-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--muted);
}

.maps-flag {
  position: absolute;
  top: 8px;
  left: 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 4px;
  background: rgba(42, 48, 45, 0.82);
  color: #fff;
  font-size: 11px;
}

.maps-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px 14px;
}

.maps-body h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 15px;
}

.maps-body p {
  margin: 0;
  font-size: 13px;
  color: var(--muted);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.maps-body footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
}

.maps-uploader {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
}

.maps-likes {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: var(--muted);
}

.maps-likes.mine {
  color: var(--red);
  font-weight: 700;
}

.maps-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 44px 20px;
  border: 1px dashed var(--line);
  border-radius: 14px;
  color: var(--muted);
}
</style>
