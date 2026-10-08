<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api, errorMessage } from '../api'
import LazyImage from '../components/LazyImage.vue'
const props = defineProps({ catalog: Object, loggedIn: Boolean })
const emit = defineEmits(['choose', 'error'])
const category = ref(''), style = ref(''), search = ref(''), mine = ref(false), page = ref(1), loading = ref(false), items = ref([]), total = ref(0)
const favorites=ref(false)
const pages = computed(() => Math.max(1, Math.ceil(total.value / 20)))
let generation = 0, searchTimer
async function load() {
  const gen = ++generation; loading.value = true
  try {
    const { data } = await api.get('/house/furniture', { params: { category: category.value, style: style.value, search: search.value, mine: mine.value, favorites:favorites.value, page: page.value } })
    if (gen === generation) { items.value = data.items; total.value = data.total }
  } catch (e) { emit('error', errorMessage(e)) } finally { if (gen === generation) loading.value = false }
}
watch([category, style, mine, favorites], () => { page.value = 1; load() })
watch(search, () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { page.value = 1; load() }, 250) })
watch(page, load)
onMounted(load)
onBeforeUnmount(()=>{generation++;clearTimeout(searchTimer)})
function drag(event, f) { event.dataTransfer.setData('application/house-furniture', JSON.stringify(f)); event.dataTransfer.effectAllowed = 'copy' }
defineExpose({ reload: load })
</script>
<template>
  <div class="furniture-browser">
    <div class="library-filters">
      <input v-model="search" type="search" aria-label="搜索家具" placeholder="寻找一件喜欢的家具…" maxlength="64" />
      <select v-model="category" aria-label="家具类别"><option value="">全部类别</option><option v-for="c in catalog?.categories" :key="c.id" :value="c.id">{{ c.label }}</option></select>
      <select v-model="style" aria-label="家具风格"><option value="">全部风格</option><option v-for="s in ['原木','奶油','北欧','复古','现代','自制']" :key="s">{{ s }}</option></select>
      <label v-if="loggedIn" class="library-mine"><input v-model="mine" type="checkbox" @change="favorites=false" />我的作品</label>
      <label v-if="loggedIn" class="library-mine"><input v-model="favorites" type="checkbox" @change="mine=false" />我的收藏</label>
    </div>
    <div v-if="loading" class="furniture-grid" aria-busy="true"><div v-for="n in 8" :key="n" class="skeleton" style="height:165px" /></div>
    <div v-else class="furniture-grid">
      <button v-for="f in items" :key="f.id" class="furniture-item" draggable="true" @dragstart="drag($event,f)" @click="emit('choose',f)">
        <LazyImage v-if="f.thumbnail" :src="f.thumbnail" :alt="f.name" />
        <div v-else class="furniture-placeholder">{{ f.name.slice(0,1) }}<small>体素创作 · 点击预览</small></div>
        <strong>{{ f.name }}</strong><small>{{ f.style }}{{ f.isVisible ? '' : ' · 已下架' }}</small>
      </button>
    </div>
    <p v-if="!loading && !items.length" class="muted">这里还没有家具，换个分类或去工坊制作一件。</p>
    <div class="library-pagination"><button :disabled="page<=1 || loading" @click="page--">上一页</button><span>{{ page }} / {{ pages }} · {{ total }}款</span><button :disabled="page>=pages || loading" @click="page++">下一页</button></div>
  </div>
</template>
<style scoped>
.library-filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}.library-filters input[type=search]{width:100%}.library-filters input,.library-filters select{min-height:38px;padding:6px 9px;border:1px solid var(--line);border-radius:6px;background:var(--paper);color:var(--ink)}.library-filters select{max-width:48%;flex:1}.library-mine{display:flex;align-items:center;gap:4px;font-size:12px}.furniture-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.furniture-item{padding:0 0 10px;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--paper);color:var(--ink);text-align:left;transition:border-color .15s}.furniture-item:hover{border-color:var(--green)}.furniture-item>img,.furniture-placeholder{width:100%;height:128px;object-fit:contain;background:#f2eee5}.furniture-placeholder{display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:serif;font-size:36px;color:#7e8c76}.furniture-placeholder small{font:10px system-ui;margin-top:6px}.furniture-item strong,.furniture-item>small{display:block;padding:0 9px;margin-top:6px;font-size:12px}.furniture-item>small{color:var(--muted);font-size:10px}.library-pagination{display:flex;justify-content:center;align-items:center;gap:10px;font-size:11px;margin-top:16px}.library-pagination button{border:1px solid var(--line);background:var(--paper);padding:8px;border-radius:5px;color:var(--ink)}@media(min-width:1000px){.furniture-browser.expanded .furniture-grid{grid-template-columns:repeat(5,minmax(0,1fr))}}
</style>
