<script setup>
defineProps({
  visible: { type: Boolean, default: false },
  tier: { type: Number, default: 0 },
  hint: { type: Object, default: null },
  failCount: { type: Number, default: 0 },
  ruleHint: { type: String, default: '' },
})

defineEmits(['close', 'show-rule'])
</script>

<template>
  <div v-if="visible" class="frost-drawer-backdrop" @click.self="$emit('close')">
    <aside class="frost-drawer" role="dialog" aria-label="线索">
      <h3>线索</h3>
      <p class="frost-sub">未通关提交 {{ failCount }} 次。卡关越多，线索越具体。</p>

      <div v-if="hint" class="frost-hint" :class="`is-tier-${hint.tier}`">
        <strong>第 {{ hint.tier }} 级线索：</strong>{{ hint.text }}
      </div>
      <p v-else class="frost-sub">继续尝试不同的排列，线索会在你需要的时候出现。</p>

      <div style="margin-top: 18px">
        <button type="button" class="frost-btn" @click="$emit('show-rule')">查看规则说明</button>
      </div>

      <div style="margin-top: 24px; display: flex; justify-content: flex-end">
        <button type="button" class="frost-btn" @click="$emit('close')">关闭</button>
      </div>
    </aside>
  </div>
</template>
