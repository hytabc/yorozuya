<script setup>
import { History } from 'lucide-vue-next'
</script>

<template>
  <div class="page inner-page versions-page">
    <div class="page-title">
      <div><span class="eyebrow"><History :size="15" /> RELEASE NOTES</span><h1>版本更新</h1><p>万事屋委托站的版本记录与功能变更</p></div>
    </div>
    <article class="version-entry">
      <h2>V0.1-Beta</h2>
      <time datetime="2026-09-08">2026-09-08 · 首个公开测试版本</time>
      <ul>
        <li>委托大厅：发布、接取、多人协作、完成确认、取消、密码、指定与匿名委托。</li>
        <li>社区：成员名录、留言板、反馈、举报、个人资料与图片审核。</li>
        <li>地图推荐：提交、点赞、举报、实拍图片上传与审核展示。</li>
        <li>砂糖社：公开档案、图片展示、双向确认配对与关系记录。</li>
        <li>运营能力：公告中心、页面活跃数据、内容审核与分级权限管理。</li>
      </ul>
    </article>
  </div>
</template>
