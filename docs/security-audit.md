# 安全审计与处理清单（2026-09）

本次交付为仓库修复与上线清单，尚未部署生产。审计覆盖认证/权限、邮箱恢复、用户媒体、前端凭证使用、代理配置和依赖公告；使用内存/临时 SQLite 库与模拟文件失败复现问题，没有针对线上账号执行写操作或压力测试。线上首页只做 HTTP/HTTPS 响应头检查，已确认 HTTPS 跳转、HSTS、CSP 生效，不代表已验证生产配置或主机安全。

## 问题与处理结果

| 编号 | 优先级、触发条件与影响 | 证据和修复 | 状态 |
|---|---|---|---|
| S1 | 高：登录令牌泄露后，无需密码即可申请换绑，可能进一步接管账号 | 旧 `/api/users/me/email` 仅传 email 返回 200；现在首次绑定与换绑均要求当前密码，10 次/5 分钟限制；两个前端入口同步 | 代码已修复，待上线 |
| S2 | 高：改密后旧重置/换绑邮件链接仍有效，可再次改密或改变邮箱 | 隔离复现两个旧链接在改密后均返回 200；现在令牌记录凭证版本，条件 UPDATE 串行化，四类凭证变更撤销旧链接和会话 | 代码已修复，待上线 |
| S3 | 高：磁盘权限/空间/数据库失败时，审核返回成功但图片仍公开 | 旧 `place_media` 吞异常且审核先提交；现在严格搬区/删除、失败 503、补偿保持私有、启动对账失败阻止启动，公开读取再查数据库，阻止隐藏/孤儿副本 | 代码已修复，待上线 |
| S4 | 中，配置相关：未设固定来源时伪造 Host 可污染邮件链接；内层代理覆盖 HTTPS 为 HTTP | 隔离请求生成过 `https://attacker.example` 来源；现在来源只读配置，代理部署强制 HTTPS，未知 Host 返回 421，跳转固定域名并保留边缘协议 | 代码已修复；实际生产配置待核对 |
| S5 | 中：同一账号使用用户名/邮箱/大小写/空白变体分散账号限流 | 旧限流键为原始输入；现在已存在账号按 ID 计数，未知输入使用规范化摘要，IP 限流及验证码保留 | 代码已修复，待上线 |
| S6 | 中：已验证账号可高速创建委托并触发数据库快照，放大资源消耗 | 创建端点原无频率限制；现在每账号 20 次/10 分钟，在哈希和写库前拦截，返回 429 与 Retry-After | 代码已修复，待上线 |
| S7 | 高（运行时组件）/中（工具链）：旧依赖版本含公开安全公告 | Starlette 上传/文件 Range 等公告、multipart 解析公告及 Pillow 解码公告；更新兼容框架组合及 pip/pytest，并查询全部安装依赖。公告命中不表示每项都可经本站利用，例如图片魔数白名单限制部分 Pillow 格式 | 版本已更新，待部署重建 |
| S8 | 中：游戏存档请求等待异步凭证时切换账号，可把旧快照发给新账号 | 两个存档模块原拦截器直接采用最新 token；现在异步读取后复核身份并固定原 ownerToken，新增真实异步拦截器竞态回归 | 代码已修复，待上线 |

主要位置：`backend/app/main.py`、`email_flow.py`、`media.py`、`config.py`、`schemas.py`、`models.py`、部署代理模板、前端邮箱入口，以及 `composables/lifeSave.js` / `frost/frostSave.js`。

### 依赖依据与版本

