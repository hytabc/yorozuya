# AGENTS.md — 万事屋委托站项目速览

> 本文件面向 AI 助手/后续维护者：先读这里再改代码，避免全库探索。最后更新：2026-09。

## 一句话概述

面向 VRChat 社区的委托发布与协作网站（"万事屋"）：委托人发布委托（可带密码/指定接单人/匿名），接单人凭密码或直接接取，全员确认后完成；含用户权限等级、举报/反馈、成员名录、砂糖社档案、AI 看板娘等模块。

## 技术栈与运行

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy 2.0（ORM）+ Pydantic v2 + pydantic-settings，默认 SQLite（`data/wsw.db`），JWT（HTTPBearer）认证 |
| 前端 | Vue 3（`<script setup>`）+ Pinia + Vue Router + Vite + axios + lucide-vue-next 图标 |
| 部署 | Docker Compose（`docker-compose.yml`，prod/dev 两套）+ 边缘 Nginx 终止 HTTPS + certbot 自动续期（`deploy/nginx/`、`deploy/certbot/`、`deploy/init-letsencrypt.sh`）；根目录 `start.sh` / `start.bat` 一键启动 |
| 测试 | 后端 pytest（`backend/tests/test_api.py` + `test_security_media.py` 等，TestClient + 内存库，约 130 个用例） |

命令：
- 后端测试：`cd backend && python -m pytest tests -q`
- 前端开发/构建：`cd frontend && npm run dev` / `npm run build`
- 生产：`docker compose up -d --build`（首次自动创建 `.env` 中配置的管理员账号）
- 首次签发证书（仅需一次）：`./deploy/init-letsencrypt.sh`（域名与邮箱见 `.env` 的 `DOMAIN` / `LETSENCRYPT_EMAIL`）

## 目录结构

```
backend/app/
  main.py        # 全部 API 路由（~1750 行，单文件）+ 启动时建管理员/SQLite 迁移/静态托管前端
  models.py      # ORM 模型与所有枚举（UserRole、TaskStatus、AnnouncementKind 等）
  schemas.py     # Pydantic 请求/响应模型（role 用 Literal["user","volunteer","staff","mascot"] 校验）
  dependencies.py# 权限收口：登录、监管权限与运营权限依赖
  security.py    # PBKDF2 密码哈希 + JWT 签发/校验（24h 会话）
  config.py      # pydantic-settings，读根目录 .env；含数据库备份、上传目录/私有媒体目录、看板娘配置
  database.py    # engine/SessionLocal；AppSession 挂自动快照（backup.py，每次写库后备份）
  backup.py      # 数据库自动快照，保留最近 db_backup_keep 份
  media.py       # 媒体分区（公开区 /uploads + 私有区 private_media）与短时签名 URL
  images.py      # 上传图片净化：解码校验、像素上限、剥 EXIF、统一静态重编码
  virtual_life*.py # 虚拟人生（/life）存档与内容包
  sugar_frost.py # 糖霜世界（/frost）存档：GET/PUT /api/sugar-frost/save，per-user 乐观锁
frontend/src/
  api.js         # axios 实例：自动带 token、401 时清缓存并派发 auth-expired
  constants.js   # 角色显示名 ROLE_LABELS / ROLE_HINTS / roleLabel()（⚠️ 改角色文案先看这里）
  stores/auth.js # Pinia：凭证经 authStorage.js 加密存于 localStorage/IndexedDB；isAdmin / isStaff / canManageRoles
  router.js      # 路由守卫（auth / guestOnly / roleManager）
  views/         # TaskHall(大厅) AdminView(后台) OperationsView(运营台) AnnouncementsView(公告) StoryHall(故事会)
                 # SugarClub(砂糖社) FriendHall(交友厅) VrMaps(地图推荐) 等
  components/    # TaskDialog(委托详情+接取) CreateTaskDialog ReportDialog FeedbackDialog StoryDetailDialog(故事会详情)
                 # UserProfileCard StatusBadge KanbanNiang(AI看板娘) AppHeader ToastHost TaskCard
                 # VrMapDetailDialog(地图详情) ImageLightbox(全屏图片放大，支持滚轮/双指缩放)
  frost/         # 糖霜世界(/frost) 因果解谜游戏：engine/(纯函数判定引擎，移植自 vrcWill)
                 # data/(12 关 JSON) + useFrostGame.js + frostSave.js + components/
  life/          # 虚拟人生(/life) 游戏内容与组件
backend/tests/   # pytest：test_api.py + test_security_media.py（安全回归）+ test_virtual_life*.py
frontend/scripts/verify-frost.mjs # 糖霜世界关卡穷举校验（node frontend/scripts/verify-frost.mjs）
```

