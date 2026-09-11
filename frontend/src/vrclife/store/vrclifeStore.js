/**
 * VRChat 玩家历程模拟器 —— Pinia store。
 * 负责：数据加载、开局、选项推进、存档、跨局元信息、结局结算。
 */
import { defineStore } from 'pinia';
import { createGame } from '../engine/engine.js';
import { loadVrclifeData } from '../data/loader.js';
import { createStorage, defaultMeta } from '../utils/storage.js';
import { stageOf } from '../utils/format.js';
import { buildInsights, evaluateAchievements } from '../engine/insights.js';

/** 模块级 storage 单例（不放进 state，避免被响应式代理） */
let _storage = null;

/**
 * 模块级引擎实例（不放进 Pinia state）。
 * 引擎内部通过闭包直接改写原始 state 对象，若放入响应式 state，
 * 改写不经过代理 setter，UI 不会收到更新通知；且代理身份会破坏
 * createGame 返回值与 store.game 的同一性。
 * 响应式靠 state.turn 计数器：每次引擎操作后 turn++，
 * 依赖 game/gameState/currentEvent/ending 等 getter 的组件随之重算。
 */
let _game = null;

function ensureStorage() {
  if (!_storage) _storage = createStorage();
  return _storage;
}

/** 随机 6 位数字种子字符串 */
export function randomSeed() {
  return String(Math.floor(100000 + Math.random() * 900000));
}

