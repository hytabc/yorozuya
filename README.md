# 万事屋委托站

一个可直接部署的委托发布与协作网站。前端使用 Vue 3 + Vite，后端使用 FastAPI + SQLAlchemy，默认以 SQLite 持久化数据。

## 功能

- 用户注册、登录与 JWT 会话；登录会话有效期为 24 小时，超过后需重新验证密码；登录时可勾选**自动登录**，勾选后 7 天内免登录（令牌有效期硬上限 7 天，改密或管理员重置密码会立即使其失效）；升级前浏览器遗留的登录缓存会自动失效；权限等级包括普通用户（默认，凭正确密码可接取带密码委托）、志愿者（可接取全部委托）与管理员（拥有志愿者权限并可管理用户等级、处理反馈）
- 超级管理员（监管台账号）可设置普通用户、志愿者与管理员；管理员只能把非管理员账号设置为普通用户或志愿者，不能授予管理员权限
- 发布委托时可选**有偿/无偿**、设置**需要几人接取**（1 人至不限人数）及固定有效期（1、2、3、5、10 天），并选择密码接取或无密码公开接取；选择无密码时会显示风险提示
- 发布委托时可选**匿名发布**：大厅中不公开昵称与个人资料，仅显示标题和内容；接取后联系方式仅委托人与接单人双方可见
- 有密码委托由所有非管理员用户凭密码接取（接单人联系委托人洽谈后获取密码）；无密码委托允许所有非管理员用户直接接取
- 接取人数凑齐后**自动开始**；委托人也可以随时手动点击“开始委托任务”（不限人数时只能手动开始）
- 委托开始前接单人可退出接取；开始后报名关闭
- **双向取消**：委托未完成前，委托人或任一接单人都可发起取消；需要委托人+全体接单人各自确认后才变为“已取消”，任一方也可随时选择继续委托使请求作废
- **全体确认验收**：委托人（发布人）与每一位接单人都需要各自确认完成，全部确认后委托才标记为已完成
- 成员名录中的管理员 QQ 对所有访客公开；志愿者 QQ 默认隐藏，可在个人设置中选择公开；委托双方仍强制可见彼此 QQ
- 首页提供**意见反馈**入口：登录用户或游客（需填联系方式）均可提交；管理员/超级管理员在后台查看、回复并标记处理，提交者可随时查看处理状态与回复
- 我的委托、个人昵称、QQ 号与简介设置
- 个人介绍页最多上传 3 张图片（单张不超过 5 MiB）；文件保存在服务端，数据库仅记录相对路径
- 成员名录和委托详情支持查看用户图片；管理员及超级管理员可在后台屏蔽或恢复不适合展示的图片
- 砂糖社：登记带照片的公开档案，查看卡片后通过仅对查看双方开放的 QQ 线下交流；双方确认后成为砂糖，任一方可结束关系，展示维持最久的前三对（含已结束记录）
- 交友厅：登记个人介绍与最多 5 张经审核照片，发起好友申请并查看好友数量排行榜
- 故事会：登录用户可发布匿名或公开的故事，同一人可写多篇；可附最多 3 张配图（单张不超过 10 MB），配图经管理员审核后公开；其他用户可评论，评论由评论者本人或故事作者删除，故事由作者本人或管理员删除
- 管理员统计、委托隐藏与恢复；隐藏原因对相关用户可见
- 看板娘「小白」：PC 端左上角常驻的站内 AI 助手，可聊天、答疑，自带倾听与心理支持模式（可配置，见下文）
- Docker Compose 一键部署：边缘 Nginx 终止 HTTPS（HTTP 强制跳转 + HSTS），Let's Encrypt 证书自动续期

## 🤖 看板娘「小白」（可选 AI 助手）

看板娘是本站的可选功能：PC 端（≥768px）左上角常驻一个可对话的站内助手，介绍功能、陪你聊天；**不配置 API Key 时聊天框显示“未启用”，不影响站点其它任何功能**。

**模型怎么配？** 小白对接的是**任意 OpenAI 兼容端点**，不用改代码，只需在 `.env` 里填三行：