## 领域模型速查（models.py）

- `User`：`role`（枚举值 `'user'|'volunteer'|'staff'|'mascot'`，SqlEnum 存字符串）+ `is_admin`（独立的更高级监管账号）+ `qq_public` + `max_concurrent_tasks`（并发接单上限）+ `title`（自定义称号，超管/管理员设置，纯展示）。
- `Announcement`：网站/活动公告，支持草稿、置顶和起止展示时间；`PageView` 保存隐私化页面访问事件（180 天留存）。
- `Task`：`status`（published→accepted→awaiting→completed；另有 cancelling/expired/cancelled）、`accept_password_hash`（只存哈希，便捷属性 `requires_password`）、`is_designated`（指定委托，designated_user_ids）、`is_anonymous`、`required_takers`、`is_visible/admin_note`（后台屏蔽）、`expires_at`（查询时惰性过期 `expire_due_tasks`）。
- `TaskMember`：接单人及 `response_status`（pending/accepted/declined）+ 完成确认 `confirmed_at` + 取消确认。
- 其余：`TaskReport`（举报）、`Feedback`（反馈）、`SugarProfile`/`SugarPair`（砂糖社）、`Story`/`StoryComment`/`StoryPhoto`（故事会：`Story.is_anonymous`；`StoryPhoto.is_visible` 默认 `False` 表示上传即待审，评论不匿名）、用户图片等。

## 权限体系（⚠️ 命名有历史包袱）

| 内部值 | 显示名 | 能力 |
|---|---|---|
| `is_admin=True` | **超级管理员** | 监管台全部：统计、反馈、授予 staff 角色、接单上限、重置密码；不接取委托 |
| `role='staff'` | **管理员**（历史名"店员"，内部值不改！） | 志愿者能力 + 管理非管理员账号的 user/volunteer 等级 + 查看处理举报/反馈 + 委托屏蔽/图片审核 + QQ 强制公开 |
| `role='mascot'` | **看板娘** | 管理网站/活动公告 + 查看页面活跃分析；不继承管理员、志愿者能力 |
| `role='volunteer'` | 志愿者 | 发布/接取全部委托 |
| `role='user'` | 普通用户 | 发布委托；凭**正确密码**可接取带密码委托；无密码委托直接接取 |

- 后端权限单一收口在 `dependencies.py`：`get_admin`（仅 is_admin）、`get_role_manager`（is_admin **或** staff）、`get_operations_manager`（is_admin **或** mascot）。改权限语义只动这里 + 各路由 Depends。
- 前端对应 `stores/auth.js` 的 `isAdmin` / `isStaff` / `isMascot` / `canManageRoles` / `canOperate`；显示名统一走 `constants.js` 的 `roleLabel()`。
- ⚠️ **不要**把 `'staff'` 改成 `'admin'` 之类的内部值：它是数据库存储值 + `schemas.py` Literal 校验 + 前端字面量三处联动，2026-09 已决策"只改显示名"。
- 授予或撤销 staff/mascot 角色仅超级管理员可做（`main.py` 的 `update_user_role`）。
- 授予或撤销 mascot 角色仅超级管理员可做；看板娘使用 `/operations`，不得复用 `/admin` 监管权限。

