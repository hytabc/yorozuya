<script setup>
/**
 * 开始页：种子输入、出生选择、继续上局、跨局统计。
 */
import { ref, computed } from 'vue';
import { useVrclifeStore } from '../store/vrclifeStore.js';
import { rarityLabel, formatHours } from '../utils/format.js';

const store = useVrclifeStore();

const RANDOM_ID = '__random__';

const seed = ref('');
const archetypeId = ref(RANDOM_ID);
const mode = ref(store.hasSave ? 'continue' : 'new');

const selectedArch = computed(() => {
  if (archetypeId.value === RANDOM_ID) return null;
  return store.archetypes.find((a) => a.id === archetypeId.value) || null;
});

const unlockedEndingCount = computed(() => (store.meta.unlockedEndings || []).length);

function startNew() {
  store.newGame({
    seed: seed.value,
    archetypeId: archetypeId.value === RANDOM_ID ? undefined : archetypeId.value,
  });
}

function continueGame() {
  store.continueGame();
}

function rollSeed() {
  seed.value = String(Math.floor(100000 + Math.random() * 900000));
}

function rarityClass(r) {
  return `r-${r || 'common'}`;
}
</script>

<template>
  <div class="vr-start">
    <div class="start-card">
      <p class="eyebrow">文字人生模拟</p>
      <h1 class="title">VRChat 玩家历程模拟器</h1>
      <p class="subtitle">戴上头显，从第一次加好友开始，走完一段虚拟人生。</p>

      <!-- 继续上局 -->
      <section v-if="mode === 'continue' && store.hasSave" class="resume">
        <div class="resume-info">
          <p class="resume-label">检测到进行中的存档</p>
          <p class="resume-meta">
            {{ formatHours(store.saveInfo.hours) }} · {{ store.saveInfo.stage }} ·
            {{ store.saveInfo.archName }}
          </p>
        </div>
        <div class="resume-actions">
          <button class="btn primary" @click="continueGame">继续上局</button>
          <button class="btn ghost" @click="mode = 'new'">新开一局</button>
        </div>
      </section>

      <!-- 新开一局 -->
      <section v-else class="newgame">
        <div class="field">
          <label class="field-label" for="vr-seed">种子（留空则随机 6 位数字）</label>
          <div class="seed-row">
            <input
              id="vr-seed"
              v-model="seed"
              class="input"
              type="text"
              inputmode="numeric"
              maxlength="12"
              placeholder="例如 834271"
            />
            <button class="btn ghost small" type="button" @click="rollSeed">随机</button>
          </div>
        </div>

        <div class="field">
          <label class="field-label" for="vr-arch">出生方式</label>
          <select id="vr-arch" v-model="archetypeId" class="input select">
            <option :value="RANDOM_ID">随机开局（推荐）</option>
            <option v-for="a in store.archetypes" :key="a.id" :value="a.id">
              {{ a.name }} · {{ rarityLabel(a.rarity) }} —— {{ a.desc }}
            </option>
          </select>
        </div>

        <div v-if="selectedArch" class="arch-preview" :class="rarityClass(selectedArch.rarity)">
          <div class="arch-head">
            <span class="arch-name">{{ selectedArch.name }}</span>
            <span class="arch-rarity">{{ rarityLabel(selectedArch.rarity) }}</span>
          </div>
          <p class="arch-desc">{{ selectedArch.desc }}</p>
          <p class="arch-start">「{{ selectedArch.startText }}」</p>
        </div>

        <div class="actions">
          <button class="btn primary" @click="startNew">开始这一生</button>
          <button v-if="store.hasSave" class="btn ghost" @click="mode = 'continue'">
            返回继续上局
          </button>
        </div>
      </section>

      <footer class="start-footer">
        累计游玩 {{ store.meta.playCount }} 局 · 已解锁结局
        {{ unlockedEndingCount }}/{{ store.endingTotal }}
      </footer>
    </div>
  </div>
</template>

<style scoped>
.vr-start {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  box-sizing: border-box;
}

.start-card {
  width: 100%;
  max-width: 560px;
  padding: 36px 32px 28px;
  border-radius: 16px;
  background: linear-gradient(160deg, rgba(124, 58, 237, 0.16), rgba(15, 10, 30, 0.72));
  border: 1px solid rgba(124, 58, 237, 0.35);
  box-shadow: 0 8px 32px rgba(124, 58, 237, 0.25);
  backdrop-filter: blur(14px);
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 13px;
  letter-spacing: 4px;
  color: #06b6d4;
}

