<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Award, ChevronLeft, ChevronRight, Coins, Star } from '@lucide/vue'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import { portfolioTagLabel } from '../credential'
import UserAvatar from '../components/UserAvatar.vue'
import UserTitleTag from '../components/UserTitleTag.vue'
import CredentialCard from '../components/CredentialCard.vue'
import AchievementWall from '../components/AchievementWall.vue'

const route = useRoute()
const toast = useToast()
const loading = ref(true)
const error = ref('')
const profile = ref(null)
const wall = ref({ total: 0, page: 1, page_size: 12, items: [] })
const page = ref(1)
const PAGE_SIZE = 12
const ratings = ref(null)

const userId = computed(() => Number(route.params.userId))
const totalPages = computed(() => Math.max(1, Math.ceil((wall.value.total || 0) / PAGE_SIZE)))

async function loadProfile() {
  try {
    profile.value = (await api.get(`/creators/${userId.value}`)).data
  } catch (err) {
    error.value = errorMessage(err, '无法加载该创作者的作品集')
  }
}

async function loadWall() {
  try {
    wall.value = (await api.get(`/creators/${userId.value}/credentials`, {
      params: { page: page.value, page_size: PAGE_SIZE },
    })).data
  } catch (err) {
    toast.error(errorMessage(err, '凭证墙加载失败'))
  }
}

async function loadRatings() {
  try {
    ratings.value = (await api.get(`/users/${userId.value}/rating-summary`)).data
  } catch {
    ratings.value = null
  }
}

async function load() {
  loading.value = true
  error.value = ''
  await loadProfile()
  await Promise.all([loadWall(), loadRatings()])
  loading.value = false
}

function go(next) {
  if (next < 1 || next > totalPages.value) return
  page.value = next
  loadWall()
}

onMounted(load)
</script>

<template>
  <div class="page inner-page creator-page">
    <div v-if="loading" class="skeleton-list">
      <div class="skeleton-block" />
      <div class="skeleton-block" />
    </div>

    <div v-else-if="error" class="empty-state">
      <span>集</span>
      <h3>{{ error }}</h3>
      <RouterLink class="button secondary" to="/">返回委托大厅</RouterLink>
    </div>

    <template v-else-if="profile">
      <section class="creator-head">
        <UserAvatar :user="profile.user" :size="72" />
        <div class="creator-identity">
          <h1>{{ profile.user.nickname }}<UserTitleTag :title="profile.user.title" /></h1>
          <p class="muted">{{ profile.user.bio || '这个人还没有填写简介。' }}</p>
          <div class="creator-tags">
            <span class="role-tag"><Award :size="13" />已完成 {{ profile.credential_count }} 份公开委托</span>
            <span v-if="ratings?.taker?.count" class="role-tag"><Star :size="13" />接单 {{ ratings.taker.average }} 星 · {{ ratings.taker.count }} 评</span>
            <span v-if="ratings?.publisher?.count" class="role-tag"><Star :size="13" />委托 {{ ratings.publisher.average }} 星 · {{ ratings.publisher.count }} 评</span>
            <span v-if="profile.user.lifetime_points" class="role-tag"><Coins :size="13" />Lv{{ profile.user.level }} · 累计 {{ profile.user.lifetime_points }} 积分</span>
            <span v-for="tag in profile.tags" :key="tag.value" class="facet-chip static">{{ portfolioTagLabel(tag) }}</span>
          </div>
          <p class="field-hint">标签由完成记录反向生成，不能自行新增或修改；同一技能完成 2 次以上才会出现。</p>
        </div>
      </section>

      <section class="creator-wall">
        <div class="section-heading"><div><span class="section-index">01</span><h2>成就</h2><p>只展示已解锁的成就</p></div></div>
        <AchievementWall :user-id="userId" />
      </section>

      <section class="creator-wall">
        <div class="section-heading">
          <div><span class="section-index">02</span><h2>凭证墙</h2><p>只展示作者设为「公开」且未被撤销的凭证</p></div>
        </div>
        <div v-if="wall.items.length" class="credential-grid">
          <RouterLink v-for="item in wall.items" :key="item.serial" class="credential-link" :to="`/credential/${item.serial}`">
            <CredentialCard :credential="item" compact />
          </RouterLink>
        </div>
        <div v-else class="empty-state">
          <span>集</span>
          <h3>作品集还是空的</h3>
          <p>完成委托后凭证会自动签发，作者把凭证设为「公开」后才会出现在这里。</p>
        </div>

        <div v-if="totalPages > 1" class="pager">
          <button class="button secondary small" :disabled="page <= 1" @click="go(page - 1)"><ChevronLeft :size="14" />上一页</button>
          <span class="muted">{{ page }} / {{ totalPages }}</span>
          <button class="button secondary small" :disabled="page >= totalPages" @click="go(page + 1)">下一页<ChevronRight :size="14" /></button>
        </div>
      </section>
    </template>
  </div>
</template>
