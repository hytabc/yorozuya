<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, errorMessage } from '../api'
import { VISIBILITY_LABELS, formatIssued } from '../credential'

const loading = ref(true)
const error = ref('')
const items = ref([])

const publicCount = computed(() => items.value.filter((item) => item.visibility === 'public' && !item.revoked).length)

async function load() {
  loading.value = true
  try {
    items.value = (await api.get('/credentials/mine')).data
  } catch (err) {
    error.value = errorMessage(err, '无法加载我的凭证')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="profile-credentials-section">
    <div class="section-heading compact">
      <div>
        <span class="section-index">07</span>
        <h2>我的凭证</h2>
        <p>完成委托后自动签发；公开的凭证会出现在你的作品集里</p>
      </div>
      <button type="button" class="button small secondary" :disabled="loading" @click="load">刷新</button>
    </div>

    <p v-if="error" class="form-error">{{ error }}</p>
    <div v-else-if="loading" class="skeleton-list"><div class="skeleton-block" /></div>
    <p v-else-if="!items.length" class="field-hint">还没有凭证。委托完成（委托人与全体接单人都确认）后会自动签发。</p>
    <template v-else>
      <p class="field-hint">共 {{ items.length }} 张，其中公开 {{ publicCount }} 张。</p>
      <ul class="my-credential-list">
        <li v-for="item in items" :key="item.serial" :class="{ revoked: item.revoked }">
          <RouterLink :to="`/credential/${item.serial}`">
            <strong>{{ item.title }}</strong>
            <small>{{ item.serial }} · {{ VISIBILITY_LABELS[item.visibility] }}<template v-if="item.revoked"> · 已撤销</template></small>
            <em class="muted">{{ formatIssued(item) }}</em>
          </RouterLink>
        </li>
      </ul>
    </template>
  </div>
</template>