- FastAPI **0.141.1** + Starlette **1.6.0**：兼容依赖声明已核验；代表性公告 [CVE-2025-54121](https://osv.dev/vulnerability/GHSA-2c2j-9gv5-cj73)、[CVE-2025-62727](https://osv.dev/vulnerability/GHSA-7f5h-v6xp-fcq8)。
- python-multipart **0.0.32**：代表性公告 [GHSA-wp53-j4wj-2cfg](https://osv.dev/vulnerability/GHSA-wp53-j4wj-2cfg)。
- Pillow **12.3.0**：替换生产 requirements 中的 11.1.0；本机原已安装新版，不能以本机版本代替生产依赖检查。
- pip **26.2.0**、pytest **9.0.3**：分别修复 [CVE-2026-13346](https://osv.dev/vulnerability/GHSA-qwm4-qh6w-59xr)、[CVE-2025-71176](https://osv.dev/vulnerability/GHSA-6w46-j5rx-g56g)。这是安装/测试工具风险，不当作公网 API 可直接利用的证据。
- 可复查命令：`cd backend && .venv/bin/python scripts/audit_dependencies.py`。只发送包名和版本到 PyPI，失败非零退出；前端使用 `npm audit --ignore-scripts`。版本与结果具有时效性。

## 验证与边界

本地验证结果（2026-09-17）：后端 **168 项测试通过**（pytest 另报告 176 个 subtests），前端 **200 项测试通过**，Vite 生产构建通过，`pip check` 无依赖冲突；PyPI 查询 **32 个安装包无未撤回的已知漏洞**，完整版本记录见 [依赖审计结果](security-dependencies.json)。前端锁定依赖 `npm audit` 为 0 项漏洞。生产和开发 Compose 均通过 `config --quiet` 检查。

安全回归包括：密码缺失/错误、四条凭证变更路径的旧链接撤销、并发令牌消费、过期会话快照签发阻断、旧库迁移幂等、真实限流、搬移/删除/数据库提交失败、两区副本、孤儿文件、目录穿越和恶意 Host。前端覆盖缓存权限不可信、换账号时拒绝发送存档以及 409 时不覆盖进度。

测试数据库、上传目录与邮件均隔离。Docker 守护进程当前不可用，**未完成容器启动、Nginx 实际加载与新版本生产冒烟**；Compose 配置可在不连接守护进程的情况下验证。应用测试不能替代镜像系统包扫描和服务器配置检查。

剩余限制：

- 已下载或旧浏览器缓存的图片无法远程删除；新响应使用 `no-store`。签名 URL 仍是短时 bearer 凭证，获知者在有效期内可访问对应私有文件。
- 数据库与磁盘无法共同原子提交；失败时优先避免公开，可能暂时缺图。批量删除部分成功后再失败会留下可重试记录，已删除的文件需从备份恢复。文件系统彻底不可写时撤回会明确失败，管理员需修复并重试。
- 限流仍是单进程内存实现，重启清零、多 worker 各自计数；本次按现有单进程部署实现，不宣称防御分布式攻击。
- 自动迁移针对当前 SQLite；非 SQLite 部署需在维护窗口手动新增 `email_tokens.credential_version INTEGER NOT NULL DEFAULT -1`，作废未使用邮件令牌并清空 `users.pending_email`，再启动新应用。

## 上线清单（由维护者执行）

1. 在根目录私有 `.env` 中确认 `DOMAIN` 与 `SITE_BASE_URL` 对应同一站点；后者必须是完整 HTTPS origin，不能有路径、查询参数或用户密码。真实值不得放入源码、文档和报告。不要使用开发 Compose 暴露服务端口。
2. 预先构建 `docker compose build --pull backend frontend`，保留旧镜像标识。执行 `docker compose config --quiet`，不要把展开后含密钥的配置贴到日志或报告里。
3. 进入维护窗口，停止后端写入。使用权限受限、仓库外的备份目录保存 `.env` 和整个 `backend/data/`（数据库及可能的 WAL 文件、uploads、private_media、backups）；若媒体目录另有挂载，同步备份。保留现有证书持久卷。验证备份可读后再继续。
4. 确认数据目录对容器 UID 10001 可写，执行 `docker compose up -d --build`。前后端须一起更新，已打开的旧页面需刷新以显示换绑密码字段。SQLite 自动添加凭证版本列；**升级前所有未使用邮箱链接失效，待绑定状态清空，需要用户重新申请**；普通已登录会话不因迁移本身强制退出。后续改密/邮箱变更才撤销会话。
5. 后端启动自动对账媒体。若出现媒体分区失败、503、权限或空间错误，保持维护状态，修复后重启；不要改回无鉴权静态托管或删除对账逻辑。检查 `docker compose ps` 与后端日志。
6. 在容器内分别运行 `docker compose exec edge nginx -t`、`docker compose exec frontend nginx -t`，并确认模板更新已被 edge 加载；必要时执行 `docker compose exec edge nginx -s reload`。
7. 冒烟：健康接口正常；HTTP 跳转到配置域名的 HTTPS；错误 Host 返回 421；注册/重发/重置邮件来源为 HTTPS；首次绑定要求当前密码；换绑后旧登录和旧邮件链接失效，新登录成功；上传待审不可公开，审核通过可读，撤回后旧公开地址 404；游戏加载与保存、普通图片与 life 游戏素材正常。用测试账号和专用图片完成，不对真实用户执行攻击复现。
8. 观察 401/422/429/503、邮件失败和“媒体…需对账”日志；确认正常后结束维护窗口。上线后再跑依赖审计及镜像扫描。

### 回滚

优先修复配置或向前修复。确需回滚时，停止写入并保留失败现场，使用保存的旧镜像、匹配的前后端与代理配置；新增列可保留，但旧版本会重新暴露本清单问题，不能作为长期方案。若必须恢复数据，数据库与两区媒体应恢复同一备份时间点，并确认维护窗口后的数据损失可接受。不得只恢复数据库而遗留另一时点的公开媒体；恢复后核查已屏蔽图片，未确认前不要开放公网。

## 二次评估：评分与加固（2026-09-17）

在 S1–S8 修复之上，对当前代码与已部署站点做了一轮独立复核（源码审计 + 线上被动检查；未做主动渗透、未对线上账号执行写操作或压测）。**结论：0 严重 / 0 高危，综合 83/100（B+，良好）**；分项为认证与会话 16/18、授权与访问控制 16/18、输入处理 11/12、上传与媒体 11/14、密钥与配置 10/12、部署加固 10/12、滥用防护 5.5/8、可观测性 3.5/6。

已确认做对（复核通过，勿回退）：手写 HS256 JWT 解码不读 header `alg`（无算法混淆 / 无 `alg:none`）；PBKDF2 310k + 随机盐 + 轮数钳制 + 未知账号计时均衡；`token_version` 强制比对；角色 `Literal` 不含 `is_admin` 且 `extra="forbid"`；邮件令牌 256-bit 只存哈希、条件 UPDATE 保证一次性、fail-closed；`normalize_image()` 魔数白名单 + 像素上限 + 剥元数据 + 重编码；媒体双区 + HMAC 常量时间校验 + 每次读取回查数据库可见性；前端零 `v-html`/`eval`、无 sourcemap、无密钥入包；仅 `edge` 暴露端口 + read_only + cap_drop ALL + 非 root；`client_ip()` 只在受信代理来源下落采信转发头。

线上被动检查（未记录域名等私有信息）：HSTS/CSP/X-Frame-Options/Referrer-Policy/Permissions-Policy 均下发，`Server` 无版本号；未知 Host 返回 421；编码式 `..` 路径返回 400，未编码的 `..` 由 nginx 归一化后落到 SPA（非文件泄露）；`/openapi.json`、`/docs` 返回 SPA 而非接口结构；`/api/site-config` 仅返回备案字段；依赖审计 32 个安装包无已知漏洞（`backend/scripts/audit_dependencies.py`）。

本轮修复（全部有回归用例或配置校验）：

| 编号 | 问题 | 修复 |
|---|---|---|
| M1 | 私有媒体签名 URL 是无绑定 bearer，且签名会随 `$request` 落进访问日志 | `MEDIA_TOKEN_TTL_SECONDS` 默认由 1h 降到 10 分钟；两层 nginx 改用 `log_format yorozuya`（记 `$uri`，去掉查询串） |
| M2 | 上传请求体先进 nginx 内存盘缓冲，且 tmpfs 未限 size（docker 默认给宿主内存一半） | 上传 location 加 `proxy_request_buffering off`（frontend 侧补 `proxy_http_version 1.1`）；所有 tmpfs 显式 `size=` |
| M3 | 证书续期失败被 `--quiet \|\| true` 静默吞掉 | `renew-loop.sh` 写持久化 `renew.log`、失败留 `renew-failed` 标记、加 `--deploy-hook`；新增 `certbot`（余期 <10 天报不健康）与 `edge`（127.0.0.1 走 HTTPS 验整条链路）healthcheck |
| M4 | `validate_storage_isolation()` 只比对数据库文件，未覆盖 `<data>/backups`（纵深防御缺口） | 增加对备份目录的互斥校验；`BACKUP_DIR_NAME` 收口到 `config.py`；新增 3 条用例 |
| L1 | 非安全上下文下 `saveAuth()` 提前 return，旧版明文 `wsw_token` 不会被清除 | 把 `removeLegacy()` 提到持久化判断之前；新增 3 条前端用例 |
| L2 | `CAPTCHA_PROVIDER=turnstile` 而缺 Site/Secret Key 时，接口发内置图形验证码、服务端却按 turnstile 校验（登录死锁） | 新增 `captcha_effective_provider` 属性，两端统一按实际生效的 provider 处理；未知 provider 启动即报错；新增用例 |
| L3 | 文档开关与 `BEHIND_PROXY` 耦合，误设一次即公开完整接口结构 | 独立 `ENABLE_DOCS`（默认 false）且代理部署下仍不暴露，dev compose 显式打开 |
| L4 | `edge` 未声明 `default_server`，依赖 tmpfs 覆盖镜像默认配置 | 两个 `listen` 显式 `default_server` |
| L5 | 首次签发默认走生产 ACME，易消耗速率额度 | `.env.example` 与 `init-letsencrypt.sh` 默认 `CERTBOT_STAGING=1` |
| L6 | `SMTP_ENCRYPTION=none` 会明文传输凭据 | `validate_email_config()` 输出 error 级告警 |
| L7 | 测试未隔离环境变量，宿主机 export 过 `SITE_ICP` 时用例失败 | conftest 显式固定 `SITE_ICP` / `SITE_ICP_URL` |

接受或未处理（不构成本轮阻塞）：签名 URL 本质仍是可转发的 bearer 凭证（只能靠短 TTL 收敛）；限流是进程内实现，依赖单 worker；基础镜像未按 digest 固定、`backend/Dockerfile` 硬编码第三方 pip 源、测试依赖仍在生产 `requirements.txt`；Turnstile 只校验 `success`，未比对 `hostname`/`action`；`GET /api/users/{id}/public` 无目录角色过滤与限流；内容审核未禁止作用于超管媒体；HSTS 刻意不含 `includeSubDomains`；`Server` 头无需额外隐藏（nginx 默认不转发上游 `Server`，线上已确认无版本号）。

验证：后端 **172 项通过**（含本轮新增）、前端 **203 项通过**、`docker compose config --quiet`（prod + dev）通过、`sh -n` 校验续期脚本。**受限于本机 Docker 守护进程不可用，未执行 `nginx -t`、镜像构建与生产冒烟**，部署时按下方清单执行。
