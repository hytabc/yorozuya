<script setup>
import { reactive, ref, computed, onMounted, onUnmounted } from 'vue'
import { Check, TriangleAlert, X } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '../api'
import { track } from '../analytics'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'
import { CATEGORIES, TASK_SKILLS, TASK_PLATFORMS, ATMOSPHERE_GROUPS, FACET_LIMITS } from '../constants'
import { buildFacets } from '../facets'
import { needsAtmosphereAck, openAtmosphereGate } from '../composables/useAtmosphere'
import TaskFacetChips from './TaskFacetChips.vue'
import UserTitleTag from './UserTitleTag.vue'

const emit = defineEmits(['close', 'created'])
const auth = useAuthStore()
const router = useRouter()
const toast = useToast()
const hasContact = computed(() => Boolean(auth.user?.qq))
const busy = ref(false)
const unlimited = ref(false)
const categories = CATEGORIES
const directory = ref({ staff: [], volunteers: [] })
const designated = ref(false)
const designatedIds = ref([])
const designatedUsers = computed(() => [...directory.value.staff, ...directory.value.volunteers])
const expiryOptions = [1, 2, 3, 5, 10]
// 模块化标签：全部可选，不填写也能正常发布（旧委托兼容）。
const skills = ref([])
const platforms = ref([])
const worlds = ref([])
const worldInput = ref('')
const worldError = ref('')
const atmosphere = reactive(Object.fromEntries(ATMOSPHERE_GROUPS.map((group) => [group.key, []])))
const atmosphereValues = computed(() => Object.values(atmosphere).flat())

function addWorld() {
  const value = worldInput.value.trim()
  if (!value) return
  if (worlds.value.length >= FACET_LIMITS.world) {
    worldError.value = `参考 World 最多选择 ${FACET_LIMITS.world} 个`
    return
  }
  if (value.length > 60) {
    worldError.value = '参考 World 名称不能超过 60 个字符'
    return
  }
  if (!worlds.value.includes(value)) worlds.value.push(value)
  worldInput.value = ''
  worldError.value = ''
}
function removeWorld(value) {
  worlds.value = worlds.value.filter((item) => item !== value)
  worldError.value = ''
}
const form = reactive({
  title: '',
  description: '',
  category: '',
  scale: 'small',
  bounty_points: 0,
  required_takers: 1,
  is_anonymous: false,
  expires_in_days: 1,
})
// 积分规则由服务端下发，避免档位/系数在前后端各写一份。
const rules = ref({
  scale_points: { small: 5, medium: 15, large: 40 },
  scale_labels: { small: '小', medium: '中', large: '大' },
  category_factors: {},
  bounty_min: 0,
  bounty_max: 200,
  advance_ratio: 0.6,
})
const wallet = computed(() => auth.user?.wallet_points || 0)
const bountyLimit = computed(() => Math.min(rules.value.bounty_max, wallet.value))
const previewBase = computed(() => {
  if (!form.category) return rules.value.scale_points[form.scale] || 0
  const factor = rules.value.category_factors[form.category] ?? 1
  return Math.max(1, Math.round((rules.value.scale_points[form.scale] || 5) * factor))
})

