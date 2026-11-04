<script setup>
import { computed, onMounted, ref } from 'vue'
import { BadgeCheck, ExternalLink, Trash2, Unlink } from '@lucide/vue'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import { trustSummary } from '../trust'
import TrustDisclosureDialog from './TrustDisclosureDialog.vue'

const toast = useToast()
const loading = ref(true)
const busy = ref(false)
const showDisclosure = ref(false)
const error = ref('')
const status = ref({
  bound: false,
  status: null,
  display_name: null,
  profile_url: null,
  verified: false,
  linked_at: null,
  disclosure: {},
  enabled: true,
  allow_new_links: true,
})
const form = ref({ display_name: '', profile: '' })
const summary = computed(() => trustSummary(status.value))

async function load() {
  loading.value = true
  error.value = ''
  try {
    status.value = (await api.get('/vrchat/status')).data
    form.value.display_name = status.value.display_name || ''
    form.value.profile = status.value.profile_url || ''
  } catch (err) {
    error.value = errorMessage(err, '无法读取 VRChat 绑定状态')
  } finally {
    loading.value = false
  }
}

async function bind() {
  busy.value = true
  try {
    status.value = { ...status.value, ...(await api.post('/vrchat/link', {
      display_name: form.value.display_name,
      profile: form.value.profile,
    })).data }
    toast.success('已保存 VRChat 身份（未验证）')
  } catch (err) {
    toast.error(errorMessage(err, '绑定失败'))
  } finally {
    busy.value = false
  }
}

async function unlink() {
  if (!window.confirm('解绑后会立即清空展示信息与披露设置，已签发的凭证会标注「身份来源已解绑」。继续吗？')) return
  busy.value = true
  try {
    status.value = { ...status.value, ...(await api.post('/vrchat/unlink')).data }
    form.value = { display_name: '', profile: '' }
    toast.success('已解绑 VRChat 身份')
  } catch (err) {
    toast.error(errorMessage(err, '解绑失败'))
  } finally {
    busy.value = false
  }
}

async function removeData() {
  if (!window.confirm('这会彻底删除你的 VRChat 身份数据，且无法恢复。继续吗？')) return
  busy.value = true
  try {
    await api.delete('/vrchat/data')
    form.value = { display_name: '', profile: '' }
    toast.success('已删除 VRChat 数据')
    await load()
  } catch (err) {
    toast.error(errorMessage(err, '删除失败'))
  } finally {
    busy.value = false
  }
}

function saved(next) {
  status.value = { ...status.value, ...next }
}

onMounted(load)
defineExpose({ load })
</script>

<template>
  <div class="profile-vrchat-section">
    <div class="section-heading compact">
      <div>
        <span class="section-index">06</span>
        <h2>VRChat 身份</h2>
        <p>自愿绑定，随时解绑；未绑定时不影响发布与接取委托</p>
      </div>
    </div>

    <p v-if="error" class="form-error">{{ error }}</p>
    <div v-else-if="loading" class="skeleton-list"><div class="skeleton-block" /></div>

    <template v-else>
      <div v-if="!status.enabled" class="notice info-notice">
        <strong>VRChat 身份功能当前已关闭</strong>
        <p>站点暂不接受绑定或展示；已有数据不会被删除。</p>
      </div>

      <template v-else>
        <div v-if="status.bound" class="vrchat-bound">
          <p class="vrchat-status">
            <BadgeCheck :size="16" />
            <strong>{{ summary?.text }}</strong>
            <span class="muted">标注「未验证」：由你手动填写，本站未接入 VRChat 官方认证。</span>
          </p>
          <p v-if="status.profile_url" class="field-hint">
            主页：<a :href="status.profile_url" target="_blank" rel="noopener noreferrer">{{ status.profile_url }} <ExternalLink :size="12" /></a>
          </p>
          <div class="dialog-actions">
            <button type="button" class="button small secondary" @click="showDisclosure = true">披露设置</button>
            <button type="button" class="button small secondary" :disabled="busy" @click="unlink"><Unlink :size="14" />解绑</button>
            <button type="button" class="button small danger" :disabled="busy" @click="removeData"><Trash2 :size="14" />删除我的 VRChat 数据</button>
          </div>
        </div>

        <form v-else class="form-stack" @submit.prevent="bind">
          <label>
            在 VRChat 中的显示名
            <input v-model.trim="form.display_name" required maxlength="64" placeholder="例如：ColdRain" />
          </label>
          <label>
            个人主页链接或用户 ID
            <input v-model.trim="form.profile" required minlength="4" maxlength="255" placeholder="https://vrchat.com/home/user/usr_…" />
            <small class="field-hint">在 VRChat 官网打开自己的主页复制地址即可。同一主页不能被两个本站账号绑定。</small>
          </label>
          <div class="notice info-notice">
            <strong>这是「软绑定」，不是官方认证</strong>
            <p>本站不会保存你的 VRChat 密码，也不会调用 VRChat API。Trust Rank、账号年龄、共同好友等数据要等接入官方同步后才可能提供，当前不会展示，也不会伪造。</p>
          </div>
          <div class="dialog-actions">
            <button type="button" class="button secondary" :disabled="busy" @click="load">重新读取</button>
            <button class="button" :disabled="busy || !status.allow_new_links">{{ busy ? '保存中…' : '保存 VRChat 身份' }}</button>
          </div>
          <p v-if="!status.allow_new_links" class="field-hint">当前暂停接受新的 VRChat 绑定。</p>
        </form>
      </template>
    </template>

    <TrustDisclosureDialog v-if="showDisclosure" :disclosure="status.disclosure" @close="showDisclosure = false" @saved="saved" />
  </div>
</template>
