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

- 机器人认证二选一，全部只放 `.env`，**不入库、不进日志、不进前端**：
  - `VRCHAT_BOT_AUTH_COOKIE`（推荐，不保存密码）；
  - `VRCHAT_BOT_USERNAME` + `VRCHAT_BOT_PASSWORD`，开启 2FA 时再加 `VRCHAT_BOT_TOTP_SECRET`（标准 TOTP，SHA1/6 位/30 秒）。
- 不保存**用户**的 VRChat 密码、Cookie 或令牌；
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
- 披露项：`identity`、`trust_rank`、`account_age`、`platform`、`common_friends`、`common_groups`、`worlds`；七项均已接入。
- Trust Rank 映射与游戏内颜色：`system_trust_legend` / `system_trust_veteran` → 可信用户 `#8143E6`；`system_trust_trusted` → 熟识用户 `#FF7B42`；`system_trust_known` → 用户 `#2BCF5C`；`system_trust_basic` → 新用户 `#1778FF`；`system_trust_visitor` → 游客 `#808080`；未知 → 未识别 `#8A8A8A`。
- 共同社群：读取双方 `GET /users/{id}/groups` 的公开社群并求交集；双方都绑定且都开启披露时才返回，最多 3 个名称。
- 共同好友：VRChat 只提供“与当前登录账号（站点机器人）的共同好友数”`GET /users/{id}/mutuals`，因此展示为“站点共同好友”，不伪装成查看者与目标之间的好友关系。
- 常驻 World：自动读取 `GET /users/{id}` 的 `homeLocation` 并解析 World 名称；用户可在个人设置手动补充最多 3 个，手动项不会被刷新覆盖。
- 用户接口新增 `PATCH /api/vrchat/worlds` 保存手动常驻 World；`GET /api/vrchat/status` 返回 `groups`、`group_count`、`mutual_friends`、`home_world`、`manual_worlds`、`worlds`。

## 4. 仍未接入

- 查看者与目标之间的完整共同好友列表：VRChat 不提供任意用户的好友列表，只提供“与当前登录账号”的共同好友；因此本站在共同好友上使用站点机器人视角并明确标注范围。
- OSC 游戏内推送：服务端无法直接向用户客户端发 OSC，文档见 `docs/osc-bridge.md`。

## 5. 运维步骤

1. 创建一个**专用 VRChat 机器人账号**（不要使用个人主号），开启 2FA；
2. 在浏览器登录后复制 `authcookie`（或完整 `auth=…; twoFactorAuth=…`）；
3. 写入根目录 `.env`：任选 `VRCHAT_BOT_AUTH_COOKIE`，或 `VRCHAT_BOT_USERNAME` + `VRCHAT_BOT_PASSWORD` +（如开启 2FA）`VRCHAT_BOT_TOTP_SECRET`；按需修改 `VRCHAT_USER_AGENT`；
4. 重启后端；在监管台「VRChat」标签查看机器人状态与上次错误；
5. cookie 失效时重新登录复制并替换，重启后端。
