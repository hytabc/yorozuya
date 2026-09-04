# AGENTS.md — 万事屋委托站项目速览

> 本文件面向 AI 助手/后续维护者：先读这里再改代码，避免全库探索。最后更新：2026-09。

## 一句话概述

面向 VRChat 社区的委托发布与协作网站（"万事屋"）：委托人发布委托（可带密码/指定接单人/匿名），接单人凭密码或直接接取，全员确认后完成；含用户权限等级、举报/反馈、成员名录、砂糖社档案、AI 看板娘等模块。

## 技术栈与运行

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy 2.0（ORM）+ Pydantic v2 + pydantic-settings，默认 SQLite（`data/wsw.db`），JWT（HTTPBearer）认证 |
| 前端 | Vue 3（`<script setup>`）+ Pinia + Vue Router + Vite + axios + lucide-vue-next 图标 |
| 部署 | Docker Compose（`docker-compose.yml`，prod/dev 两套）+ FRP 内网穿透（`deploy/frpc.toml`）；根目录 `start.sh` / `start.bat` 一键启动 |
| 测试 | 后端 pytest（`backend/tests/test_api.py`，TestClient + 内存库，约 34 个用例） |

命令：
- 后端测试：`cd backend && python -m pytest tests -q`
- 前端开发/构建：`cd frontend && npm run dev` / `npm run build`
- 生产：`docker compose up -d --build`（首次自动创建 `.env` 中配置的管理员账号）

## 目录结构

```
backend/app/
  main.py        # 全部 API 路由（~1750 行，单文件）+ 启动时建管理员/SQLite 迁移/静态托管前端
  models.py      # ORM 模型与所有枚举（UserRole、TaskStatus、FeedbackStatus、ReportStatus 等）
  schemas.py     # Pydantic 请求/响应模型（role 用 Literal["user","volunteer","staff"] 校验）
  dependencies.py# 权限收口：get_current_user / get_optional_user / get_admin / get_role_manager
  security.py    # PBKDF2 密码哈希 + JWT 签发/校验（24h 会话）
  config.py      # pydantic-settings，读根目录 .env；含数据库备份、砂糖上传目录、看板娘配置
  database.py    # engine/SessionLocal；AppSession 挂自动快照（backup.py，每次写库后备份）
  backup.py      # 数据库自动快照，保留最近 db_backup_keep 份
frontend/src/
  api.js         # axios 实例：自动带 token、401 时清缓存并派发 auth-expired
  constants.js   # 角色显示名 ROLE_LABELS / ROLE_HINTS / roleLabel()（⚠️ 改角色文案先看这里）
  stores/auth.js # Pinia：token/user 持久化到 localStorage；isAdmin / isStaff / canManageRoles
  router.js      # 路由守卫（auth / guestOnly / roleManager）
  views/         # TaskHall(大厅) MyTasks ProfileView AdminView(后台) StaffView(名录) SugarClub LoginView
  components/    # TaskDialog(委托详情+接取) CreateTaskDialog ReportDialog FeedbackDialog
                 # UserProfileCard StatusBadge KanbanNiang(AI看板娘) AppHeader ToastHost TaskCard
```

## 领域模型速查（models.py）

- `User`：`role`（枚举值 `'user'|'volunteer'|'staff'`，SqlEnum 存字符串）+ `is_admin`（独立的更高级监管账号）+ `qq_public` + `max_concurrent_tasks`（并发接单上限）。
- `Task`：`status`（published→accepted→awaiting→completed；另有 cancelling/expired/cancelled）、`accept_password_hash`（只存哈希，便捷属性 `requires_password`）、`is_designated`（指定委托，designated_user_ids）、`is_anonymous`、`required_takers`、`is_visible/admin_note`（后台屏蔽）、`expires_at`（查询时惰性过期 `expire_due_tasks`）。
- `TaskMember`：接单人及 `response_status`（pending/accepted/declined）+ 完成确认 `confirmed_at` + 取消确认。
- 其余：`TaskReport`（举报）、`Feedback`（反馈）、`SugarProfile`/`SugarPair`（砂糖社）、用户图片等。

## 权限体系（⚠️ 命名有历史包袱）

