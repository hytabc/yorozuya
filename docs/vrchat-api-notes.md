# VRChat 身份接入（预研结论 + 2026-11 实现）

> 结论：VRChat 没有公开 OAuth，本站采用「**站点机器人读取公开资料 + 用户简介验证码**」证明资料控制权。
> 不保存任何用户的 VRChat 密码；机器人凭据只放服务端 `.env`。
> 最后更新：2026-11

## 1. 预研事实

| 问题 | 结论 |
|---|---|
| 是否有公开 OAuth / 开放平台 | **没有**。VRChat 未向第三方站点提供 OAuth 授权入口 |
| 社区 SDK 怎么认证 | `vrchatapi` / VRChat.js 使用「用户名 + 密码 + 2FA」，或长期 Cookie |
| 能否匿名读别人的资料 | **不能**。读取任意用户 profile 需要登录会话 |
| 常用字段 | `tags` 中的 `system_trust_*`、`date_joined`、`last_platform` |
| 速率限制与稳定性 | 非官方契约，接口与限流随时可能变化；封号策略由对方决定 |

## 2. 采用方案

1. 用户提交 `usr_…` 或 VRChat 主页链接；
2. 服务端用**专用机器人账号**的 `auth` cookie 调用 `GET /users/{id}`，读取公开资料；
3. 生成 10 分钟一次性验证码 `【万事屋 VRChat 验证 - vrcverify…】`；
4. 用户把验证码写入 VRChat 个人简介；
5. 服务端再次读取最新简介，做 NFKC / 破折号 / 空白归一化后匹配；
6. 通过后 `verified=true`，记录 Trust Rank、账号年龄、平台；资料快照 7 天有效；
7. 用户逐项披露；所有裁剪发生在接口层。

### 安全与运维

- 机器人 cookie 只放 `.env` 的 `VRCHAT_BOT_AUTH_COOKIE`，**不入库、不进日志、不进前端**；
- 不保存用户的 VRChat 密码、Cookie 或令牌；
- 机器人请求串行 + 最小间隔，尊重 `429` 与 `Retry-After`；
- 连续 5 次验证失败冷却 5 分钟；
- 机器人会话失效时 **fail-closed**，明确提示「暂时不可用」，不伪造数据；
- 不自动加好友、不自动发消息、不批量抓取；
- 后台可按 `usr_` 查询绑定、解绑、拉黑；黑名单只存 ID、操作人与时间。

## 3. 数据与接口

- 表：`vrchat_identities`（绑定、验证状态、资料快照、一次性验证码）、`vrchat_bans`（黑名单）。
- 用户接口：
  - `GET /api/vrchat/status`
  - `POST /api/vrchat/link/start`（兼容旧路径 `POST /api/vrchat/link`）
  - `POST /api/vrchat/link/check`
  - `POST /api/vrchat/refresh`
  - `POST /api/vrchat/unlink`
  - `DELETE /api/vrchat/data`
  - `PATCH /api/vrchat/disclosure`
- 公开信任摘要：`GET /api/users/{id}/trust`、`GET /api/tasks/{id}/trust`（游客可读，按披露裁剪；匿名委托 `publisher=null`）。
- 后台：`GET /api/admin/vrchat/status`、`PATCH /api/admin/vrchat/config`、`GET /api/admin/vrchat/accounts?vrchat_user_id=`、解绑/拉黑/解除拉黑、`GET /api/admin/vrchat/bans`。
- 披露项：`identity`、`trust_rank`、`account_age`、`platform`、`common_friends`、`common_groups`、`worlds`；前四项已可用，后三项仍未接入。
- Trust Rank 映射：`system_trust_legend` / `system_trust_veteran` → 可信用户；`system_trust_trusted` → 熟识用户；`system_trust_known` → 用户；`system_trust_basic` → 新用户；`system_trust_visitor` → 游客；未知 → 未识别。

## 4. 仍未接入

- 共同好友、共同社群、常驻 World：需要双方授权与额外接口语义，当前不展示、不伪造；
- OSC 游戏内推送：服务端无法直接向用户客户端发 OSC，文档见 `docs/osc-bridge.md`。

## 5. 运维步骤

1. 创建一个**专用 VRChat 机器人账号**（不要使用个人主号），开启 2FA；
2. 在浏览器登录后复制 `authcookie`（或完整 `auth=…; twoFactorAuth=…`）；
3. 写入根目录 `.env` 的 `VRCHAT_BOT_AUTH_COOKIE`，按需修改 `VRCHAT_USER_AGENT`；
4. 重启后端；在监管台「VRChat」标签查看机器人状态与上次错误；
5. cookie 失效时重新登录复制并替换，重启后端。