## 关键业务规则

1. **接取**（`POST /api/tasks/{id}/accept`）：管理员不能接、不能接自己的、指定委托仅名单内 pending 成员可响应；带密码须 `verify_password`；有并发上限（行锁 `with_for_update` 防超限）。
2. **开始**：`required_takers` 凑齐自动开始；不限人数只能手动开始。开始后报名关闭，可退出（leave）。
3. **完成**：委托人 + 全体接单人各自确认（confirm）才算 completed。
4. **取消**：双向发起 → cancelling → 委托人+全体接单人同意才取消，可 cancel-continue 作废。
5. **委托密码**：委托人可 `PATCH /api/tasks/{id}/password` 设置/重设（4-32 位），无密码委托设密后转为凭密码接取。
6. **可见性**：普通用户大厅只看 published；staff/admin 看全部状态；被举报委托对非相关人隐藏；匿名委托隐藏发布人。
7. **名录** `GET /api/staff`：公开管理员、风纪委员、看板娘与志愿者资料；管理员 QQ 对游客公开，志愿者仅在主动开启时公开，风纪委员与看板娘 QQ 不公开。
7.1 **称号**：`PATCH /api/admin/users/{id}/title`（`get_role_manager`：超管 + 管理员），自定义称号 ≤16 字、空串清空；**管理员只能设置普通用户/志愿者的称号**，超管、管理员、看板娘、风纪委员的称号仅超管可设置；用户本人不能自改（不在 `UserUpdate`）。字段随 `UserPublic/UserProfileOut/UserSelf/AdminUserOut` 下发，前端 `UserTitleTag.vue` 展示在成员名录、资料弹窗及全站昵称旁。
8. **反馈**：游客可提交（需联系方式）；`GET/PATCH /api/admin/feedback` 用 `get_role_manager`（staff 可处理）。
9. **举报**：有每日上限设置（`/api/admin/settings/report-limit`）；处理动作 close/hide/restore。
10. **砂糖社**：公开档案（照片存 `sugar_upload_path`）→ 互相 confirm 成 pair → 任一方 end；**砂糖榜只展示进行中（`active`）的关系**，已结束的 pair 仅保留在库中用于历史时长、不再出现在 `GET /api/sugar/pairs/top`，榜上取维持最久前三对。
10.1 **交友厅**（`/friends`，需登录）：每人一份 `FriendProfile`，登记**必填**「VRChat 中的昵称」（`vrc_nickname`，1-64 字，新增列已在 `migrate_schema()` 追加）与介绍，可传最多 5 张照片（审核后公开）；好友申请 `pending→accepted/rejected`，`accepted` 即互为好友。接口在 `/api/friends*`，照片审核在监管台「图片管理 → 交友照片」（`/api/admin/friends/photos*`）。
10.2 **大图放大**：砂糖社/交友厅/地图详情的照片、个人资料弹窗与「个人设置」的介绍图片，点击后用 `frontend/src/components/ImageLightbox.vue` 全屏放大（带缩放动效，支持滚轮/按钮/双击/双指缩放与拖动平移）；卡片封面点击行为不变。
11. **看板娘**：站内 AI 助手，走 Moonshot API（`mascot_*` 配置，未配 key 优雅降级）。
12. **首页公告弹窗**：游客每次进入首页都需确认当前公告；登录用户按账号在浏览器记录各公告的 `updated_at`，仅首次看到或公告更新后再次确认。
13. **地图实拍**：推荐地图时可附 3 张图片；此后每位用户可为同一地图上传最多 5 张实拍，单张最大 10 MB，审核通过后公开展示。
14. **糖霜世界**（`/frost`，任意登录用户可玩）：纯前端因果解谜游戏，12 关 / 45 设计结局 + 5 全局结局；进度按用户存于 `sugar_frost_saves`（`GET/PUT /api/sugar-frost/save`，revision CAS，409 表示其他页面已更新）。关卡数据/文案在 `frontend/src/frost/data/`，判定逻辑在 `frontend/src/frost/engine/`；改数据后跑 `node frontend/scripts/verify-frost.mjs` 校验可达性。
15. **故事会**（`/stories`，需登录）：用户可发布匿名或公开的故事（`Story.is_anonymous`，同一人可发多篇），可附最多 3 张配图（单张 ≤10 MB，需审核后才公开）；其他登录用户可评论（评论不匿名），评论可由评论作者、故事作者或管理员组（超管/`staff`）删除；故事可由作者本人或管理员组删除，删除时级联清理评论与磁盘图片。接口在 `/api/stories*`，配图审核在监管台「图片管理 → 故事配图」（`/api/admin/story-photos*`）。
16. **备案信息**（`/api/site-config`）：页脚展示 `.env` 里的 `SITE_ICP`，点击新窗口跳转 `SITE_ICP_URL`（默认工信部备案查询系统 `https://beian.miit.gov.cn/`），满足国内备案对"可点击跳转官方系统"的要求。留空则整行不展示。**备案号是私有信息，只从 `.env` 读，不得写进任何入库文件**（详见「约定与坑」）。`/life`、`/life-admin` 全屏游戏页不显示页脚。
17. **加载性能约定**（图片懒加载 + 骨架屏 + 按需请求）：
   - **图片**：所有展示后台内容图的 `<img>` 必须用 `frontend/src/components/LazyImage.vue`（IntersectionObserver 进入视口才请求 + shimmer 占位 + 淡入，单根 `<img>` 渲染以便 `.card > img` 等选择器继续生效）。**例外**（保持原生 `<img>`）：验证码、`ImageLightbox` 单张大图、`URL.createObjectURL` 的本地待上传预览、`life/**` 与 `vrclife/**` 游戏素材。
   - **骨架屏**：全局工具类在 `frontend/src/styles.css`（`.skeleton` 卡片 / `.skeleton-block` / `.skeleton-line` / `.skeleton-list`），各页加载期一律渲染骨架，不再用「正在加载…」纯文字。
   - **按需请求**：监管台 `/admin` 与运营台 `/operations` 均为**按标签页懒加载**（切换标签才请求，`loaded` 标记防重复）。监管台统计卡与各标签角标统一走 `GET /api/admin/summary`（`get_content_moderator`：超管 / `staff` / 风纪委员；仅超管返回用户与委托总量），它只做 COUNT 查询、不返回列表；运营台角标取自 `/api/operations/analytics` 的 `pending_beta_applications`。**注意 `/api/admin/stats` 仍是超管专属（`get_admin`），不要放宽**，测试已断言 `staff` 访问返回 403。
   - **路由分包**：`frontend/src/router.js` 全部页面用 `() => import()` 动态导入，不要改回静态 import。

