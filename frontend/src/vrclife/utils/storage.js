/**
 * 存档 / 跨局元信息 的 localStorage 读写封装。
 * - 后端可注入（测试用内存对象），默认使用 globalThis.localStorage。
 * - 读取时做版本与结构校验，任何异常都不抛出，统一返回 null / 默认值。
 */

export const SAVE_KEY = 'vrclife.save.v1';
export const META_KEY = 'vrclife.meta.v1';
export const SAVE_VERSION = '1.0';

/** 跨局元信息默认值（每次调用返回新对象，避免共享引用） */
export function defaultMeta() {
  return {
    playCount: 0,
    unlockedEndings: [],
    unlockedArchetypes: [],
    seenEvents: [],
  };
}

/** 内存后端：Node / 隐私模式下的兜底实现 */
function memoryBackend() {
  const map = new Map();
  return {
    getItem(key) {
      return map.has(key) ? map.get(key) : null;
    },
    setItem(key, value) {
      map.set(key, String(value));
    },
    removeItem(key) {
      map.delete(key);
    },
  };
}

function resolveBackend(backend) {
  if (backend && typeof backend.getItem === 'function') return backend;
  try {
    if (typeof globalThis !== 'undefined' && globalThis.localStorage) {
      return globalThis.localStorage;
    }
  } catch (_e) {
    /* 某些环境访问 localStorage 会抛异常 */
  }
  return memoryBackend();
}

function safeGet(backend, key) {
  try {
    return backend.getItem(key);
  } catch (_e) {
    return null;
  }
}

function safeSet(backend, key, value) {
  try {
    backend.setItem(key, value);
    return true;
  } catch (_e) {
    return false;
  }
}

function safeRemove(backend, key) {
  try {
    backend.removeItem(key);
    return true;
  } catch (_e) {
    return false;
  }
}

/**
 * 创建存储访问器。
 * @param {{getItem:Function,setItem:Function,removeItem:Function}} [backend]
 */
export function createStorage(backend) {
  const be = resolveBackend(backend);

  return {
    /** 原始后端，测试里可直接读写 */
    backend: be,

    /**
     * 读取存档。
     * 校验：version === '1.0' 且含 state 对象；否则返回 null（不抛）。
     * @returns {{version:string, savedAt:number, state:object, meta:object}|null}
     */
    loadSave() {
      const raw = safeGet(be, SAVE_KEY);
      if (!raw) return null;
      let obj = null;
      try {
        obj = JSON.parse(raw);
      } catch (_e) {
        return null;
      }
      if (!obj || typeof obj !== 'object') return null;
      if (obj.version !== SAVE_VERSION) return null;
      if (!obj.state || typeof obj.state !== 'object') return null;
      return obj;
    },

    /**
     * 写入存档。
     * @param {{state:object, meta?:object, savedAt?:number, version?:string}} save
     * @returns {boolean}
     */
    writeSave(save) {
      if (!save || !save.state || typeof save.state !== 'object') return false;
      const payload = {
        version: SAVE_VERSION,
        savedAt: save.savedAt || Date.now(),
        state: save.state,
        meta: save.meta || defaultMeta(),
      };
      return safeSet(be, SAVE_KEY, JSON.stringify(payload));
    },

    clearSave() {
      return safeRemove(be, SAVE_KEY);
    },

    /**
     * 读取跨局元信息；字段缺失或损坏时回落到默认值。
     */
    loadMeta() {
      const def = defaultMeta();
      const raw = safeGet(be, META_KEY);
      if (!raw) return def;
      let obj = null;
      try {
        obj = JSON.parse(raw);
      } catch (_e) {
        return def;
      }
      if (!obj || typeof obj !== 'object') return def;
      return {
        playCount: Number.isFinite(obj.playCount) ? Math.max(0, Math.trunc(obj.playCount)) : 0,
        unlockedEndings: Array.isArray(obj.unlockedEndings) ? [...obj.unlockedEndings] : [],
        unlockedArchetypes: Array.isArray(obj.unlockedArchetypes) ? [...obj.unlockedArchetypes] : [],
        seenEvents: Array.isArray(obj.seenEvents) ? [...obj.seenEvents] : [],
      };
    },

    writeMeta(meta) {
      const payload = { ...defaultMeta(), ...(meta || {}) };
      return safeSet(be, META_KEY, JSON.stringify(payload));
    },
  };
}

export default createStorage;