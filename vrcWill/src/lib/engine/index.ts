/**
 * 判定引擎统一出口
 * ------------------------------------------------------------------
 * 外部模块（Svelte 组件、Store、校验脚本、单测）一律从本文件导入，
 * 不要直接引用内部文件，以便将来重构。
 */

export * from './types.ts';
export * from './constraints.ts';
export * from './scoring.ts';
export * from './judge.ts';
export * from './butterfly.ts';
export * from './hints.ts';
