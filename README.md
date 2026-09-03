# 万事屋委托站

一个可直接部署的委托发布与协作网站。前端使用 Vue 3 + Vite，后端使用 FastAPI + SQLAlchemy，默认以 SQLite 持久化数据。

## 功能

- 用户注册、登录与 JWT 会话；权限等级包括普通用户（默认，可接取无密码委托）、志愿者（可接取全部委托）与店员（拥有志愿者权限并可管理用户等级）
- 管理员可设置普通用户、志愿者与店员；店员只能把非管理员账号设置为普通用户或志愿者，不能授予店员权限
- 发布委托时可选**有偿/无偿**、设置**需要几人接取**（1 人至不限人数），并选择密码接取或无密码公开接取；选择无密码时会显示风险提示
- 有密码委托由志愿者或店员联系委托人洽谈并凭密码接取；无密码委托允许所有非管理员用户直接接取
- 接取人数凑齐后**自动开始**；委托人也可以随时手动点击“开始委托任务”（不限人数时只能手动开始）
- 委托开始前接单人可退出接取；开始后报名关闭
- **双向取消**：委托未完成前，委托人或任一接单人都可发起取消；需要委托人+全体接单人各自确认后才变为“已取消”，任一方也可随时选择继续委托使请求作废
- **全体确认验收**：委托人（发布人）与每一位接单人都需要各自确认完成，全部确认后委托才标记为已完成
- 成员名录中的店员 QQ 对所有访客公开；志愿者 QQ 默认隐藏，可在个人设置中选择公开；委托双方仍强制可见彼此 QQ
- 首页提供**意见反馈**入口：登录用户或游客（需填联系方式）均可提交；管理员在监管台查看、回复并标记处理，提交者可随时查看处理状态与回复
- 我的委托、个人昵称、QQ 号与简介设置
- 个人介绍页最多上传 3 张图片（单张不超过 5 MiB）；文件保存在服务端，数据库仅记录相对路径
- 成员名录和委托详情支持查看用户图片；店员及管理员可在监管台屏蔽或恢复不适合展示的图片
- 砂糖社：登记带照片的公开档案，查看卡片后通过仅对查看双方开放的 QQ 线下交流；双方确认后成为砂糖，任一方可结束关系，展示维持最久的前三对（含已结束记录）
- 管理员统计、委托隐藏与恢复；隐藏原因对相关用户可见
- Docker Compose 一键部署与 FRP TCP 内网穿透

## Docker Compose 部署

默认部署会在构建镜像时将 Vue 前端编译为静态文件，并由 Nginx 提供服务及代理 `/api`。
浏览器首次访问不再等待 Vite 实时转换模块，静态资源也可直接缓存。

1. 创建环境配置：

   ```bash
   cp env.example .env
   ```

2. 修改 `.env` 中的 `SECRET_KEY` 和 `ADMIN_PASSWORD`。推荐生成密钥：

   ```bash
   openssl rand -hex 32
   ```

   同时设置 `STAFF_GROUP_ID`。普通用户打开无法接取的有密码委托时，页面会展示该群聊 ID，并引导其联系店员申请志愿者权限。

3. 启动（首次或重新部署）：

   ```bash
   docker compose up -d --build
   ```

   浏览器访问 `http://localhost:<WEB_PORT>`（默认 `8080`）。首次启动会自动创建 `.env` 中配置的管理员账号。

   - 数据持久化：数据库通过绑定挂载保存在宿主机 `backend/data/wsw.db`，用户资料及砂糖社上传图片保存在同目录的 `backend/data/uploads/`
     （该目录已被 `.gitignore` 忽略）。详情见下方「数据存储与备份」；
   - 部署代码更新后，运行 `docker compose up -d --build` 重新生成静态文件和镜像；
   - 前端入口不缓存，带内容哈希的 JS/CSS 长期缓存，更新部署后浏览器会加载新版本。

4. 启用 FRP 内网穿透（可选）：先在 `.env` 填写 `FRP_SERVER_ADDR`、`FRP_TOKEN` 和远端端口，再运行：

   ```bash
   docker compose --profile tunnel up -d
   ```

   `frpc`（仅该 profile 启动）会把远端 `FRP_REMOTE_PORT` 转发到前端容器的 80 端口。
   对应的 `frps` 服务端需允许该 TCP 端口。

## Docker Compose 热部署开发

开发时叠加 `docker-compose.dev.yml`，即可保留原来的源码同步和页面自动刷新能力：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- 后端挂载 `./backend/app` 并通过 `uvicorn --reload` 运行，Python 文件变化后自动重载；
- 前端挂载 `./frontend` 并通过 Vite 运行，Vue、JavaScript、CSS 等文件变化后通过 HMR
  自动更新页面；`/api` 代理到 Compose 网络内的后端；
- 访问地址仍为 `http://localhost:<WEB_PORT>`（默认 `8080`）；
- `node_modules` 保留在容器卷中，避免宿主机与 Linux 容器的依赖不兼容；
- 修改依赖清单后需要再次加 `--build`，只改源码无需重建镜像。

后台运行时可在命令末尾加 `-d`。停止该开发环境：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

## 本地启动（不使用 Docker）