```env
# 例 1:Moonshot
MASCOT_API_BASE=https://api.moonshot.cn/v1
MASCOT_API_KEY=sk-你的key
MASCOT_MODEL=kimi-k2.7-code-highspeed

# 例 2:DeepSeek(换服务只改这三行)
# MASCOT_API_BASE=https://api.deepseek.com/v1
# MASCOT_API_KEY=sk-你的key
# MASCOT_MODEL=deepseek-chat
```

| 配置 | 含义 |
|---|---|
| `MASCOT_API_BASE` | OpenAI 兼容接口地址(默认 Moonshot) |
| `MASCOT_API_KEY` | 你的 API Key;**留空 = 关闭看板娘聊天** |
| `MASCOT_MODEL` | 模型名(默认 kimi-k2.7-code-highspeed) |
| `MASCOT_MAX_TOKENS` | 单次回复上限(默认 1500) |

- 人设与开场白修改：后端 `backend/app/mascot.py` 的 `PERSONA`、前端 `frontend/src/components/KanbanNiang.vue`
- 会向模型发送最近的 16 条消息；本功能**不读取数据库**，不会泄露任何委托/用户数据

## 登录/注册人机验证

登录与注册默认启用 **Cloudflare Turnstile**，用于拦截暴力破解与批量注册。所有配置都在项目根目录 `.env`：

```env
CAPTCHA_ENABLED=true
CAPTCHA_PROVIDER=turnstile
TURNSTILE_SITE_KEY=0x4AAAAAAEwPP7x-AwVA_SVE
TURNSTILE_SECRET_KEY=你的secret
```

| 配置 | 含义 |
|---|---|
| `CAPTCHA_ENABLED` | `false` 则登录/注册不再要求验证码（不推荐生产环境关闭） |
| `CAPTCHA_PROVIDER` | `turnstile`（Cloudflare，推荐）或 `builtin`（站内图形验证码，不依赖第三方） |
| `TURNSTILE_SITE_KEY` | Turnstile 公开 Site Key（可入库） |
| `TURNSTILE_SECRET_KEY` | Turnstile Secret Key，**只能放服务端**；必填，否则校验永远失败 |

注意事项：

- 在 Cloudflare Turnstile 控制台把实际访问域名加入 Widget 的 **Allowed domains**（本地开发记得加 `localhost`），否则组件会报域名不匹配。
- 未配置 `TURNSTILE_SECRET_KEY` 时登录/注册会返回“人机验证未正确配置”；本地可用官方测试密钥 `1x0000000000000000000000000000000AA`（恒定通过）。
- 选择 `builtin` 时无需第三方服务，后端用 Pillow 生成图形验证码；Turnstile token 为一次性，校验失败后前端会自动重新挑战。

## Docker Compose 部署

默认部署会在构建镜像时将 Vue 前端编译为静态文件，并由 Nginx 提供服务及代理 `/api`。
浏览器首次访问不再等待 Vite 实时转换模块，静态资源也可直接缓存。

对外入口是 `edge` 容器（终止 TLS + 强制 HTTPS）；`frontend`、`backend` 只在内网互通，不映射宿主机端口。

1. 创建环境配置：

   ```bash
   cp .env.example .env
   ```

2. 修改 `.env` 中的 `SECRET_KEY` 和 `ADMIN_PASSWORD`（这两项在 Compose 中为必填，未填写会拒绝启动）。
   若直接以 `uvicorn`/`start.sh` 等方式运行且未配置，程序会拒绝使用内置占位值：
   `SECRET_KEY` 每次启动随机生成（重启后需重新登录），首次创建管理员时随机生成密码并打印到日志。
   推荐生成密钥：

   ```bash
   openssl rand -hex 32
   ```

