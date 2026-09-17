#!/bin/sh
# edge 容器健康检查：配置可加载 + 证书存在时验证 HTTPS 整条链路。
# 链路 = TLS 终止 → frontend → backend /api/health，因此它同时覆盖「证书已被加载」
# 和「反代仍能到达后端」两件事（edge 只 reload 不重启，配置坏了也能靠它发现）。
set -u

: "${DOMAIN:?healthcheck 需要 DOMAIN 环境变量}"

nginx -t >/dev/null 2>&1 || { echo "nginx 配置校验失败" >&2; exit 1; }

# 证书还没签发时 edge 处于 HTTP 引导模式（只服务 ACME 挑战），属于正常状态。
[ -s "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ] || exit 0

# 证书 CN 是 ${DOMAIN}，直连 127.0.0.1 需要显式 Host 头并跳过证书域名校验。
wget -q -O /dev/null --timeout=5 --no-check-certificate \
    --header="Host: ${DOMAIN}" "https://127.0.0.1/api/health" \
    || { echo "HTTPS 健康检查失败（TLS 或后端反代不可用）" >&2; exit 1; }

echo "edge 正常"