## 安全加固（2026-09 起）

- **令牌版本**：`User.token_version`（JWT 载荷 `ver`）；`dependencies.py` 比对令牌与用户字段，不匹配即 401。改密/管理员重置密码时 `token_version += 1`，旧令牌立即失效。新增列需在 `migrate_schema()` 补 `ALTER TABLE users ADD COLUMN token_version`（`title` 列同理）。
- **自动登录令牌**：登录勾选「自动登录」时签发 7 天有效令牌（载荷含 `rm` 声明，`exp` 由 `remember_token_days` 决定，硬上限 7 天）；未勾选维持 24 小时。`security.py` 的 `decode_access_token` 按 `rm` 选择绝对上限（`REMEMBER_MAX_AGE_SECONDS` 7 天 / `SESSION_MAX_AGE_SECONDS` 24 小时）。**前端 `stores/auth.js` 的本地有效期窗口必须与之同步**（`REMEMBER_MAX_AGE_MS` / `LOGIN_MAX_AGE_MS`），否则会出现前端提前登出或后端拒绝。`token_version` 机制不变：7 天令牌在改密/重置后同样立即失效。
- **自助改密**必须带 `current_password`（`UserPasswordUpdate`）；管理员重置用 `AdminPasswordReset`（无此要求）。
- **限流**：`backend/app/ratelimit.py` 进程内滑动窗口，`enforce(bucket, key, limit, window)`；已用于登录（IP+账号）、注册、带密码接取、看板娘 `/mascot/chat`、反馈，以及 2026-09 补的 `page-view-ip`（IP，120/60s）、`upload`（用户，30/3600s，覆盖全部上传入口）、`board-post`（用户，20/600s）、`password-change`（用户，10/300s）。`BEHIND_PROXY=true` 时按 `X-Real-IP/X-Forwarded-For` 取真实 IP（compose 已设）。**pytest 下自动跳过**（否则测试会互相触发 429）。
- **媒体分区与签名访问**（`backend/app/media.py`，2026-09）：
  - 已过审的媒体在**公开区** `SUGAR_UPLOAD_DIR`（`/uploads` 静态托管）；待审/被屏蔽的媒体在**私有区** `MEDIA_PRIVATE_DIR`（默认上传目录同级 `private_media`，**不在任何静态挂载内**），只能通过 `GET /api/media/{key}?exp=&sig=` 校验 HMAC 签名后读取（`<img>` 带不了 Bearer 令牌，故签名即访问控制，TTL 见 `MEDIA_TOKEN_TTL_SECONDS`，默认 6h）。
  - `file_path` 列永远只存逻辑 key（如 `sugar/x.jpg`），**所在区由可见性推导**：URL 一律经 `media.media_url(key, public=...)` 生成，落盘用 `media.write_media(key, content, public=...)`，删除用 `media.delete_media(key)`（两区都删），审核翻转用 `media.place_media(key, public=...)` 搬区 —— 因此"审核驳回后旧公开地址立即失效"。
  - **新增上传/审核/删除路径必须走上面四个 helper**，不要手写 `settings.sugar_upload_path / path` 或 `unlink()`，否则会绕过分区与撤回语义。测试断言待审文件时用 `tmp_path / "private_media"`。
  - 启动对账 `sync_media_zones()`（`lifespan` 内，pytest 下跳过）把历史遗留的"已屏蔽但仍在公开区"文件搬进私有区。
  - `config.validate_storage_isolation()` 会拒绝把私有区放进公开区之内（否则等于没隔离），`validate_directories_writable()` 在启动时给出可执行的中文提示。
