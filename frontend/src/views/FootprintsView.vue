<script setup>
import { onMounted, ref } from 'vue'
import { History } from '@lucide/vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import LifeRecords from '../components/LifeRecords.vue'

const auth = useAuthStore()
const ledger = ref({ total: 0, page: 1, page_size: 20, items: [] })
const ledgerBusy = ref(false)

async function loadLedger(page = 1) {
  ledgerBusy.value = true
  try {
    const { data } = await api.get('/points/ledger', { params: { page, page_size: 20 } })
    ledger.value = page === 1 ? data : { ...data, items: [...ledger.value.items, ...data.items] }
  } catch { /* 流水加载失败不影响页面 */ } finally { ledgerBusy.value = false }
}

onMounted(() => loadLedger())
</script>

<template>
  <div class="page inner-page footprints-page">
    <div class="page-title">
      <div>
        <span class="eyebrow"><History :size="15" />FOOTPRINTS</span>
        <h1>足迹</h1>
        <p>累计完成、评分与积分流水；只统计真实委托，官方委托不计入。</p>
      </div>
    </div>

    <section class="section-heading">
      <div><span class="section-index">01</span><h2>人生记录</h2><p>等级、完成数、评分与常做分类</p></div>
    </section>
    <LifeRecords :user-id="auth.user.id" />

    <section class="section-heading">
      <div><span class="section-index">02</span><h2>积分流水</h2><p>仅本人可见</p></div>
    </section>
    <ul class="ledger-list">
      <li v-for="item in ledger.items" :key="item.id">
        <span>{{ item.kind_label }}<small v-if="item.note" class="muted"> · {{ item.note }}</small></span>
        <strong :class="{ minus: item.wallet_delta < 0 }">{{ item.wallet_delta > 0 ? '+' : '' }}{{ item.wallet_delta }}</strong>
      </li>
    </ul>
    <p v-if="!ledger.items.length" class="muted">还没有积分记录。</p>
    <button v-if="ledger.items.length < ledger.total" type="button" class="button secondary small" :disabled="ledgerBusy" @click="loadLedger(ledger.page + 1)">{{ ledgerBusy ? '加载中…' : '加载更多' }}</button>
  </div>
</template>