export const useVrclifeStore = defineStore('vrclife', {
  state: () => ({
    /** 加载后的数据包 */
    data: null,
    /** 回合计数器：引擎操作后 ++，驱动依赖引擎态的 getter 重算 */
    turn: 0,
    /** 'loading'|'start'|'opening'|'playing'|'ended'|'error' */
    phase: 'loading',
    errorMsg: '',
    /** 跨局元信息 */
    meta: defaultMeta(),
    /** 最近一次 choose 的返回值，供结果弹层使用 */
    result: null,
    /** 本局出生 archetype */
    startArch: null,
    /** 出生 startText（opening 阶段展示） */
    startText: '',
    /** 存档摘要（开始页「继续上局」用） */
    saveInfo: null,
    /** 内部：本局是否已结算，防止 playCount 重复累加 */
    _finalized: false,
    /** 本局成就结算结果：{ earnedIds, newlyIds }（供结局页高亮新解锁） */
    endingAchievements: null,
  }),

  getters: {
    /** 引擎实例（原始对象；读取时触碰 turn 以建立响应式依赖） */
    game() {
      void this.turn;
      return _game;
    },
    gameState() {
      void this.turn;
      if (!_game) return null;
      const s = _game.state;
      // 返回浅层刷新快照：引擎通过闭包原地改写嵌套结构（skills/relation/history/tags…），
      // 若直接返回原对象，下游 computed 因引用相等（Object.is）收不到更新通知。
      return {
        ...s,
        skills: { ...s.skills },
        counters: { ...s.counters },
        tags: [...s.tags],
        circles: [...s.circles],
        flags: [...s.flags],
        history: [...s.history],
        relation: s.relation ? { ...s.relation } : null,
        relations: (s.relations || []).map((r) => ({ ...r })),
        focusId: s.relation && s.relation.id !== undefined ? s.relation.id : null,
      };
    },
    vocab: (state) => (state.data ? state.data.vocab : null),
    archetypes: (state) => (state.data && state.data.archetypes) || [],
    endings: (state) => (state.data && state.data.endings) || [],
    currentEvent() {
      void this.turn;
      return _game ? _game.current : null;
    },
    ending() {
      void this.turn;
      return _game ? _game.ending : null;
    },
    seedStr() {
      void this.turn;
      const st = _game && _game.state;
      return st && st.seed !== undefined ? String(st.seed) : '';
    },
    currentStage() {
      const st = this.gameState;
      return stageOf(st ? st.hours : 0, this.vocab);
    },
    endingTotal() {
      const n = this.endings.length;
      return n > 0 ? n : 16;
    },
    hasSave: (state) => !!state.saveInfo,
  },

  actions: {
    /** 注入自定义 storage 后端（测试用） */
    initWithStorage(backend) {
      _storage = createStorage(backend);
      return _storage;
    },

    /** 浏览器入口：fetch 数据后进入开局页 */
    async init() {
      this.phase = 'loading';
      this.errorMsg = '';
      try {
        const data = await loadVrclifeData();
        this.initWithData(data);
      } catch (e) {
        this.errorMsg = (e && e.message) ? e.message : '数据加载失败';
        this.phase = 'error';
      }
    },

    /** 测试 / 预载入入口：直接拿到 data 对象 */
    initWithData(data) {
      const storage = ensureStorage();
      this.data = data;
      this.meta = storage.loadMeta();
      _game = null;
      this.turn++;
      this.result = null;
      this.startArch = null;
      this.startText = '';
      this._finalized = false;
      this.endingAchievements = null;
      const save = storage.loadSave();
      this.saveInfo = save ? this._describeSave(save) : null;
      this.phase = 'start';
    },

    _describeSave(save) {
      const st = (save && save.state) || {};
      const hours = Number(st.hours) || 0;
      return {
        hours,
        playerName: st.playerName || '我',
        archName: st.arch && st.arch.name ? st.arch.name : '未知开局',
        savedAt: save.savedAt || 0,
        stage: stageOf(hours, this.vocab),
      };
    },

    /** 开新局 */
    newGame({ seed, archetypeId, playerName } = {}) {
      if (!this.data) throw new Error('数据尚未加载');
      const storage = ensureStorage();

      const rawSeed = seed === undefined || seed === null ? '' : String(seed).trim();
      const finalSeed = rawSeed || randomSeed();

      const game = createGame({
        data: this.data,
        seed: finalSeed,
        playerName: playerName || '我',
        archetypeId: archetypeId || undefined,
      });

      _game = game;
      this.turn++;
      this.result = null;
      this._finalized = false;
      this.endingAchievements = null;
      this.startArch = (game.state && game.state.arch) || null;
      this.startText = (this.startArch && this.startArch.startText) || '';
      this.saveInfo = null;

      const archId = this.startArch && this.startArch.id;
      if (archId && !this.meta.unlockedArchetypes.includes(archId)) {
        this.meta.unlockedArchetypes.push(archId);
      }
      this.persistMeta();
      this.persistSave();
      this.phase = 'opening';
      return game;
    },

    /** 开场卡 → 正式进入第一回合 */
    begin() {
      if (this.phase === 'opening') this.phase = 'playing';
    },

    /** 做出选择 */
    choose(optionId) {
      const game = _game;
      if (!game || game.phase !== 'playing') return null;

      let res = null;
      try {
        res = game.choose(optionId);
      } catch (e) {
        this.errorMsg = (e && e.message) ? e.message : '选择失败';
        return null;
      }
      this.turn++; // 引擎已改写状态，通知所有依赖方重算
      this.result = res;

      const evId = res && res.entry ? res.entry.eventId : null;
      if (evId && !this.meta.seenEvents.includes(evId)) {
        this.meta.seenEvents.push(evId);
      }
      this.persistMeta();

      if (game.phase === 'ended') {
        this.finalizeEnding();
      } else {
        this.persistSave();
      }
      return res;
    },

    /** 从存档恢复 */
    continueGame() {
      const storage = ensureStorage();
      const save = storage.loadSave();
      if (!save) {
        this.saveInfo = null;
        this.phase = 'start';
        return false;
      }
      try {
        const game = createGame.fromSave(save.state, this.data);
        _game = game;
        this.turn++;
        this.result = null;
        this._finalized = false;
      this.endingAchievements = null;
        this.startArch = (game.state && game.state.arch) || null;
        this.startText = '';
        this.saveInfo = null;
        if (game.phase === 'ended') {
          this.phase = 'ended';
          this.finalizeEnding();
        } else {
          this.phase = 'playing';
        }
        return true;
      } catch (e) {
        storage.clearSave();
        _game = null;
        this.turn++;
        this.saveInfo = null;
        this.errorMsg = (e && e.message) ? e.message : '存档损坏，已清除';
        this.phase = 'start';
        return false;
      }
    },

    /** 清档回到开始页（保留 meta） */
    restart() {
      const storage = ensureStorage();
      storage.clearSave();
      _game = null;
      this.turn++;
      this.result = null;
      this.startArch = null;
      this.startText = '';
      this.saveInfo = null;
      this._finalized = false;
      this.endingAchievements = null;
      this.phase = 'start';
    },

    /** 主动结束当前局 */
    quitGame() {
      if (!_game || _game.phase !== 'playing') return;
      _game.quit();
      this.turn++;
      if (_game.phase === 'ended') this.finalizeEnding();
    },

    /** 结算：元信息累加 + 清存档 */
    finalizeEnding() {
      if (this._finalized) return;
      this._finalized = true;

      const storage = ensureStorage();
      const ending = this.ending;

      this.meta.playCount = (Number(this.meta.playCount) || 0) + 1;
      if (ending && ending.id && !this.meta.unlockedEndings.includes(ending.id)) {
        this.meta.unlockedEndings.push(ending.id);
      }

      // ---- 成就结算：本局判定 + 跨局累计（写入 meta）----
      const st = this.gameState || {};
      const insights = buildInsights(st, this.vocab, this.data);
      const before = new Set(this.meta.unlockedAchievements || []);
      const result = evaluateAchievements({
        st,
        ending,
        insights,
        vocab: this.vocab,
        data: this.data,
        meta: this.meta,
      });
      const newlyIds = result.earnedIds.filter((id) => !before.has(id));
      const unlocked = new Set(this.meta.unlockedAchievements || []);
      for (const id of result.earnedIds) unlocked.add(id);
      this.meta.unlockedAchievements = [...unlocked];
      this.endingAchievements = { earnedIds: result.earnedIds, newlyIds };
      // ------------------------------------------------

      this.persistMeta();
      storage.clearSave();

      this.saveInfo = null;
      this.phase = 'ended';
    },

    /** 写入进行中的存档 */
    persistSave() {
      if (!_game) return;
      const storage = ensureStorage();
      storage.writeSave({
        state: _game.serialize(),
        meta: { ...this.meta },
        savedAt: Date.now(),
      });
    },

    /** 写入跨局元信息 */
    persistMeta() {
      ensureStorage().writeMeta({ ...this.meta });
    },
  },
});

export default useVrclifeStore;