async function submit() {
  if (!hasContact.value) {
    toast.error('发布委托需要先添加联系方式，请先到个人设置填写 QQ 号')
    emit('close')
    router.push('/profile')
    return
  }
  busy.value = true
  try {
    // 服务端同样会校验（403），这里先拦一次避免用户白填一遍表单。
    if (needsAtmosphereAck()) {
      emit('close')
      openAtmosphereGate()
      return
    }
    const payload = {
      ...form,
      required_takers: unlimited.value ? null : form.required_takers,
      designated_user_ids: designated.value ? designatedIds.value : [],
      facets: buildFacets({
        skills: skills.value,
        platforms: platforms.value,
        worlds: worlds.value,
        atmosphere: atmosphereValues.value,
      }),
    }
    const { data } = await api.post('/tasks', payload)
    toast.success(designated.value ? '指定委托已发布，等待被指定人员响应' : (unlimited.value || form.required_takers === 1 ? '委托已发布' : '委托已发布，凑齐人数后自动开始'))
    track('task.create')
    emit('created', data)
  } catch (error) { toast.error(errorMessage(error)) } finally { busy.value = false }
}
function onKey(event) { if (event.key === 'Escape') emit('close') }
function goAddContact() {
  emit('close')
  router.push('/profile')
}
onMounted(() => { document.body.classList.add('modal-open'); window.addEventListener('keydown', onKey) })
onMounted(async () => {
  try { directory.value = (await api.get('/staff')).data } catch { directory.value = { staff: [], volunteers: [] } }
  try { rules.value = { ...rules.value, ...(await api.get('/points/rules')).data } } catch { /* 用内置规则兜底 */ }
})
onUnmounted(() => { document.body.classList.remove('modal-open'); window.removeEventListener('keydown', onKey) })
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="dialog create-dialog" role="dialog" aria-modal="true" aria-label="发布新委托">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>
      <div class="dialog-heading"><span class="eyebrow">NEW REQUEST</span><h2>发布新委托</h2><p>把交付目标和时间说清楚，更容易遇到合适的人。</p></div>
      <div v-if="!hasContact" class="notice risk-notice" role="alert">
        <strong><TriangleAlert :size="17" />发布委托需要先添加联系方式</strong>
        <p>接单人需要靠 QQ 联系你确认细节并完成交付，请先在个人设置中填写 QQ 号。</p>
        <button type="button" class="button small secondary" @click="goAddContact">去个人设置添加联系方式</button>
      </div>
      <form class="form-stack" @submit.prevent="submit">
        <label>委托标题<input v-model.trim="form.title" required minlength="2" maxlength="80" placeholder="一句话说明需要什么" /></label>
        <label>详细说明<textarea v-model.trim="form.description" required minlength="10" maxlength="3000" rows="6" placeholder="说明背景、具体要求和交付方式"></textarea><small>{{ form.description.length }}/3000</small></label>
        <label>委托分类<select v-model="form.category" required><option value="" disabled>请选择委托类型</option><option v-for="item in categories" :key="item">{{ item }}</option></select></label>
        <div class="form-row">
          <label>委托规模<select v-model="form.scale"><option v-for="(label, key) in rules.scale_labels" :key="key" :value="key">{{ label }}（基础 {{ rules.scale_points[key] }} 分）</option></select></label>
          <label>额外悬赏<input v-model.number="form.bounty_points" type="number" :min="rules.bounty_min" :max="bountyLimit" step="1" /><small class="field-hint">当前可用 {{ wallet }} 分，最多可托管 {{ bountyLimit }} 分；悬赏直接压给对方，取消或过期会退回。</small></label>
        </div>
        <div class="point-preview">
          <strong>完成后接单人可得 {{ previewBase }} 分<template v-if="form.bounty_points > 0"> + 悬赏 {{ form.bounty_points }} 分</template></strong>
          <small>系统积分按评价星级结算（5 星全额，0 星为 0），完成时先发 {{ Math.round(rules.advance_ratio * 100) }}%。</small>
        </div>
        <div class="facet-section">
          <span class="eyebrow">技能与平台（可选）</span>
          <TaskFacetChips v-model="skills" label="技能" :options="TASK_SKILLS" :max="FACET_LIMITS.skill" hint="选填，帮助合适的人更快找到这份委托。" />
          <TaskFacetChips v-model="platforms" label="期望平台" :options="TASK_PLATFORMS" :max="FACET_LIMITS.platform" />
          <div class="facet-field">
            <span class="taker-label">参考 World<small class="muted">（最多 {{ FACET_LIMITS.world }} 个）</small></span>
            <div class="taker-row">
              <input v-model="worldInput" maxlength="60" placeholder="填写 World 名称或链接" aria-label="参考 World" @keydown.enter.prevent="addWorld" />
              <button type="button" class="button small secondary" :disabled="!worldInput.trim()" @click="addWorld">添加</button>
            </div>
            <div v-if="worlds.length" class="facet-chip-row">
              <button v-for="world in worlds" :key="world" type="button" class="facet-chip active" @click="removeWorld(world)">{{ world }} ×</button>
            </div>
            <small v-if="worldError" class="field-error">{{ worldError }}</small>
          </div>
          <span class="eyebrow">氛围标签（可选）</span>
          <TaskFacetChips v-for="group in ATMOSPHERE_GROUPS" :key="group.key" v-model="atmosphere[group.key]" :label="group.label" :options="group.options" single />
        </div>
        <div class="taker-field">
          <span class="taker-label">需要几人接取</span>
          <div class="taker-row">
            <input v-model.number="form.required_takers" type="number" min="1" max="999" :disabled="unlimited" required aria-label="需要接取人数" />
            <label class="checkbox-inline"><input v-model="unlimited" type="checkbox" /><span>不限人数</span></label>
          </div>
          <small class="field-hint">凑齐人数后委托自动开始；不限人数时需要你手动点击开始。</small>
        </div>
        <div class="designated-field">
          <label class="checkbox-inline"><input v-model="designated" type="checkbox" /><span>指定管理员/志愿者接取</span></label>
          <small class="field-hint">指定委托仅名单内人员可响应；单人接受即开始，多人需全部响应后开始。</small>
          <div v-if="designated" class="designated-list">
            <label v-for="person in designatedUsers" :key="person.id" class="designated-option">
              <input v-model="designatedIds" type="checkbox" :value="person.id" />
              <span>{{ person.nickname }}</span><UserTitleTag :title="person.title" /><small>{{ person.role === 'staff' ? '管理员' : '志愿者' }}</small><Check v-if="designatedIds.includes(person.id)" :size="15" />
            </label>
            <p v-if="!designatedUsers.length" class="field-hint">当前没有可指定的管理员或志愿者。</p>
            <p v-if="designated && !designatedIds.length" class="field-error">请至少指定一名管理员或志愿者</p>
          </div>
        </div>
        <div class="anonymous-field">
          <label class="checkbox-inline"><input v-model="form.is_anonymous" type="checkbox" /><span>匿名发布</span></label>
          <small class="field-hint">匿名委托在大厅不公开昵称与个人资料，仅显示标题和内容；接取后联系方式仅双方可见。</small>
        </div>
        <label>有效期（自发布起）<select v-model.number="form.expires_in_days" required><option v-for="days in expiryOptions" :key="days" :value="days">{{ days }} 天</option></select></label>
        <div class="dialog-footer"><button type="button" class="button secondary" @click="$emit('close')">暂不发布</button><button class="button" :disabled="busy || !hasContact || (designated && !designatedIds.length)">{{ busy ? '发布中…' : '确认发布' }}</button></div>
      </form>
    </section>
  </div>
</template>