3. 在 `.env` 中配置域名、证书邮箱与页脚备案号：

   ```env
   DOMAIN=example.com
   LETSENCRYPT_EMAIL=you@example.com
   CORS_ORIGINS=
   SITE_ICP=
   ```

   > ⚠️ 真实域名与备案号属于私有信息，**只写进 `.env`**（已被 `.gitignore` 忽略）。
   > 不要写进 `.env.example`、compose、README 等任何会提交到仓库的文件。

   同时确认该域名的 A/AAAA 记录已指向本机公网 IP，且云厂商安全组与主机防火墙已放行
   **80 与 443**（80 用于 ACME 挑战与跳转，不可关闭）。

4. 首次申请证书并启动：

   ```bash
   ./deploy/init-letsencrypt.sh
   ```

   脚本会先以「仅 HTTP」引导模式拉起 `edge`（同时启动 `frontend` 与 `backend`），校验 ACME 挑战目录可达后，
   通过 HTTP 挑战向 Let's Encrypt 申请正式证书，最后重启 `edge` 切换为 HTTPS。

   为避免反复调试触发 Let's Encrypt 速率限制，可先用 staging 试跑：

   ```bash
   CERTBOT_STAGING=1 ./deploy/init-letsencrypt.sh
   ```

   确认无误后把 `.env` 的 `CERTBOT_STAGING` 改回 `0` 并重新执行，换成浏览器信任的正式证书。

   浏览器访问 `https://<你的域名>`（即 `.env` 里的 `DOMAIN`）。首次启动会自动创建 `.env` 中配置的管理员账号。

   - 数据持久化：数据库通过绑定挂载保存在宿主机 `backend/data/wsw.db`，用户资料及砂糖社图片保存在同目录的 `backend/data/uploads/`
     （该目录已被 `.gitignore` 忽略）。详情见下方「数据存储与备份」；
   - **后端容器以非 root 用户（UID 10001）运行**，因此首次部署（以及从旧版本升级）时需要在宿主机执行一次：

     ```bash
     chown -R 10001:10001 backend/data
     ```

     否则启动日志会提示「数据库目录不可写」。之后新增的上传文件由容器内该用户创建，无需再改权限；
   - 部署代码更新后，运行 `docker compose up -d --build` 重新生成静态文件和镜像；
   - 证书已存在时可直接用 `docker compose up -d --build` 启动或更新，无需再跑初始化脚本；
   - 前端入口不缓存，带内容哈希的 JS/CSS 长期缓存，更新部署后浏览器会加载新版本。

### HTTPS 与证书续期

公网入口是 `edge`（配置模板 `deploy/nginx/edge.conf.template`）：80 端口只处理 ACME 挑战并 301 跳转 HTTPS，
443 终止 TLS 后转发给内网 `frontend`，并附加 `Strict-Transport-Security` 等安全响应头。

- **自动续期**：`certbot` 容器常驻，每 12 小时执行一次 `certbot renew`。Let's Encrypt 证书有效期 90 天，
  certbot 只在到期前 30 天内真正续期，因此大多数轮次是空跑，属正常现象。
- **新证书生效**：`edge` 容器内每 6 小时重新渲染配置并 `nginx -s reload`，加载续期后的证书（不依赖 docker socket）。
- **证书缺失时的行为**：`edge` 会自动切到「仅 HTTP」引导配置（只放行 ACME 挑战，其余请求返回 503），
  不会崩溃重启；重新签发证书后重启 `edge` 即恢复 HTTPS。
- **手动检查续期链路**：`docker compose exec certbot certbot renew --dry-run`
- **强制重签**：删除 `deploy/certbot/conf/live/<域名>`、`archive/<域名>`、`renewal/<域名>.conf` 后，
  重新执行 `./deploy/init-letsencrypt.sh`。
- **证书存放**：宿主机 `deploy/certbot/conf/`（已在 `.gitignore` 中忽略，**含私钥，注意权限与备份**）。
- **排查思路**：签发失败多半是 80 端口不通或 DNS 未生效，可先 `curl -I http://<你的域名>/.well-known/acme-challenge/测试文件` 验证；
  仓库中的 `deploy/certbot/www/` 就是 webroot 目录，可放个测试文件自测。
  触发速率限制时改用 `CERTBOT_STAGING=1` 试跑。

