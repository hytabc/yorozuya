<script setup>
import { Award } from '@lucide/vue'
import AchievementWall from '../components/AchievementWall.vue'
</script>

<template>
  <div class="page inner-page achievements-page">
    <div class="page-title">
      <div>
        <span class="eyebrow"><Award :size="15" />ACHIEVEMENTS</span>
        <h1>成就</h1>
        <p>完成委托、获得好评、参与社区都会解锁成就并获得终身积分。</p>
      </div>
    </div>

    <section class="section-heading">
      <div><span class="section-index">01</span><h2>成就墙</h2><p>打开页面会自动补发已达成但未记录的成就</p></div>
    </section>
    <AchievementWall />
  </div>
</template>
