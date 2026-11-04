<script setup>
import { computed } from 'vue'
import { Check } from '@lucide/vue'

const props = defineProps({
  label: { type: String, required: true },
  // 选项可以是字符串，也可以是 { value, label }；后端目录接口返回后者。
  options: { type: Array, default: () => [] },
  modelValue: { type: Array, default: () => [] },
  max: { type: Number, default: 0 },
  single: Boolean,
  hint: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const selected = computed(() => props.modelValue || [])
const normalized = computed(() =>
  props.options.map((option) =>
    typeof option === 'string' ? { value: option, label: option } : option,
  ),
)
const limitReached = computed(() => Boolean(props.max) && selected.value.length >= props.max)

function toggle(value) {
  if (props.single) {
    emit('update:modelValue', selected.value.includes(value) ? [] : [value])
    return
  }
  const next = selected.value.includes(value)
    ? selected.value.filter((item) => item !== value)
    : [...selected.value, value]
  if (!selected.value.includes(value) && props.max && next.length > props.max) return
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="facet-field">
    <span class="taker-label">
      {{ label }}
      <small v-if="max" class="muted">（最多 {{ max }} 个）</small>
    </span>
    <div class="facet-chip-row" role="group" :aria-label="label">
      <button
        v-for="option in normalized"
        :key="option.value"
        type="button"
        class="facet-chip"
        :class="{ active: selected.includes(option.value) }"
        :aria-pressed="selected.includes(option.value)"
        :disabled="!single && !selected.includes(option.value) && limitReached"
        @click="toggle(option.value)"
      >
        <Check v-if="selected.includes(option.value)" :size="12" />
        {{ option.label }}
      </button>
    </div>
    <small v-if="hint" class="field-hint">{{ hint }}</small>
  </div>
</template>
