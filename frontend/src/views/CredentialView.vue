<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Flag } from '@lucide/vue'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'
import { VISIBILITY_HINTS, VISIBILITY_LABELS, VISIBILITY_OPTIONS, isSerialValid } from '../credential'
import CredentialCard from '../components/CredentialCard.vue'
import FeedbackDialog from '../components/FeedbackDialog.vue'

const route = useRoute()
const auth = useAuthStore()
const toast = useToast()
const loading = ref(true)
const error = ref('')
const credential = ref(null)
const showReport = ref(false)
const busy = ref(false)

const serial = computed(() => String(route.params.serial || ''))
const isOwner = computed(() => Boolean(credential.value) && auth.user?.id === credential.value.taker_id)

async function load() {
  loading.value = true
  error.value = ''
  credential.value = null
  if (!isSerialValid(serial.value)) {
    error.value = '凭证编号格式不正确'
    loading.value = false
    return
  }
  try {
    credential.value = (await api.get(`/credentials/${serial.value}`)).data
  } catch (err) {
    error.value = errorMessage(err, '无法加载该凭证')
  } finally {
    loading.value = false
  }
}

async function changeVisibility(value) {
  if (busy.value || !credential.value) return
  busy.value = true
  try {
    credential.value = (await api.patch(
      `/credentials/${credential.value.serial}/visibility`,
      { visibility: value },
    )).data
    toast.success(`已切换为「${VISIBILITY_LABELS[value]}」`)
  } catch (err) {
    toast.error(errorMessage(err, '修改失败'))
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page inner-page credential-page">
    <section class="section-heading">
      <div>
        <span class="section-index">CREDENTIAL</span>
        <h2>委托凭证</h2>
        <p>凭证编号可在站内验证，证明「这次委托在站内完成了」。</p>
      </div>
    </section>

    <div v-if="loading" class="credential-skeleton skeleton-block" />
    <div v-else-if="error" class="empty-state">
      <span>凭</span>
      <h3>{{ error }}</h3>
      <p>请检查链接是否完整；私有的凭证只有接单人本人可以查看。</p>
      <RouterLink class="button secondary" to="/">返回委托大厅</RouterLink>
    </div>
    <template v-else-if="credential">
      <CredentialCard :credential="credential" />

      <section v-if="isOwner" class="credential-owner-panel">
        <h3>谁能看到这张凭证？</h3>
        <p class="field-hint">可见性由服务端校验，不会只靠前端隐藏。</p>
        <div class="mode-options">
          <label v-for="option in VISIBILITY_OPTIONS" :key="option" class="mode-option" :class="{ active: credential.visibility === option }">
            <input type="radio" name="credential-visibility" :value="option" :checked="credential.visibility === option" :disabled="busy" @change="changeVisibility(option)" />
            <span class="mode-option-text"><strong>{{ VISIBILITY_LABELS[option] }}</strong><small>{{ VISIBILITY_HINTS[option] }}</small></span>
          </label>
        </div>
      </section>

      <p class="credential-report">
        <button type="button" class="text-link" @click="showReport = true"><Flag :size="14" />这张凭证有问题？举报伪造或刷单</button>
      </p>
    </template>

    <FeedbackDialog v-if="showReport" @close="showReport = false" />
  </div>
</template>
