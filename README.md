# 万事屋委托站

一个可直接部署的委托发布与协作网站。前端使用 Vue 3 + Vite，后端使用 FastAPI + SQLAlchemy，默认以 SQLite 持久化数据。

## 功能

- 用户注册、登录与 JWT 会话
- 发布委托，设置分类、报酬说明和 1 小时至 90 天的有效期
- 接受委托、提交完成、发布者验收的完整状态流转
- 已发布（绿）、处理中/待验收（黄）、已过期（红）等状态展示
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
已发布 -> 处理中 -> 待验收 -> 已完成
   |          |          |
   +----------+----------+-> 已过期
   |
   +-> 已取消（仅发布者、尚未接单时）
```

到期状态会在查询委托或后台统计时自动更新。

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
