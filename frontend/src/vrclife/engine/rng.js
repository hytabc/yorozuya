/**
 * RNG 模块 —— mulberry32 + FNV-1a 哈希。
 * NOTE: 与 PRD §6.1 一致，使用 mulberry32；与 simulate.py 的 random.Random
 * 单局随机序列不要求一致，验收靠统计分布对齐（见 §6 测试）。
 */

/**
 * FNV-1a 32 位字符串哈希。
 * @param {string} str
 * @returns {number} 无符号 32 位整数
 */
export function hashSeed(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/**
 * mulberry32 生成器（内联版，以便暴露内部状态 a）。
 * @param {number} seed
 * @returns {() => number}
 */
function mulberry32(seed) {
  let a = seed | 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * 创建带辅助方法的 RNG。
 * @param {string|number} seed
 * @returns {{
 *   next: () => number,
 *   randInt: (lo:number, hi:number) => number,
 *   randint: (lo:number, hi:number) => number,
 *   pick: <T>(arr:T[]) => T,
 *   weightedPick: <T>(items:T[], weights:number[]) => T,
 *   getState: () => number,
 *   setState: (s:number) => void
 * }}
 */
export function createRng(seed) {
  let a = typeof seed === 'string' ? hashSeed(seed) : ((Number(seed) | 0) | 0);

  function next() {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  const randIntImpl = (lo, hi) => lo + Math.floor(next() * (hi - lo + 1));
  return {
    next,
    /** 闭区间整数，等价 Python randint(lo, hi)。 */
    randInt: randIntImpl,
    /** randInt 的小写别名（对齐 Python 命名，部分移植代码沿用）。 */
    randint: randIntImpl,
    pick(arr) {
      if (!arr || arr.length === 0) return undefined;
      return arr[Math.floor(next() * arr.length)];
    },
    /**
     * 累计权重抽取，越界返回最后一项。
     * 等价 simulate.py 的 `x = next()*total; acc += w; if (x <= acc) return`。
     * 全 0 权重时返回第一项、不抛错。
     */
    weightedPick(items, weights) {
      let total = 0;
      for (let i = 0; i < weights.length; i++) total += weights[i];
      const x = next() * total;
      let acc = 0;
      for (let i = 0; i < items.length; i++) {
        acc += weights[i];
        if (x <= acc) return items[i];
      }
      return items[items.length - 1];
    },
    getState() {
      return a;
    },
    setState(s) {
      a = s | 0;
    },
  };
}