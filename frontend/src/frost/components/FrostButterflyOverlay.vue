<script setup>
defineProps({
  butterfly: { type: Object, required: true },
})

defineEmits(['dismiss'])
</script>

<template>
  <div class="frost-butterfly" role="dialog" aria-modal="true" aria-label="因果涟漪">
    <div class="frost-butterfly-inner">
      <h3>因果涟漪</h3>
      <p>{{ butterfly.revealText }}</p>
      <div style="display: flex; justify-content: flex-end; margin-top: 18px">
        <button type="button" class="frost-btn is-primary" @click="$emit('dismiss')">继续</button>
      </div>
    </div>
  </div>
</template>
