# FF14Push 的 19999 端口启用 HTTPS

适用于万事屋与 FF14Push 部署在同一台服务器、使用同一域名的情况。
访问地址为 `https://example.com:19999`（替换为万事屋根目录 `.env` 的 `DOMAIN`）。
TLS 证书验证域名而非端口，直接使用万事屋已有正式证书，无需重新签发或复制私钥。
edge 的定时 reload 会同时加载主站和游戏的新证书。游戏联机 WebSocket 自动使用 WSS。

## 修复旧版主站显示游戏的问题

旧版 edge 同时连接主站与游戏网络，两个 Compose 项目均自动注册 `frontend` DNS 名，
导致 443 的 `proxy_pass http://frontend:80` 可能落到游戏容器。
当前版本将主站上游固定为仅在主站网络注册的 `yorozuya-web`，游戏仍使用 `ff14-frontend`。
80 只跳转到主站 443，19999 独立服务游戏。

服务器已运行过旧版脚本时，**同步更新根目录 `docker-compose.yml` 以及整个 `deploy/` 目录**，
不能只替换脚本。保留服务器现有 `.env` 与两个 `docker-compose.override.yml`，然后重跑：

```sh
sh /home/admin/web/yorozuya/deploy/enable-ff14-https.sh
```

脚本兼容旧版生成的覆盖文件，会先更新主站前端网络别名，再重建 edge。
主站当前返回游戏页面或 HTTP 404/502 不会阻止修复，只要入口 TLS 证书仍有效即可。
修复后检查服务响应内容与两个 HTTP 跳转目标；游戏首页返回 200 不再会被当成主站健康。

## 已部署服务器切换

要求 Docker Compose >= 2.24.4（使用 `!reset` 清除旧端口映射），主站 HTTPS 证书有效。
服务器目录为 `/home/admin/web/yorozuya` 和 `/home/admin/web/FF14Push`。
将本次修改同步到服务器的万事屋目录，保留两项目的 `.env`、数据库和证书，然后只需执行：

```sh
sh /home/admin/web/yorozuya/deploy/enable-ff14-https.sh
```

脚本从自身位置找到万事屋目录，默认寻找同级 `FF14Push`，通过 Docker Compose 读取现有
`.env` 中的 `DOMAIN`，不需要再次填写域名。要求服务器有 `docker`、`python3` 和 `curl`。
如游戏在其他目录，可使用 `FF14_DIR=/其他路径/FF14Push sh deploy/enable-ff14-https.sh`。

脚本会先校验 Compose 版本、两套配置、运行中的容器、19999 容器端口占用，以及入口正式证书。
检查通过后创建共享网络，在两个项目根目录各保存 `docker-compose.override.yml`，
更新主站前端网络别名、重建游戏前端以释放旧 HTTP 端口，再重建 edge 接管 19999，
最后校验主站、游戏前端及游戏后端的 HTTPS 响应内容，以及 80/19999 的 HTTP 跳转目标。
不构建镜像，不重建游戏数据库或后端。可重复运行；若存在不同内容的覆盖文件则停止，避免覆盖部署定制。
需保留原 Compose 项目名；若原来通过 `-p` 指定项目名，应在各自 `.env` 中设置相应 `COMPOSE_PROJECT_NAME`。

切换期间游戏会短暂中断，edge 重建也会使主站连接短暂中断。
脚本验证的是本机通过域名和 SNI 的 TLS 链路，无法自动修改云安全组或验证公网可达性。

云安全组和宿主机防火墙放行 **TCP 19999**，80/443 保持原状用于主站和证书续期。
DNS 仍指向同一服务器。若使用 Cloudflare 橙云代理，它不支持 19999 HTTPS 端口，
需使用 DNS only 的域名且证书覆盖该域名；本配置要求与主站 `DOMAIN` 一致。

## 验证

替换下面的示例域名，在服务器外执行（不要添加 `-k`，以便检查证书信任）：

```sh
curl --fail --show-error https://example.com:19999/healthz
curl --fail --show-error https://example.com:19999/health
curl -I http://example.com:19999/
curl --fail --show-error https://example.com/api/health
```

预期游戏健康检查成功、HTTP 请求返回 301 到相同端口的 HTTPS、主站仍正常。
浏览器登录游戏并进入联机页面，开发者工具中 `/api/v1/coop/ws` 应以 `wss://` 连接并返回 101。
如果游戏返回 502，检查游戏前端是否运行且两个入口容器均已加入 `yorozuya-ff14-https` 网络。
证书不存在时仅主站 80 端口提供 ACME 引导，19999 不提供明文游戏。

## 后续更新与回滚

一键脚本生成的 `docker-compose.override.yml` 会被普通 `docker compose up -d --build` 自动加载，
以后在两个项目原目录更新即可，主站重签证书脚本也会自动加载。请保留这两个服务器本地文件。
万事屋已将生成文件加入 `.gitignore`；游戏项目也应将其视为本地部署配置，不提交到仓库。
若使用显式 `-f` 参数，Compose 不再自动加载覆盖文件，必须同时指定对应覆盖文件。
不要在 `.env` 中设置 `COMPOSE_FILE`，否则会绕过默认自动加载规则。
例行证书续期由现有 certbot 和 edge 完成，无需额外操作。

切换失败时脚本返回非零并保留配置，修复提示的问题后重跑即可。
如需回滚，先移走两个脚本生成的覆盖文件，再按以下顺序恢复原部署：

```sh
cd /home/admin/web/yorozuya
mv docker-compose.override.yml docker-compose.override.yml.disabled
docker compose up -d --no-deps --force-recreate edge
cd /home/admin/web/FF14Push
mv docker-compose.override.yml docker-compose.override.yml.disabled
docker compose up -d --no-deps frontend
```

回滚恢复的是 HTTP；浏览器已有主站 HSTS 时仍会强制使用 HTTPS，不能视作长期可用方案。
不要执行 `down -v`，也不要删除任何数据库或证书目录。