- **图片净化**（`backend/app/images.py`，2026-09）：所有上传入口（头像/资料图/砂糖/交友/故事/地图/life 素材/NPC 导入）都必须经 `normalize_image()` —— 魔数白名单 → 先读文件头判像素（`MAX_IMAGE_PIXELS` 25MP，挡压缩炸弹）→ `exif_transpose` 摆正 → 剥全部元数据（不传 exif/icc_profile）→ 长边 `MAX_IMAGE_EDGE` 2560 等比缩小 → 有 alpha 出 PNG，否则出 JPEG；动图只取首帧。**因此测试里不能再传"魔数 + 填充"的假图片**，用 `test_api.py` 的 `make_png()/make_jpeg()`。
- **⚠️ 不要给 ORM 模型加 `avatar_url` / `image_url` 属性**（`models.py` 已刻意移除）：`UserPublic`/`UserPhotoOut` 用 `from_attributes` 序列化，一旦 ORM 上有同名属性，任何"直接塞 ORM 对象进响应模型"的端点都会绕过 `avatar_visible`/`is_visible` 泄露未过审媒体地址（2026-09 已修 `present_sugar_profile`/`present_sugar_pair`/`present_feedback`）。新增相关端点必须走 `present_user_public()` / `visible_user_photos()` / `present_user_self()` / `present_admin_user()`。
- **默认值防护**：`config.py` 不再直接使用 `change-this-secret-in-production`/`Admin123!`；未配置 `SECRET_KEY` 时启动随机生成，首次创建管理员随机密码并打印日志，已存在且仍用默认密码的管理员会被自动轮换（pytest 下跳过以免动到真实库）。`SUGAR_UPLOAD_DIR` 不得指向数据库目录，否则启动报错。
- **前端权限**：`router.js` 对 `moderator/operations/life*/roleManager` 路由先 `await auth.restore()`（走 `/api/auth/me`）再判权限；`AdminView/OperationsView` 在 `onMounted` 再复核一次。**localStorage 的 `wsw_user` 只是界面缓存，绝不可作为权限依据**。
- **权限可信标记 `auth.verified`**：只有服务端响应（登录/注册或 `/auth/me`）才能把 `verified` 置为 true；`isAdmin/isStaff/isMascot/isDisciplinarian/role/canModerate/canManageRoles/canOperate/isBetaTester` 全部 `verified && ...`。组件里禁止直接读 `auth.user.role/is_admin`（用 `auth.role`/`auth.isAdmin`），这样改写 localStorage 也无法让界面误认为自己拥有权限。
- **请求模型**：`RequestModel` 设 `extra="forbid"`，请求体夹带 `role`/`is_admin` 等多余字段会被 422 拒绝（后端另有显式白名单赋值与 `update_user_role` 的角色保护，`is_admin` 无法经任何接口写入）。
- **本地凭证加密存储**：登录令牌/用户信息不再明文写 localStorage，改由 `frontend/src/authStorage.js` 用 Web Crypto AES-GCM 加密后写入 `wsw_auth`，密钥为不可导出的 `CryptoKey` 存于 IndexedDB；旧明文键（`wsw_token` 等）首次读取时自动迁移并删除。取 token 一律走 `getToken()/getTokenSync()`，禁止再直接读 localStorage。非安全上下文自动降级为“仅内存不落盘”。
- **登录/注册人机验证**：`backend/app/captcha.py`，`CAPTCHA_PROVIDER` 可选 `turnstile`（Cloudflare，推荐）或 `builtin`（Pillow 图形验证码）；前端 `composables/useCaptcha.js` + `components/CaptchaField.vue`。`login/register` 在校验密码前先 `verify_captcha`（fail-closed），pytest 下自动跳过。Turnstile Secret Key 只放 `.env`（`TURNSTILE_SECRET_KEY`），Site Key 公开。
- **公网入口只有 `edge`**：`docker-compose.yml` 中 `edge` 独占宿主机 80/443（TLS 终止 + HTTP 301 跳转 + HSTS），`frontend`/`backend` 一律不发布宿主机端口（dev 覆盖文件才把 `WEB_PORT` 加回 `frontend`）。**不要给 frontend/backend 增加 `ports`**，否则会绕过 HTTPS 出现明文入口。
- **真实客户端 IP**：`edge` 写入 `X-Real-IP`，`frontend/nginx.conf` 用 `real_ip` 模块（信任私网网段）还原后透传给后端，限流才按真实 IP 计数。改动代理层时务必保留这条链路，否则所有用户会被算作同一个来源。
- **响应头与 CSP**：`frontend/nginx.conf` 除基础安全头外下发 `Content-Security-Policy`（`default-src 'self'`，仅额外放行 Cloudflare Turnstile 的 script/connect/frame；`style-src` 需 `'unsafe-inline'` 供 Vue 的 `:style` 绑定；`img-src` 需 `data:` 供内置验证码、`blob:` 供上传前预览）。`/uploads/` 与 `/api/media/` 额外带 `default-src 'none'; sandbox`，使被直开的上传文件无法作为页面执行。**⚠️ nginx 的 `add_header` 不跨层级合并**：在 location 里加任何一个 `add_header`，server 层的其余安全头就全部失效，必须原样重复。后端也有一层 HTTP 中间件兜底（直连后端/Vite 代理场景）。改动站点引入第三方资源（字体、CDN 脚本）时必须同步放宽 CSP，否则会被浏览器拦截。
- **运行面加固**：`backend` 镜像以 `USER app`（UID 10001）运行，compose 里 `read_only: true` + `tmpfs: [/tmp]` + `cap_drop: [ALL]` + `no-new-privileges`；`frontend`/`edge` 只读根文件系统 + 内存临时目录（**`edge` 的 `/etc/nginx/conf.d` 必须挂 tmpfs**，entrypoint 要写入渲染后的配置）；`certbot` 保持可写但 `cap_drop: [ALL]`。因此宿主机 `backend/data` 必须对 UID 10001 可写：首次部署与旧版升级都要 `chown -R 10001:10001 backend/data`（`config.validate_directories_writable()` 会在启动时用中文提示这一点）。`docker-compose.dev.yml` 显式 `read_only: false`。
- **证书续期**：`certbot` 容器每 12h `certbot renew`，`edge` 容器每 6h `nginx -s reload` 加载新证书（不依赖 docker socket）。证书在宿主机 `deploy/certbot/conf/`（已 gitignore，含私钥）。首次签发用 `./deploy/init-letsencrypt.sh`；改域名/换证书后需重新执行并 `nginx -s reload`。

