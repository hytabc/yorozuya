# 万事屋委托站

一个可直接部署的委托发布与协作网站。前端使用 Vue 3 + Vite，后端使用 FastAPI + SQLAlchemy，默认以 SQLite 持久化数据。

## 功能

- 用户注册、登录与 JWT 会话
- 发布委托时设置**接取密码**，设置分类、报酬说明和 1 小时至 90 天的有效期
- 接单人浏览委托、通过委托详情中的 QQ 联系委托人洽谈；谈妥后委托人把接取密码告知对方
- 接单人凭密码接取委托；密码仅以哈希保存，任何接口都不会回传明文
- **双向完成确认**：委托人、接单人任一方可先“确认完成”，双方都确认后委托才标记为已完成
- 委托完成前委托人可重设接取密码（例如想改让另一位接单人接取）
- 我的委托、个人昵称、QQ 号与简介设置
- 管理员统计、委托隐藏与恢复；隐藏原因对相关用户可见
- Docker Compose 一键部署与 FRP TCP 内网穿透

## Docker Compose 部署

1. 创建环境配置：

   ```bash
   cp .env.example .env
   ```

2. 修改 `.env` 中的 `SECRET_KEY` 和 `ADMIN_PASSWORD`。推荐生成密钥：

   ```bash
   openssl rand -hex 32
   ```

3. 启动网站：

   ```bash
   docker compose up -d --build
   ```

   浏览器访问 `http://localhost:8080`。首次启动会自动创建 `.env` 中配置的管理员账号。

   > 数据库不再保存在 Docker 命名卷中，而是通过绑定挂载存放在宿主机
   > `backend/data/wsw.db`（该目录已被 `.gitignore` 忽略）。详情见下方「数据存储与备份」。

4. 启用 FRP 穿透：先在 `.env` 填写 `FRP_SERVER_ADDR`、`FRP_TOKEN` 和远端端口，再运行：

   ```bash
   docker compose --profile tunnel up -d --build
   ```

   `frpc` 会将远端 `FRP_REMOTE_PORT` 转发到前端容器的 80 端口。对应的 `frps` 服务端需允许该 TCP 端口。

## 本地开发

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

Vite 开发环境可通过 `VITE_API_BASE=http://localhost:8000/api` 指向本地后端。生产容器由 Nginx 同源代理 `/api`。

## 状态流转

```text
已发布(待接取) -> 处理中(凭密码接取) -> 待确认(任一方先确认) -> 已完成(双方均确认)
    |                                                         |
    +-------------------------------> 已过期
    |
    +-> 已取消（仅委托人、尚未被接取时）
```

### 接单与完成逻辑

1. **委托人**发布委托并设置接取密码；
2. **接单人**在大厅看到委托，通过详情中的 QQ 联系委托人洽谈；
3. **委托人**同意后把接取密码私下告知该接单人；
4. **接单人**在站内输入密码完成接取，委托进入“处理中”；
5. 协作结束时，**委托人**与**接单人**各自确认完成——任一方都可先确认，进入“待确认”；
   只有双方都确认后，委托才会变为“已完成”。

- 登录用户可看到待接取委托的联系方式；委托被接取后，联系方式仅协作双方互相可见。
- 委托人可在委托尚未被接取时重设接取密码，旧密码立即失效。
- 到期状态会在查询委托或后台统计时自动更新。

> 升级提示：旧版“已提交待验收(submitted)”数据会在启动时自动迁移为“待确认(awaiting)”，
> 并把原提交时间记录为接单人的确认时间，需要委托人补一次确认即可完成。

## 数据存储与备份

- **数据库位置**：Compose 将宿主机目录 `backend/data/` 绑定挂载到容器内 `/data`，
  数据库文件即宿主机上的 `backend/data/wsw.db`。因此：
  - 每次 `docker compose up -d --build`（更新部署）后数据依然保留，不会丢失；
  - 随时可用任意 SQLite 工具（如 DB Browser for SQLite、`sqlite3`）直接打开该外部路径查看。
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
