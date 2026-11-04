<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Star, TriangleAlert } from '@lucide/vue'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'

const props = defineProps({ taskId: { type: Number, required: true } })
const toast = useToast()
const loading = ref(true)
const busy = ref(false)
const data = ref({ deadline: null, role: null, can_rate: false, slots: [] })
// rateeId -> 正在编辑的表单；null 表示不在编辑。
const editing = ref(null)
const appealFor = ref(null)
const appealReason = ref('')
const appealing = ref(false)
const draft = reactive({ stars_half: 10, comment: '', reason_code: '' })
const REASONS = [
  { value: 'not_delivered', label: '未交付' },
  { value: 'breach', label: '严重失约' },
  { value: 'delay', label: '恶意拖延' },
  { value: 'harassment', label: '言语骚扰' },
]
const deadlineText = computed(() => {
  if (!data.value.deadline) return ''
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(data.value.deadline))
})
const isNegative = computed(() => draft.stars_half <= 4)
const canSubmit = computed(() => {
  if (draft.stars_half === 0 && !draft.reason_code) return false
  if (isNegative.value && draft.comment.trim().length < 15) return false
  return draft.comment.trim().length <= 200
})

function starsText(half) {
  return `${(half / 2).toFixed(half % 2 === 0 ? 0 : 1)} 星`
}

function setStars(half) {
  draft.stars_half = half
  if (half > 0) draft.reason_code = ''
}

async function load() {
  loading.value = true
  try {
    data.value = (await api.get(`/tasks/${props.taskId}/ratings`)).data
  } catch {
    data.value = { deadline: null, role: null, can_rate: false, slots: [] }
  } finally {
    loading.value = false
  }
}

function startRate(slot) {
  editing.value = slot.counterpart.id
  draft.stars_half = 10
  draft.comment = ''
  draft.reason_code = ''
}

function startEdit(slot) {
  editing.value = slot.counterpart.id
  draft.stars_half = Math.round(slot.my_rating.stars * 2)
  draft.comment = slot.my_rating.comment || ''
  draft.reason_code = slot.my_rating.reason_code || ''
}

async function submit(slot) {
  if (!canSubmit.value) return
  busy.value = true
  try {
    const payload = {
      stars_half: draft.stars_half,
      comment: draft.comment.trim() || null,
      reason_code: draft.reason_code || null,
    }
    if (slot.my_rating) {
      await api.patch(`/tasks/${props.taskId}/ratings/${slot.counterpart.id}`, payload)
      toast.success('评价已更新')
    } else {
      await api.post(`/tasks/${props.taskId}/ratings`, { ...payload, ratee_id: slot.counterpart.id })
      toast.success('评价已提交，对方评价后即可互相查看')
    }
    editing.value = null
    await load()
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function submitAppeal(ratingId) {
  if (appealReason.value.trim().length < 20) return
  appealing.value = true
  try {
    await api.post(`/ratings/${ratingId}/appeal`, { reason: appealReason.value.trim() })
    toast.success('申诉已提交，管理员复核后会更新结果')
    appealFor.value = null
    appealReason.value = ''
    await load()
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    appealing.value = false
  }
}

onMounted(load)
</script>

<template>
  <section v-if="!loading && data.slots.length" class="rating-section">
    <h4>互相评价<span v-if="deadlineText" class="muted"> · {{ deadlineText }} 前可评价</span></h4>
    <article v-for="slot in data.slots" :key="slot.counterpart.id" class="rating-slot">
      <header>
        <strong>{{ slot.counterpart.nickname }}</strong>
        <span v-if="slot.my_rating" class="rating-stars"><Star :size="14" />{{ starsText(slot.my_rating.stars * 2) }}</span>
        <button v-if="slot.can_edit && editing !== slot.counterpart.id" type="button" class="text-link" @click="startEdit(slot)">修改</button>
      </header>

      <p v-if="slot.my_rating && editing !== slot.counterpart.id" class="rating-comment">
        {{ slot.my_rating.comment || '未填写文字' }}
        <span v-if="slot.my_rating.reason_label" class="rating-reason">{{ slot.my_rating.reason_label }}</span>
      </p>

      <div v-if="editing === slot.counterpart.id" class="rating-form">
        <div class="rating-input" role="radiogroup" aria-label="评分">
          <button v-for="half in 10" :key="half" type="button" role="radio" :aria-checked="draft.stars_half === half"
                  class="rating-half" :class="{ active: draft.stars_half >= half }" @click="setStars(half)">
            <Star :size="18" />
          </button>
          <span class="rating-value">{{ starsText(draft.stars_half) }}</span>
          <button v-if="draft.stars_half > 0" type="button" class="text-link" @click="setStars(0)">改为 0 星</button>
        </div>
        <label v-if="draft.stars_half === 0">差评原因
          <select v-model="draft.reason_code">
            <option value="" disabled>请选择原因</option>
            <option v-for="item in REASONS" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <label>评价内容<small v-if="isNegative" class="muted">（2 星及以下需至少 15 字）</small>
          <textarea v-model="draft.comment" rows="3" maxlength="200" :placeholder="isNegative ? '请说明具体发生了什么，方便对方改进' : '选填，说说这次协作的感受'" />
          <small>{{ draft.comment.length }}/200</small>
        </label>
        <p v-if="!canSubmit" class="rating-hint"><TriangleAlert :size="14" />{{ draft.stars_half === 0 ? '请选择差评原因' : '请至少填写 15 字说明' }}</p>
        <div class="rating-actions">
          <button type="button" class="button small" :disabled="busy || !canSubmit" @click="submit(slot)">{{ busy ? '提交中…' : (slot.my_rating ? '保存修改' : '提交评价') }}</button>
          <button type="button" class="button secondary small" :disabled="busy" @click="editing = null">取消</button>
        </div>
      </div>

      <div v-else-if="slot.can_rate" class="rating-actions">
        <button type="button" class="button small" @click="startRate(slot)">评价 {{ slot.counterpart.nickname }}</button>
      </div>

      <div v-if="slot.their_rating" class="rating-received">
        <p v-if="slot.their_rating.revoked" class="muted rating-wait">对方给你的这条评价已被管理员撤销，不再计入评分。</p>
        <template v-else>
          <p class="rating-comment their">
            <span class="muted">对方对你的评价：</span><span class="rating-stars"><Star :size="13" />{{ starsText(slot.their_rating.stars * 2) }}</span>
            {{ slot.their_rating.comment || '' }}
            <span v-if="slot.their_rating.reason_label" class="rating-reason">{{ slot.their_rating.reason_label }}</span>
          </p>
          <button v-if="slot.their_rating.stars <= 2" type="button" class="text-link" @click="appealFor = appealFor === slot.their_rating.id ? null : slot.their_rating.id">申请复核</button>
          <div v-if="appealFor === slot.their_rating.id" class="rating-form">
            <label>申诉理由（至少 20 字）
              <textarea v-model="appealReason" rows="3" maxlength="500" placeholder="说明实际发生了什么，方便管理员核实" />
              <small>{{ appealReason.length }}/500</small>
            </label>
            <div class="rating-actions">
              <button type="button" class="button small" :disabled="appealing || appealReason.trim().length < 20" @click="submitAppeal(slot.their_rating.id)">{{ appealing ? '提交中…' : '提交申诉' }}</button>
              <button type="button" class="button secondary small" @click="appealFor = null">取消</button>
            </div>
          </div>
        </template>
      </div>
      <p v-else class="muted rating-wait">对方还没评价；双方都提交后会立即互相可见，否则 7 天后自动公开。</p>
    </article>
  </section>
</template>