## Docker Compose 热部署开发

开发时叠加 `docker-compose.dev.yml`，即可保留原来的源码同步和页面自动刷新能力：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- 后端挂载 `./backend/app` 并通过 `uvicorn --reload` 运行，Python 文件变化后自动重载；
- 前端挂载 `./frontend` 并通过 Vite 运行，Vue、JavaScript、CSS 等文件变化后通过 HMR
  自动更新页面；`/api` 代理到 Compose 网络内的后端；
- 访问地址为 `http://localhost:<WEB_PORT>`（默认 `8080`）。该模式**只有明文 HTTP**（`edge`/`certbot` 已通过 profile 排除），
  仅供本机开发，绝不可用于公网；
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
2. **有密码委托**所有非管理员用户均可凭正确密码接取：接单人通过 QQ 洽谈，委托人同意后私下告知密码；密码错误会被拒绝；
3. **无密码委托**允许所有非管理员用户直接接取，无需委托人事先确认，因此发布时会明确提示占用名额及自动开始风险；
4. 人数凑齐时委托**自动开始**（进入“处理中”）；若选了“不限人数”，或想提前开工，
   委托人可点击“开始委托任务”手动开始；
5. 委托**开始后**不能再加入或退出；开始前接单人可随时退出接取；
6. **取消委托**：委托未完成（招募中/处理中/待确认）时，委托人或任一接单人可发起取消，
   进入“取消确认中”；委托人+全体接单人各自同意后才变为“已取消”，任一方也可选择继续委托使请求作废；
7. 协作结束时，**委托人**与**每一位接单人**各自点击确认完成——任一方都可先确认，进入“待确认”；
   全部确认后，委托才会变为“已完成”。

- 登录用户可看到待接取委托的联系方式；委托被接取后，联系方式仅协作成员互相可见。
- 匿名委托在接取前不公开发布人身份，也不对外显示接单名单；接取后双方联系方式互相可见。
- 委托人可在委托尚未开始时设置或重设接取密码；设置密码后，无密码委托会转为需凭密码接取。
- 到期状态会在查询委托或后台统计时自动更新。

> 升级提示：旧版单接单人委托（含更早“submitted/待验收”状态）会在启动时自动迁移进
> “接单人成员表”，并补齐“需要人数=1”；历史进行中的委托需要委托人再补一次确认即可完成。

## 安全说明

- **会话令牌**：JWT 有效期 24 小时；浏览器端以 Web Crypto AES-GCM 加密后存入 localStorage（键名 `wsw_auth`），密钥为不可导出的 `CryptoKey` 存于 IndexedDB，不再明文落盘；修改密码会自增令牌版本，旧密码签发的所有登录立即失效。
- **密码**：PBKDF2-HMAC-SHA256（31 万次迭代）；自助改密必须验证当前密码；超级管理员重置密码后对方需重新登录。
- **登录限流**：登录（按来源 IP 与账号双维度）、注册、带密码委托接取、看板娘对话、反馈提交均有滑动窗口限流，超限返回 429。
- **人机验证**：登录/注册默认要求 Cloudflare Turnstile（可切换站内图形验证码），服务端通过 siteverify 兜底校验，失败一律拒绝；配置见「登录/注册人机验证」。
- **权限校验**：前端所有权限标记（`auth.isAdmin`/`auth.role`/`canModerate` 等）都带 `verified` 前缀，
  只有服务端响应（登录/注册或 `/auth/me`）才能置为可信；路由与页面会先向服务端复核身份。
  因此即便手工改写本地缓存也无法让界面误认为自己拥有管理员权限（后端对每个接口独立鉴权）。
- **拒绝越权字段**：请求模型启用 `extra="forbid"`，请求体夹带 `role`/`is_admin` 等额外字段会返回 422；
  `is_admin` 无法通过任何接口写入，只有超级管理员能通过 `PATCH /admin/users/{id}/role` 调整 `staff`/`mascot`/`disciplinarian`。
