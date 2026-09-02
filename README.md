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

到期状态会在查询委托或后台统计时自动更新。数据库文件保存在 Compose 的 `wsw_data` 数据卷中。
