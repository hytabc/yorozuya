#!/usr/bin/env node
/**
 * 把仓库根 vrclife/data/*.json 拷到 frontend/public/vrclife-data/。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(FRONTEND, '..');
const SRC = path.join(REPO_ROOT, 'vrclife', 'data');
const DEST = path.join(FRONTEND, 'public', 'vrclife-data');

const FILES = ['events.index.json', 'vocab.json', 'endings.json', 'archetypes.json'];

function main() {
  if (!fs.existsSync(SRC)) {
    console.error(`源目录不存在: ${SRC}`);
    process.exit(1);
  }
  fs.mkdirSync(DEST, { recursive: true });
  for (const name of FILES) {
    const srcPath = path.join(SRC, name);
    const dstPath = path.join(DEST, name);
    if (!fs.existsSync(srcPath)) {
      console.error(`缺失文件: ${srcPath}`);
      process.exit(1);
    }
    fs.copyFileSync(srcPath, dstPath);
    const bytes = fs.statSync(dstPath).size;
    console.log(`copied ${name}  ->  ${dstPath}  (${bytes} bytes)`);
  }
  console.log(`完成，共 ${FILES.length} 个文件 -> ${DEST}`);
}

main();