<script setup>
import { computed, onMounted, ref } from 'vue'
import { BadgeCheck, Copy, ExternalLink, Plus, RefreshCw, Trash2, TriangleAlert, Unlink } from '@lucide/vue'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import { platformLabel, trustSummary } from '../trust'
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
  verified_at: null,
  last_verified_at: null,
  last_synced_at: null,
  trust_rank: null,
  trust_rank_label: null,
  trust_rank_color: null,
  account_age_label: null,
  platform: null,
  groups: [],
  group_count: 0,
  mutual_friends: null,
  home_world: null,
  manual_worlds: [],
  worlds: [],
  social_synced_at: null,
  stale: false,
  disclosure: {},
  enabled: true,
  allow_new_links: true,
  bot_configured: true,
  challenge: null,
  challenge_locked_until: null,
  last_error: null,
})
const form = ref({ profile: '' })
const worldsDraft = ref([])
const worldInput = ref('')
const canAddWorld = computed(
  () => worldsDraft.value.length < 3 && Boolean(worldInput.value.trim()),
)
const summary = computed(() => trustSummary(status.value))
const challengeExpired = computed(() => {
  const value = status.value.challenge?.expires_at
  return Boolean(value && new Date(value) <= new Date())
})
const locked = computed(() => {
  const value = status.value.challenge_locked_until
  return Boolean(value && new Date(value) > new Date())
})

function formatDate(value) {
  if (!value) return ''
  try {
    return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  } catch {
    return value
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    status.value = { ...status.value, ...(await api.get('/vrchat/status')).data }
    form.value.profile = status.value.profile_url || ''
    worldsDraft.value = [...(status.value.manual_worlds || [])]
  } catch (err) {
    error.value = errorMessage(err, '无法读取 VRChat 绑定状态')
  } finally {
    loading.value = false
  }
}

async function start() {
  busy.value = true
  try {
    status.value = { ...status.value, ...(await api.post('/vrchat/link/start', {
      profile: form.value.profile || status.value.profile_url,
    })).data }
    toast.success('验证码已生成，请写入 VRChat 简介后开始验证')
  } catch (err) {
    toast.error(errorMessage(err, '生成验证码失败'))
  } finally {
    busy.value = false
  }
}

async function check() {
  busy.value = true
  try {
    status.value = { ...status.value, ...(await api.post('/vrchat/link/check')).data }
    toast.success('VRChat 身份已验证')
  } catch (err) {
    toast.error(errorMessage(err, '验证失败'))
    await load()
  } finally {
    busy.value = false
  }
}

async function refresh() {
  busy.value = true
  try {
    status.value = { ...status.value, ...(await api.post('/vrchat/refresh')).data }
    toast.success(status.value.verified ? '资料已刷新，验证仍然有效' : '资料已刷新；简介中未找到验证码')
  } catch (err) {
    toast.error(errorMessage(err, '刷新失败'))
  } finally {
    busy.value = false
  }
}

async function copyCode() {
  const code = status.value.challenge?.code
  if (!code) return
  try {
    await navigator.clipboard.writeText(code)
    toast.success('验证码已复制')
  } catch {
    toast.error('复制失败，请手动选择验证码复制')
  }
}