## 启动行为（main.py 顶部）

- 建表 + 若无管理员则按 `ADMIN_USERNAME/PASSWORD` bootstrap 创建；旧 SQLite 库自动 `ALTER TABLE` 补 `role` 列等轻量迁移（改枚举/加列时在此处追加）。
- 启动自检：`validate_storage_isolation()`（公开区/私有区/数据库目录互相隔离）+ `validate_directories_writable()`（不可写时给出 chown 提示），随后 `sync_media_zones()` 对账媒体分区（pytest 下跳过）。
- `GET /api/health` 健康检查；前端构建产物由后端静态托管（Docker 内）。

## 约定与坑

- 所有面向用户的错误信息为中文（`HTTPException(detail=...)`），前端 `errorMessage()` 直接展示 detail；改文案时前后端要同步（如 403 提示）。
- 配置全部走根目录 `.env`（见 `.env.example`），pydantic-settings 自动读取，环境变量名 = 字段大写。
- ⚠️ **私有信息（真实域名 `DOMAIN`、备案号 `SITE_ICP`、邮箱、密钥）只能写在根目录 `.env`**（已被 `.gitignore` 忽略）。**禁止**把真实值写进任何入库文件 —— 包括 `.env.example`、`docker-compose*.yml`、`README.md`、`AGENTS.md`、nginx 模板与源码；示例一律用 `example.com` 之类占位符。仓库要能公开。前端不保存这些值：页脚备案号通过 `GET /api/site-config` 运行时读取（`config.py` 的 `site_icp` / `site_icp_url`）。
- 测试用内存库，不经 AppSession（无自动快照）；测试断言与业务文案强耦合（如断言 detail 含"接取密码不正确"），改文案记得改测试。
- 多个测试模块共用同一个 FastAPI `app`，各自在 import 时设置 `get_db` 覆盖 —— **每个模块的 `setup_function` 里要重新指向自己的内存库**，否则会被别的模块抢走覆盖而报 "no such table"。
- 本地若无 Python 3.12，用 3.14 跑测试需 SQLAlchemy>=2.0.44（2.0.38 与 3.14 不兼容）；生产 Docker 是 3.12，requirements.txt 版本锁定不要随意升级。
- 前端登录缓存有版本号 `AUTH_CACHE_VERSION`（stores/auth.js），改 user 对象结构时递增可强制全员重新登录。
