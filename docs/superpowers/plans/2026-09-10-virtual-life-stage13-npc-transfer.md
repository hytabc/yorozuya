# 虚拟人生 Stage 13 — NPC 级数据导入导出

## 需求原话

> 得做个npc相关数据的导入导出吧,要不然线上环境不小心把别人的数据覆盖了怎么办

## 设计

**导出**：`GET /api/virtual-life/packs/{pack_id}/npcs/{npc_id}/export`（role_manager）

- 单 NPC 完整切片打包成 `wsw-life-npc@v1` JSON：npc 档案（含默认回复）、portrait、presence、7 天剧本、初始对话
- `/uploads/life/` 站内图片（立绘/节点图/回复图）base64 内嵌进 `images`；外链（如 `/life-assets/`）原样保留；文件缺失记入 `missingImages` 不致命

**导入**：`POST /api/virtual-life/packs/{pack_id}/npcs/import`（role_manager，body `{bundle}`）

1. bundle 结构校验（format/version/npcId 合法性/data 键齐全）→ 422
2. 自动备份当前包为 `{id}-bak-{时间戳}` 行（撞 id 自动加后缀）
3. 图片 base64 → 魔数嗅探 + 5MiB 上限（复用 `_life_image_extension`/`MAX_LIFE_IMAGE_BYTES`）→ 落盘新 uuid 文件名 → 旧路径→新路径映射
4. 改写切片内图片路径后合并：只动 npcIds/npcs/portraits/presence/dialogue/initialState.conversations，其余键一律不碰
5. 整体过 `validate_pack_content`；任何失败 `db.rollback()` + 删除已写入图片，不留痕迹
6. 成功：版本 +1，返回 `npcImport: {npcId, mode: created|overwritten, images, backupId}`

**前端**（内容管理「人物」页）：标题区「导入 NPC」按钮（选文件 → 摘要 confirm：模式/天数/节点数/图片数 → 导入 → 重新载入包）；每行加「导出」按钮（直接下载 `{packId}.{npcId}.npc.json`）。

## 生成与审计

- DeepSeek 直连 API 生成（`deepseek-v4-flash-vision-exp`，~4 分钟，4 个文件），Kimi 审计落盘。
- 审计记录：后端 diff 除新增段外仅有引号风格变化；导入失败路径（422/500）均有回滚+文件清理；`except PackContentError` 为死代码（内层已包成 HTTPException），无害未改。

## 验证

- 后端 pytest 96 全绿（新增 `test_virtual_life_npc_transfer.py` 6 个用例：导出内嵌/回环恢复/切片隔离/坏包回滚/自动备份/权限 403）
- 前端 85 node:test 全绿、`npm run build` 通过
- 浏览器实测（/life-admin，本地真实库）：
  - 米米行「导出」→ 请求 200，JSON 含 1 张内嵌图片
  - 「导入 NPC」上传改名后的 bundle → confirm 摘要正确（覆盖/7 天/20 节点/1 图）→ 表格即时变为「米米·改」
  - 服务端复核：包 v10→v11、备份行生成、米米立绘路径重写为新 uuid、其余 4 个 NPC 逐键未动
  - 实测结束后已恢复米米原名并删除测试备份行（当前 v12）

## 遗留

- 整包推送脚本 `push_pack.py`（Kimi 工作区）用于首次部署/全量同步；日常迁移用本阶段的 NPC 级导入导出。
- 事件（events）是房间级数据，不随 NPC 切片迁移。
