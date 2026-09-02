<script setup>
import { CircleCheck, CircleAlert } from 'lucide-vue-next'
import { toasts } from '../composables/toast'
</script>

<template>
  <div class="toast-host" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="toast in toasts" :key="toast.id" class="toast" :class="toast.type">
        <CircleAlert v-if="toast.type === 'error'" :size="18" />
        <CircleCheck v-else :size="18" />
        <span>{{ toast.message }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>