设备需预先安装 Python 3.10+ 和 Node.js 20.19+（或 22.12+）。脚本首次运行会创建
`backend/.venv`、安装前后端依赖，并同时启动 FastAPI 与 Vite。后端代码变化后自动重载，
前端代码变化后页面通过 HMR 自动更新；数据库仍保存在 `backend/data/wsw.db`。

macOS / Linux：

```bash
chmod +x start.sh
./start.sh
```

Windows：

```bat
start.bat
```

浏览器访问 `http://127.0.0.1:8080`。macOS / Linux 按 `Ctrl+C` 会同时停止两个服务；
Windows 会分别打开后端和前端命令窗口，关闭这两个窗口即可停止。

运行自动化测试（后端测试 + 前端生产构建）：

```bash
./start.sh test
```

```bat
start.bat test
```

可通过 `WEB_PORT`、`BACKEND_PORT` 环境变量修改端口。依赖已安装且未修改依赖清单时，
可设置 `SKIP_INSTALL=1` 加快启动。后端会读取项目根目录 `.env` 中的管理员及密钥配置；
未创建 `.env` 时使用仅适合本地测试的默认值。

## 状态流转

```text
已发布/招募中(published) -> 处理中/进行中(accepted) -> 待确认(awaiting) -> 已完成(completed)
    |    （凑齐所需人数自动开始，或委托人手动开始）
    |
    +----------------> 已过期
    |
    +-> 取消确认中(cancelling) --全员同意--> 已取消(cancelled)
        （任一方发起；任一方也可选择“继续委托”使请求作废并恢复原状态）
```

### 接单与完成逻辑（可多人协作）

1. **委托人**发布委托时设置「需要几人接取」（1-999，或选不限人数），并选择密码接取或无密码接取；
2. **有密码委托**仅志愿者和店员可接取：接单人通过 QQ 洽谈，委托人同意后私下告知密码；普通用户可通过公开店员名录联系店员申请调整权限；
3. **无密码委托**允许所有非管理员用户直接接取，无需委托人事先确认，因此发布时会明确提示占用名额及自动开始风险；
4. 人数凑齐时委托**自动开始**（进入“处理中”）；若选了“不限人数”，或想提前开工，
   委托人可点击“开始委托任务”手动开始；
5. 委托**开始后**不能再加入或退出；开始前接单人可随时退出接取；
6. **取消委托**：委托未完成（招募中/处理中/待确认）时，委托人或任一接单人可发起取消，
   进入“取消确认中”；委托人+全体接单人各自同意后才变为“已取消”，任一方也可选择继续委托使请求作废；
7. 协作结束时，**委托人**与**每一位接单人**各自点击确认完成——任一方都可先确认，进入“待确认”；
   全部确认后，委托才会变为“已完成”。

- 登录用户可看到待接取委托的联系方式；委托被接取后，联系方式仅协作成员互相可见。
- 委托人可在委托尚未开始时设置或重设接取密码；设置密码后，无密码委托会转为仅志愿者或店员可凭密码接取。
- 到期状态会在查询委托或后台统计时自动更新。

> 升级提示：旧版单接单人委托（含更早“submitted/待验收”状态）会在启动时自动迁移进
> “接单人成员表”，并补齐“需要人数=1”；历史进行中的委托需要委托人再补一次确认即可完成。

## 数据存储与备份

- **数据库位置**：Compose 将宿主机目录 `backend/data/` 绑定挂载到容器内 `/data`，
  数据库文件即宿主机上的 `backend/data/wsw.db`。因此：
  - 每次 `docker compose up -d --build`（更新部署）后数据依然保留，不会丢失；
  - 随时可用任意 SQLite 工具（如 DB Browser for SQLite、`sqlite3`）直接打开该外部路径查看。
- **图片位置**：用户资料图片位于 `backend/data/uploads/users/<用户ID>/`，砂糖社图片位于
  `backend/data/uploads/sugar/`。数据库只保存相对路径和用户图片的展示状态；整个 `backend/data/`
  已绑定到容器 `/data`，重建容器不会丢失图片。
- **自动快照**：每次有内容写入并成功提交后，后端会自动把数据库快照为带时间戳的副本，
  存到同目录 `backend/data/backups/wsw-YYYYMMDD-HHMMSS.db`，并只保留最近
  `DB_BACKUP_KEEP`（默认 100）份，更早的自动清理。
  这样每次用户发布/更新内容都会留档，需要时可按时间点恢复。
- **手动快照**：容器运行中执行
  `docker compose exec backend python -c "from app.backup import take_snapshot; take_snapshot()"`。
- **恢复快照**：停止后端后，用备份文件覆盖主数据库即可，例如
  `cp backend/data/backups/wsw-<时间戳>.db backend/data/wsw.db`，再 `docker compose up -d`。

### 从旧版 wsw_data 数据卷迁移

若之前用命名卷 `wsw_data` 运行过且其中已有数据，切换为绑定挂载后不会自动带上旧数据，
请先停止容器并执行一次迁移（把卷里的 `wsw.db` 复制到宿主机目录）。在项目根目录运行：

```bash
docker compose stop backend
docker run --rm \
  -v "$(basename "$PWD")_wsw_data:/src" \
  -v "$PWD/backend/data:/dst" \
  alpine sh -c "cp /src/wsw.db /dst/wsw.db && ls -la /dst"
docker compose up -d
```

> 卷名通常是 `仓库名_wsw_data`，可用 `docker volume ls | grep wsw` 确认后再替换上文的卷名。