async function unlink() {
  if (!window.confirm('解绑后会立即清空展示信息与披露设置，已签发的凭证会标注「身份来源已解绑」。继续吗？')) return
  busy.value = true
  try {
    status.value = { ...status.value, ...(await api.post('/vrchat/unlink')).data }
    form.value = { profile: '' }
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
    form.value = { profile: '' }
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
  worldsDraft.value = [...(status.value.manual_worlds || [])]
}

function addWorld() {
  const value = worldInput.value.trim()
  if (!value || worldsDraft.value.length >= 3) return
  if (!worldsDraft.value.includes(value)) worldsDraft.value = [...worldsDraft.value, value]
  worldInput.value = ''
}

function removeWorld(value) {
  worldsDraft.value = worldsDraft.value.filter((item) => item !== value)
}

async function saveWorlds() {
  busy.value = true
  try {
    const { data } = await api.patch('/vrchat/worlds', { worlds: worldsDraft.value })
    status.value = { ...status.value, ...data }
    worldsDraft.value = [...(data.manual_worlds || [])]
    toast.success('常驻 World 已保存')
  } catch (err) {
    toast.error(errorMessage(err, '保存常驻 World 失败'))
  } finally {
    busy.value = false
  }
}

onMounted(load)
defineExpose({ load })
</script>

<template>
  <div class="profile-vrchat-section">
    <div class="section-heading compact">
      <div>
        <span class="section-index">08</span>
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
            <BadgeCheck v-if="status.verified" :size="16" />
            <TriangleAlert v-else :size="16" />
            <strong>{{ summary?.text }}</strong>
            <span v-if="status.verified" class="muted">已验证：资料由 VRChat 简介验证码核对。</span>
            <span v-else class="muted">未验证：请把验证码写入 VRChat 简介后完成验证。</span>
          </p>
          <p v-if="status.stale" class="form-error">资料可能已过期，建议点击“刷新资料”。</p>
          <p v-if="!status.verified && status.last_verified_at" class="field-hint">
            曾于 {{ formatDate(status.last_verified_at) }} 验证；当前简介中没有找到验证码。
          </p>
          <p v-if="status.profile_url" class="field-hint">
            主页：<a :href="status.profile_url" target="_blank" rel="noopener noreferrer">{{ status.profile_url }} <ExternalLink :size="12" /></a>
          </p>

          <div v-if="status.challenge" class="notice info-notice">
            <strong>把验证码保存到 VRChat 个人简介</strong>
            <p>打开 VRChat 官网的个人资料，把下面这串码完整保存到简介里，然后点击“开始验证”。</p>
            <p class="vrchat-challenge-code"><code>{{ status.challenge.code }}</code><button type="button" class="button small secondary" @click="copyCode"><Copy :size="14" />复制</button></p>
            <p class="field-hint">有效期至 {{ formatDate(status.challenge.expires_at) }}；建议把验证码放在简介最前面，避免被“Read More”折叠或长度截断，保存后稍等 10-60 秒再验证。</p>
            <p v-if="challengeExpired" class="form-error">验证码已过期，请重新生成。</p>
            <p v-else-if="locked" class="form-error">验证失败次数过多，请 {{ formatDate(status.challenge_locked_until) }} 后再试。</p>
            <div class="dialog-actions">
              <button type="button" class="button" :disabled="busy || challengeExpired || locked" @click="check">{{ busy ? '验证中…' : '开始验证' }}</button>
              <button type="button" class="button secondary" :disabled="busy" @click="start">重新生成验证码</button>
            </div>
          </div>

          <div v-if="status.verified" class="vrchat-facts">
            <span v-if="status.trust_rank_label">Trust Rank：<strong :style="{ color: status.trust_rank_color }">{{ status.trust_rank_label }}</strong></span>
            <span v-if="status.account_age_label">账号年龄：<strong>{{ status.account_age_label }}</strong></span>
            <span v-if="status.platform">常用平台：<strong>{{ platformLabel(status.platform) }}</strong></span>
            <span v-if="status.mutual_friends !== null && status.mutual_friends !== undefined">站点共同好友：<strong>{{ status.mutual_friends }}</strong> 位</span>
            <span v-if="status.group_count">公开社群：<strong>{{ status.group_count }}</strong> 个</span>
            <span v-if="status.worlds?.length">常驻 World：<strong>{{ status.worlds.map((world) => world.name).join('、') }}</strong></span>
            <span v-if="status.last_synced_at">最近同步：<strong>{{ formatDate(status.last_synced_at) }}</strong></span>
          </div>

          <div v-if="status.verified" class="vrchat-worlds-editor">
            <div class="section-heading compact">
              <div>
                <h3>常驻 World</h3>
                <p class="field-hint">自动读取主页 World；也可以手动补充，最多 3 个。开启“常驻 World”披露后其他人可见。</p>
              </div>
            </div>
            <p v-if="status.home_world" class="field-hint">
              主页 World：<strong>{{ status.home_world.name }}</strong>（自动读取，不占用手动名额）
            </p>
            <p v-else class="field-hint">暂未读取到主页 World；可以手动填写常驻 World。</p>
            <div v-if="worldsDraft.length" class="vrchat-world-chips">
              <span v-for="world in worldsDraft" :key="world" class="facet-chip static">
                {{ world }}
                <button type="button" class="text-link" :aria-label="`移除 ${world}`" @click="removeWorld(world)">×</button>
              </span>
            </div>
            <div class="vrchat-world-editor">
              <input v-model.trim="worldInput" maxlength="100" placeholder="输入 World 名称，例如：咖啡厅" @keyup.enter="addWorld" />
              <button type="button" class="button small secondary" :disabled="!canAddWorld || busy" @click="addWorld"><Plus :size="14" />添加</button>
              <button type="button" class="button small" :disabled="busy" @click="saveWorlds">保存常驻 World</button>
            </div>
          </div>

          <p v-if="status.last_error && !status.challenge" class="form-error">{{ status.last_error }}</p>

          <div class="dialog-actions">
            <button v-if="!status.challenge" type="button" class="button small" :disabled="busy" @click="start">
              {{ status.verified ? '重新验证' : '生成验证码' }}
            </button>
            <button type="button" class="button small secondary" :disabled="busy" @click="showDisclosure = true">披露设置</button>
            <button v-if="status.profile_url" type="button" class="button small secondary" :disabled="busy" @click="refresh"><RefreshCw :size="14" />刷新资料</button>
            <button type="button" class="button small secondary" :disabled="busy" @click="unlink"><Unlink :size="14" />解绑</button>
            <button type="button" class="button small danger" :disabled="busy" @click="removeData"><Trash2 :size="14" />删除我的 VRChat 数据</button>
          </div>
        </div>

        <form v-else class="form-stack" @submit.prevent="start">
          <label>
            VRChat 个人主页链接或用户 ID
            <input v-model.trim="form.profile" required minlength="4" maxlength="255" placeholder="https://vrchat.com/home/user/usr_…" />
            <small class="field-hint">在 VRChat 官网打开自己的主页复制地址即可。同一主页不能被两个本站账号绑定。</small>
          </label>
          <div class="notice info-notice">
            <strong>通过简介验证码确认是你本人</strong>
            <p>服务端会用站点机器人账号读取你的公开资料；<strong>不会保存你的 VRChat 密码</strong>。生成验证码后，把它写入 VRChat 个人简介，再由服务端核对。</p>
            <p v-if="!status.bot_configured" class="form-error">站点尚未配置 VRChat 机器人。请在根目录 .env 设置 VRCHAT_BOT_AUTH_COOKIE，或 VRCHAT_BOT_USERNAME + VRCHAT_BOT_PASSWORD（2FA 再加 VRCHAT_BOT_TOTP_SECRET），然后重启后端。</p>
          </div>
          <div class="dialog-actions">
            <button type="button" class="button secondary" :disabled="busy" @click="load">重新读取</button>
            <button class="button" :disabled="busy || !status.allow_new_links || !status.bot_configured">{{ busy ? '读取中…' : '生成验证码' }}</button>
          </div>
          <p v-if="!status.allow_new_links" class="field-hint">当前暂停接受新的 VRChat 绑定。</p>
        </form>
      </template>
    </template>

    <TrustDisclosureDialog v-if="showDisclosure" :disclosure="status.disclosure" @close="showDisclosure = false" @saved="saved" />
  </div>
</template>