- **上传与文件**：图片会先按文件头校验真实类型，再用 Pillow **真正解码**一次后重新编码：
  按拍摄方向摆正、剥离 EXIF/GPS 等全部元数据、限制单张像素（约 25 MP，先看文件头再解码，挡下压缩炸弹）
  与长边（2560 px）、动图只保留首帧；文件名由服务端生成 UUID。
  上传目录与数据库目录强制隔离，避免 `wsw.db` 与备份被静态托管下载。
- **待审媒体受控访问**：媒体分两个区 —— 已过审的文件在公开区 `backend/data/uploads/`，由 `/uploads` 静态托管；
  待审与被屏蔽的文件落在**公开目录之外**的 `backend/data/private_media/`，只能通过短时签名地址
  `/api/media/<key>?exp=&sig=` 访问（`<img>` 带不了 Bearer 令牌，所以签名即访问控制，默认有效期 6 小时）。
  审核通过时文件搬进公开区，驳回/屏蔽时搬回私有区，因此**撤回后旧公开地址立即失效**。
  升级到本版本时后端会在启动阶段做一次对账，把历史遗留的"已屏蔽但仍在公开区"的文件搬进私有区。
- **响应头**：Nginx 统一附加 `X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`、`Permissions-Policy`，
  并下发 `Content-Security-Policy`（`default-src 'self'`，仅额外放行 Cloudflare Turnstile）；
  `/uploads/` 与 `/api/media/` 额外带 `default-src 'none'; sandbox`，使任何被直接打开的上传文件都无法作为页面执行。
- **传输加密**：对外入口 `edge` 已内置 HTTPS（Let's Encrypt 自动续期）、HTTP 强制跳转与 HSTS，
  令牌与密码不再明文过网。部署时务必按上文配置 `DOMAIN` 与证书，不要绕过 `edge` 直接把前端/后端暴露到公网。
- **运行面加固**：`backend` 容器以非 root（UID 10001）运行，根文件系统只读、`/tmp` 为内存盘、丢弃全部 Linux
  capability 并禁止提权；`frontend`/`edge` 为只读根文件系统 + 内存临时目录（`edge` 的 `/etc/nginx/conf.d`
  必须挂 tmpfs，entrypoint 要写入渲染后的配置）。开发覆盖文件 `docker-compose.dev.yml` 会显式取消只读，
  仅用于本机且不可用于公网。
- **生产建议**：务必在 `.env` 设置足够随机的 `SECRET_KEY` 与强 `ADMIN_PASSWORD`。

## 邮箱验证与邮件通知

本站用邮箱做账号体系的一部分：注册必须验证邮箱、存量账号登录后强制补充绑定、可以用邮箱找回密码与换绑邮箱，
并且登录时还要再输入一次邮件验证码（二次验证）。邮件通过 **Brevo SMTP 中继** 发送。

### 功能一览

| 场景 | 行为 |
|---|---|
| 注册 | 必须填邮箱；注册成功后**不会直接登录**，需点击邮件里的验证链接 |
| 登录 | 登录名支持「用户名」或「邮箱」；已绑定并验证邮箱的账号，密码通过后还要输入邮件里的 6 位验证码 |
| 存量账号 | 旧账号没有邮箱，登录后会被强制要求绑定并验证；未完成前除「绑定邮箱 / 改密码 / 浏览」外的写操作都会被拒绝 |
| 忘记密码 | 用用户名或邮箱申请重置链接（30 分钟有效、一次性）；重置后所有旧登录立即失效 |
| 换绑邮箱 | 先向新地址发确认链接，确认后才生效；旧邮箱会收到变更提醒 |
| 事件通知 | 委托被接取/开始/完成/取消、委托被隐藏、反馈收到回复、志愿者与内测申请审核结果 |

通知邮件只发给「已验证邮箱 + 未关闭通知开关」的账号，正文不含 QQ 等联系方式。
公告类**不做群发**（会按用户数消耗 Brevo 配额且有滥用风险）。

### 配置（Brevo）