.title {
  margin: 0 0 10px;
  font-size: 30px;
  font-weight: 700;
  line-height: 1.3;
  color: #e9e4f5;
  background: linear-gradient(100deg, #e9e4f5 10%, #7c3aed 55%, #06b6d4 95%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.subtitle {
  margin: 0 0 26px;
  font-size: 16px;
  line-height: 1.8;
  color: #8b7fa8;
}

.resume {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.resume-info {
  padding: 16px 18px;
  border-radius: 12px;
  background: rgba(6, 182, 212, 0.08);
  border: 1px solid rgba(6, 182, 212, 0.32);
}

.resume-label {
  margin: 0 0 6px;
  font-size: 13px;
  color: #06b6d4;
  letter-spacing: 1px;
}

.resume-meta {
  margin: 0;
  font-size: 17px;
  color: #e9e4f5;
  overflow-wrap: anywhere;
}

.resume-actions,
.actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.newgame {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  font-size: 13px;
  color: #8b7fa8;
  letter-spacing: 0.5px;
}

.seed-row {
  display: flex;
  gap: 10px;
}

.input {
  flex: 1;
  min-width: 0;
  padding: 11px 14px;
  border-radius: 10px;
  border: 1px solid rgba(124, 58, 237, 0.4);
  background: rgba(15, 10, 30, 0.7);
  color: #e9e4f5;
  font-size: 16px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.input:focus {
  border-color: #7c3aed;
  box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.22);
}

.select {
  cursor: pointer;
}

.select option {
  background: #160f2a;
  color: #e9e4f5;
}

.arch-preview {
  padding: 14px 16px;
  border-radius: 12px;
  background: rgba(124, 58, 237, 0.1);
  border-left: 3px solid #7c3aed;
}

.arch-preview.r-rare {
  border-left-color: #06b6d4;
  background: rgba(6, 182, 212, 0.1);
}

.arch-preview.r-legendary {
  border-left-color: #ec4899;
  background: rgba(236, 72, 153, 0.1);
}

.arch-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.arch-name {
  font-size: 17px;
  font-weight: 600;
  color: #e9e4f5;
}

.arch-rarity {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid rgba(124, 58, 237, 0.55);
  color: #b79cf0;
}

.arch-preview.r-rare .arch-rarity {
  border-color: rgba(6, 182, 212, 0.6);
  color: #67e8f9;
}

.arch-preview.r-legendary .arch-rarity {
  border-color: rgba(236, 72, 153, 0.6);
  color: #f9a8d4;
}

.arch-desc {
  margin: 0 0 8px;
  font-size: 14px;
  line-height: 1.7;
  color: #8b7fa8;
}

.arch-start {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: #b9aede;
  font-style: italic;
}

.btn {
  padding: 11px 22px;
  border-radius: 10px;
  border: 1px solid transparent;
  font-size: 16px;
  font-family: inherit;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.btn:active {
  transform: translateY(1px);
}

.btn.primary {
  background: linear-gradient(120deg, #7c3aed, #06b6d4);
  color: #fff;
  box-shadow: 0 6px 22px rgba(124, 58, 237, 0.4);
}

.btn.primary:hover {
  box-shadow: 0 8px 28px rgba(124, 58, 237, 0.55);
}

.btn.ghost {
  background: rgba(124, 58, 237, 0.1);
  border-color: rgba(124, 58, 237, 0.45);
  color: #cbb8f5;
}

.btn.ghost:hover {
  background: rgba(124, 58, 237, 0.2);
}

.btn.small {
  padding: 11px 14px;
  font-size: 14px;
}

.start-footer {
  margin-top: 28px;
  padding-top: 16px;
  border-top: 1px solid rgba(124, 58, 237, 0.2);
  font-size: 13px;
  color: #8b7fa8;
  text-align: center;
}

/* =============== 窄屏（≤900px） =============== */
@media (max-width: 900px) {
  .vr-start {
    align-items: flex-start;
    padding: 24px 14px 40px;
  }

  .start-card {
    padding: 24px 18px 22px;
    border-radius: 14px;
  }

  .title {
    font-size: 24px;
  }

  .subtitle {
    font-size: 15px;
    line-height: 1.75;
    margin-bottom: 20px;
  }

  .newgame {
    gap: 14px;
  }

  .seed-row {
    flex-direction: column;
    gap: 8px;
  }

  .seed-row .input,
  .seed-row .btn {
    width: 100%;
  }

  .field .input,
  .field .select {
    width: 100%;
  }

  .input {
    min-height: 44px;
    font-size: 16px;
  }

  .resume-actions,
  .actions {
    flex-direction: column;
    gap: 10px;
  }

  .resume-actions .btn,
  .actions .btn {
    width: 100%;
    min-height: 46px;
  }

  .arch-name {
    font-size: 16px;
  }

  .start-footer {
    font-size: 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .btn {
    transition: none;
  }
}
</style>