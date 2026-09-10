/**
 * 关卡数据穷举校验器
 * ------------------------------------------------------------------
 * 用法： node tools/verify-levels.ts [关卡ID...]
 *
 * 对每个关卡枚举"全部合法排列"，回答四个问题：
 *   1. 每个设计结局是否至少被一种排列命中（可达性）？
 *   2. 每个结局的最优排列是什么，得分余量多少？
 *   3. 有多少排列落入混沌（是否过高/过低）？
 *   4. 数据本身是否自洽（ID 唯一、锚点正确、约束引用的碎片存在、阈值不超上限）？
 *
 * 退出码：0 = 全部通过；1 = 存在错误。
 */

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Level, Ending } from '../src/lib/engine/types.ts';
import { judgeChain } from '../src/lib/engine/judge.ts';
import { sumWeights } from '../src/lib/engine/constraints.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const LEVELS_DIR = join(HERE, '..', 'src', 'lib', 'data', 'levels');

/* ----------------------------- 工具 ----------------------------- */

function permutations<T>(arr: T[]): T[][] {
  if (arr.length <= 1) return [arr.slice()];
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i++) {
    const rest = arr.slice(0, i).concat(arr.slice(i + 1));
    for (const p of permutations(rest)) out.push([arr[i], ...p]);
  }
  return out;
}

const C = {
  red: (s: string) => `\x1b[31m${s}\x1b[0m`,
  green: (s: string) => `\x1b[32m${s}\x1b[0m`,
  yellow: (s: string) => `\x1b[33m${s}\x1b[0m`,
  gray: (s: string) => `\x1b[90m${s}\x1b[0m`,
  bold: (s: string) => `\x1b[1m${s}\x1b[0m`,
};

/* --------------------------- 数据自检 --------------------------- */

function validateLevel(level: Level): string[] {
  const errors: string[] = [];
  const ids = level.fragments.map((f) => f.id);

  // ID 唯一
  if (new Set(ids).size !== ids.length) errors.push('存在重复的碎片 ID');

  // 锚点存在且类型为 gray
  for (const key of ['first', 'last'] as const) {
    const id = level.anchors[key];
    const frag = level.fragments.find((f) => f.id === id);
    if (!frag) errors.push(`锚点 ${key}=${id} 不存在`);
    else if (frag.type !== 'gray') errors.push(`锚点 ${id} 的类型应为 gray，实际为 ${frag.type}`);
  }

  // initialOrder 合法
  const order = level.initialOrder;
  if (order[0] !== level.anchors.first) errors.push('initialOrder 首位不是 anchors.first');
  if (order[order.length - 1] !== level.anchors.last)
    errors.push('initialOrder 末位不是 anchors.last');
  if (new Set(order).size !== order.length) errors.push('initialOrder 存在重复');
  for (const id of order) if (!ids.includes(id)) errors.push(`initialOrder 含未知碎片 ${id}`);
  for (const id of order) {
    const f = level.fragments.find((x) => x.id === id)!;
    if (f.type === 'gray' && id !== level.anchors.first && id !== level.anchors.last)
      errors.push(`灰色碎片 ${id} 出现在可动区间`);
  }

  // 约束引用的碎片存在
  const allEndings: Ending[] = [...level.endings, level.chaosEnding];
  for (const e of allEndings) {
    for (const c of [...e.constraints, ...e.anti]) {
      const refs = [c.a, c.b, c.frag, ...(c.frags ?? [])].filter(Boolean) as string[];
      if (refs.length === 0) errors.push(`结局 ${e.id} 存在空约束 ${JSON.stringify(c)}`);
      for (const r of refs) {
        if (!ids.includes(r)) errors.push(`结局 ${e.id} 引用了不存在的碎片 ${r}`);
      }
      if (c.kind === 'position' && typeof c.index !== 'number')
        errors.push(`结局 ${e.id} 的 position 约束缺少 index`);
    }
    if (e.type !== 'chaos') {
      const max = sumWeights(e.constraints);
      if (e.threshold > max)
        errors.push(
          `结局 ${e.id} 阈值 ${e.threshold} 超过理论上限 ${max} —— 永远不会命中`,
        );
    }
  }

  // 结论 ID 唯一
  const endingIds = allEndings.map((e) => e.id);
  if (new Set(endingIds).size !== endingIds.length) errors.push('存在重复的结局 ID');

  // 各结局的理论最高分必须一致（否则 score 排序会偏袒权重更高的结局）
  const maxes = level.endings.map((e) => sumWeights(e.constraints));
  if (maxes.length > 0 && new Set(maxes).size > 1) {
    errors.push(
      `各结局的理论最高分不一致：[${level.endings
        .map((e) => `${e.id}=${sumWeights(e.constraints)}`)
        .join(', ')}] —— 请把每个结局的约束权重归一化到同一总分`,
    );
  }

  return errors;
}

/* --------------------------- 穷举校验 --------------------------- */

interface EndingStat {
  id: string;
  title: string;
  type: string;
  reachable: boolean;
  witness: string[] | null;
  bestScore: number;
  threshold: number;
  margin: number;
  /** 该结局引用的碎片是否全部存在于当前链（否则视为"不适用"，跳过） */
  applicable: boolean;
}

interface LevelReport {
  levelId: string;
  title: string;
  configs: {
    label: string;
    chainLength: number;
    permCount: number;
    chaosCount: number;
    endingStats: EndingStat[];
  }[];
  errors: string[];
}