1. 在 Brevo 后台 → **SMTP & API → SMTP** 获取登录账号（形如 `xxxx@smtp-brevo.com`）并生成 SMTP key。
2. 在 Brevo 后台 → **Senders 验证一个发件地址**（或验证你的域名）。
   ⚠️ `EMAIL_FROM_ADDRESS` 必须是**已验证的发件地址**，否则中继会返回 554/550 拒收。
3. 把凭据写进根目录 `.env`（**该文件已被 `.gitignore` 忽略，密钥绝不要写进任何入库文件**）：

   ```bash
   EMAIL_DELIVERY=smtp
   SMTP_HOST=smtp-relay.brevo.com
   SMTP_PORT=587
   SMTP_USERNAME=xxxx@smtp-brevo.com
   SMTP_PASSWORD=你的-SMTP-key
   EMAIL_FROM_ADDRESS=no-reply@你的域名
   EMAIL_FROM_NAME=万事屋委托站
   SITE_BASE_URL=https://你的域名   # 邮件里链接的前缀，建议显式填写
   ```

4. `docker compose up -d --build` 重启后端使配置生效。

本地开发不想配 SMTP 时，设 `EMAIL_DELIVERY=log`：邮件不会真的发出，而是打印到后端日志里（可直接复制验证链接）。

### 策略开关

| 变量 | 默认 | 说明 |
|---|---|---|
| `LOGIN_CODE_REQUIRED` | `true` | 登录是否要求邮箱验证码。**关掉可让登录只靠密码+人机验证** |
| `REQUIRE_EMAIL_VERIFICATION` | `true` | 未验证邮箱是否封锁写操作 |
| `NOTIFY_EMAIL_ENABLED` | `true` | 事件通知邮件总开关 |
| `EMAIL_VERIFICATION_TTL_HOURS` | `24` | 验证/换绑链接有效期 |
| `PASSWORD_RESET_TTL_MINUTES` | `30` | 重置密码链接有效期 |
| `LOGIN_CODE_TTL_MINUTES` | `10` | 登录验证码有效期（连错 5 次作废） |
| `EMAIL_SEND_COOLDOWN_SECONDS` | `60` | 同一账号同一用途的最小发信间隔 |

### ⚠️ 被锁住时的救援步骤

邮件服务出问题时（密钥失效、Brevo 拒收发件地址、配额用尽），会影响注册、验证、找回密码与登录验证码。
**超级管理员（`is_admin`）不受验证闸门限制**，可在后台处理日常事务；若连登录验证码都收不到，按下面顺序恢复：

1. 在 `.env` 里把 `LOGIN_CODE_REQUIRED=false`（先能登录）→ `docker compose up -d` 重启后端；
2. 修好邮件配置后，再把它改回 `true`；
3. 若大量存量用户被卡在验证上，可临时 `REQUIRE_EMAIL_VERIFICATION=false` 放行写操作，恢复后改回 `true`。

### 相关约定

- 邮件里的链接令牌**只以哈希入库**（`email_tokens` 表），一次性、限时，用后作废；
- 重置密码等同确认了邮箱控制权，因此会把该邮箱标记为已验证，并使全部旧会话失效；
- 「账号是否存在」不会被泄露：重发验证信与申请重置密码接口对不存在的账号同样返回成功。

## 数据存储与备份

- **数据库位置**：Compose 将宿主机目录 `backend/data/` 绑定挂载到容器内 `/data`，
  数据库文件即宿主机上的 `backend/data/wsw.db`。因此：
  - 每次 `docker compose up -d --build`（更新部署）后数据依然保留，不会丢失；
  - 随时可用任意 SQLite 工具（如 DB Browser for SQLite、`sqlite3`）直接打开该外部路径查看。
- **图片位置**：用户资料图片位于 `backend/data/uploads/users/<用户ID>/`，交友厅图片位于
  `backend/data/uploads/friends/<用户ID>/`，砂糖社图片位于 `backend/data/uploads/sugar/`。
  数据库只保存相对路径和用户图片的展示状态；整个 `backend/data/`
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