| 内部值 | 显示名 | 能力 |
|---|---|---|
| `is_admin=True` | **超级管理员** | 监管台全部：统计、反馈、授予 staff 角色、接单上限、重置密码；不接取委托 |
| `role='staff'` | **管理员**（历史名"店员"，内部值不改！） | 志愿者能力 + 管理非管理员账号的 user/volunteer 等级 + 查看处理举报/反馈 + 委托屏蔽/图片审核 + QQ 强制公开 |
| `role='volunteer'` | 志愿者 | 发布/接取全部委托 |
| `role='user'` | 普通用户 | 发布委托；凭**正确密码**可接取带密码委托；无密码委托直接接取 |

- 后端权限单一收口在 `dependencies.py`：`get_admin`（仅 is_admin）、`get_role_manager`（is_admin **或** staff，用于后台管理类接口）。改权限语义只动这里 + 各路由 Depends。
- 前端对应 `stores/auth.js` 的 `isAdmin`（is_admin）/`isStaff`（role==='staff' 且非 admin）/`canManageRoles`；显示名统一走 `constants.js` 的 `roleLabel()`。
- ⚠️ **不要**把 `'staff'` 改成 `'admin'` 之类的内部值：它是数据库存储值 + `schemas.py` Literal 校验 + 前端字面量三处联动，2026-09 已决策"只改显示名"。
- 授予 staff 角色仅超级管理员可做（`main.py` update_user_role，403 文案"只有超级管理员可以授予管理员权限"）。

## 关键业务规则

1. **接取**（`POST /api/tasks/{id}/accept`）：管理员不能接、不能接自己的、指定委托仅名单内 pending 成员可响应；带密码须 `verify_password`；有并发上限（行锁 `with_for_update` 防超限）。
2. **开始**：`required_takers` 凑齐自动开始；不限人数只能手动开始。开始后报名关闭，可退出（leave）。
3. **完成**：委托人 + 全体接单人各自确认（confirm）才算 completed。
4. **取消**：双向发起 → cancelling → 委托人+全体接单人同意才取消，可 cancel-continue 作废。
5. **委托密码**：委托人可 `PATCH /api/tasks/{id}/password` 设置/重设（4-32 位），无密码委托设密后转为凭密码接取。
6. **可见性**：普通用户大厅只看 published；staff/admin 看全部状态；被举报委托对非相关人隐藏；匿名委托隐藏发布人。
7. **名录** `GET /api/staff`：staff 分组（QQ 对游客公开）+ 公开 QQ 的志愿者；`STAFF_GROUP_ID` 为权限申请群聊 ID。
8. **反馈**：游客可提交（需联系方式）；`GET/PATCH /api/admin/feedback` 用 `get_role_manager`（staff 可处理）。
9. **举报**：有每日上限设置（`/api/admin/settings/report-limit`）；处理动作 close/hide/restore。
10. **砂糖社**：公开档案（照片存 `sugar_upload_path`）→ 互相 confirm 成 pair → 任一方 end；展示维持最久前三对。
11. **看板娘**：站内 AI 助手，走 Moonshot API（`mascot_*` 配置，未配 key 优雅降级）。

## 启动行为（main.py 顶部）

- 建表 + 若无管理员则按 `ADMIN_USERNAME/PASSWORD` bootstrap 创建；旧 SQLite 库自动 `ALTER TABLE` 补 `role` 列等轻量迁移（改枚举/加列时在此处追加）。
- `GET /api/health` 健康检查；前端构建产物由后端静态托管（Docker 内）。

## 约定与坑

- 所有面向用户的错误信息为中文（`HTTPException(detail=...)`），前端 `errorMessage()` 直接展示 detail；改文案时前后端要同步（如 403 提示）。
- 配置全部走根目录 `.env`（见 `.env.example`），pydantic-settings 自动读取，环境变量名 = 字段大写。
- 测试用内存库，不经 AppSession（无自动快照）；测试断言与业务文案强耦合（如断言 detail 含"接取密码不正确"），改文案记得改测试。
- 本地若无 Python 3.12，用 3.14 跑测试需 SQLAlchemy>=2.0.44（2.0.38 与 3.14 不兼容）；生产 Docker 是 3.12，requirements.txt 版本锁定不要随意升级。
- 前端登录缓存有版本号 `AUTH_CACHE_VERSION`（stores/auth.js），改 user 对象结构时递增可强制全员重新登录。