function verifyLevel(level: Level): LevelReport {
  const errors = validateLevel(level);

  // 参与判定的碎片 = initialOrder 的成员
  const baseMovable = level.initialOrder.slice(1, -1);
  const baseSet = new Set(level.initialOrder);

  // 额外配置：加入"隐藏且非蓝色"的链内碎片
  const hiddenChainFrags = level.fragments
    .filter((f) => f.hidden && f.type !== 'blue' && !baseSet.has(f.id))
    .map((f) => f.id);

  const configs: { label: string; movable: string[] }[] = [
    { label: '基础配置', movable: baseMovable },
  ];
  if (hiddenChainFrags.length > 0) {
    configs.push({
      label: `解锁配置(+${hiddenChainFrags.length})`,
      movable: [...baseMovable, ...hiddenChainFrags],
    });
  }

  const configReports: LevelReport['configs'] = [];

  for (const cfg of configs) {
    const perms = permutations(cfg.movable);
    const chainSet = new Set([level.anchors.first, ...cfg.movable, level.anchors.last]);
    const stats = new Map<string, EndingStat>();
    for (const e of level.endings) {
      const refs = [...e.constraints, ...e.anti]
        .flatMap((c) => [c.a, c.b, c.frag, ...(c.frags ?? [])])
        .filter(Boolean) as string[];
      const applicable = refs.every((r) => chainSet.has(r));
      stats.set(e.id, {
        id: e.id,
        title: e.title,
        type: e.type,
        reachable: false,
        witness: null,
        bestScore: -Infinity,
        threshold: e.threshold,
        margin: 0,
        applicable,
      });
    }
    let chaosCount = 0;

    for (const perm of perms) {
      const chain = [level.anchors.first, ...perm, level.anchors.last];
      // unlockedEndingIds = null → 全部视为已解锁（校验"设计上是否可达"）
      const result = judgeChain(chain, level, { unlockedEndingIds: null });

      if (result.isChaos) {
        chaosCount++;
        continue;
      }

      const st = stats.get(result.ending.id);
      if (!st) continue;
      st.reachable = true;
      if (result.score > st.bestScore) {
        st.bestScore = result.score;
        st.witness = chain;
      }
    }

    for (const st of stats.values()) {
      if (st.bestScore === -Infinity) st.bestScore = 0;
      st.margin = st.bestScore - st.threshold;
    }

    configReports.push({
      label: cfg.label,
      chainLength: cfg.movable.length + 2,
      permCount: perms.length,
      chaosCount,
      endingStats: [...stats.values()],
    });
  }

  return { levelId: level.id, title: level.title, configs: configReports, errors };
}

/* ----------------------------- 主流程 ----------------------------- */

function loadLevels(filter: string[]): Level[] {
  if (!existsSync(LEVELS_DIR)) {
    console.error(C.red(`找不到关卡目录：${LEVELS_DIR}`));
    process.exit(1);
  }
  const files = readdirSync(LEVELS_DIR).filter((f) => f.endsWith('.json') && f !== 'index.json');
  const levels: Level[] = [];
  for (const f of files) {
    const raw = readFileSync(join(LEVELS_DIR, f), 'utf8');
    const level = JSON.parse(raw) as Level;
    if (filter.length > 0 && !filter.includes(level.id)) continue;
    levels.push(level);
  }
  // 按章节/序号排序
  levels.sort((a, b) => a.chapter - b.chapter || a.order - b.order);
  return levels;
}

function main(): void {
  const filter = process.argv.slice(2).filter((a) => !a.startsWith('-'));
  const levels = loadLevels(filter);

  if (levels.length === 0) {
    console.error(C.yellow('没有匹配的关卡。'));
    process.exit(1);
  }

  let hasError = false;
  const distinctEndings = new Map<string, boolean>(); // endingId → reachable

  for (const level of levels) {
    const report = verifyLevel(level);
    const head = C.bold(`\n━━ ${level.id} ${level.title} ━━`);
    console.log(head);

    if (report.errors.length > 0) {
      hasError = true;
      for (const e of report.errors) console.log(C.red(`  ✗ 数据错误：${e}`));
    } else {
      console.log(C.gray('  数据自检通过'));
    }

    for (const cfg of report.configs) {
      console.log(
        C.gray(
          `  · ${cfg.label}｜链长 ${cfg.chainLength}｜排列 ${cfg.permCount}｜混沌 ${cfg.chaosCount} (${(
            (cfg.chaosCount / cfg.permCount) * 100
          ).toFixed(1)}%)`,
        ),
      );
      for (const st of cfg.endingStats) {
        if (!st.applicable) {
          console.log(
            C.gray(`      – ${st.type.padEnd(12)} ${st.title.padEnd(10)} 不适用（缺少其引用的碎片）`),
          );
          continue;
        }
        // 去重统计：同一结局可能出现在多个配置中（如 1-3 的 true 只在解锁配置里）
        const prev = distinctEndings.get(st.id);
        distinctEndings.set(st.id, (prev ?? false) || st.reachable);
        if (!st.reachable && prev === undefined) hasError = true;
        const mark = st.reachable ? C.green('✓') : C.red('✗');
        const marginStr = st.reachable
          ? C.gray(`得分 ${st.bestScore}/${st.threshold}  余量 +${st.margin}`)
          : C.red('不可达');
        console.log(`      ${mark} ${st.type.padEnd(12)} ${st.title.padEnd(10)} ${marginStr}`);
        if (st.reachable && st.margin < 0) {
          hasError = true;
          console.log(C.red('        ↑ 余量为负，阈值设定有误'));
        }
      }
    }
  }

  const distinctReachable = [...distinctEndings.values()].filter(Boolean).length;
  console.log(
    C.bold(
      `\n总计：${levels.length} 关，设计结局 ${distinctEndings.size} 项（去重后），可达 ${distinctReachable} 项。`,
    ),
  );
  if (hasError) {
    console.log(C.red('校验未通过，请修正上方标记的问题。'));
    process.exit(1);
  }
  console.log(C.green('全部关卡校验通过。'));
}

main();
