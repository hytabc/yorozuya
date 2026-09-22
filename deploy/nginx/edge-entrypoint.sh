#!/bin/sh
# edge 容器入口：渲染 nginx 配置、启动 nginx，并定期重新渲染 + reload。
#
# 证书不存在时自动退化为「仅 HTTP」的引导配置，因此首次部署不需要先手工造一张占位证书，
# 也不会因为证书丢失/损坏而陷入崩溃重启循环（此时仍可访问 ACME 挑战接口重新签发）。
set -e

: "${DOMAIN:?edge 需要设置 DOMAIN 环境变量（在项目根目录 .env 中配置）}"

command -v envsubst >/dev/null 2>&1 || {
    echo "edge: 镜像中缺少 envsubst，无法渲染配置模板" >&2
    exit 1
}

CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
TEMPLATE_DIR=/etc/nginx/templates
CONF=/etc/nginx/conf.d/default.conf

mkdir -p /var/www/certbot

render() {
    if [ -s "$CERT_DIR/fullchain.pem" ] && [ -s "$CERT_DIR/privkey.pem" ]; then
        echo "edge: 已找到 $DOMAIN 证书，使用 HTTPS 配置"
        envsubst '${DOMAIN}' < "$TEMPLATE_DIR/edge.conf.template" > "$CONF.tmp"
        # 可选游戏入口与主站共用证书，每次续期 reload 时一并更新。
        if [ -f "$TEMPLATE_DIR/ff14.conf.template" ]; then
            envsubst '${DOMAIN}' < "$TEMPLATE_DIR/ff14.conf.template" >> "$CONF.tmp"
        fi
    else
        echo "edge: 未找到 $DOMAIN 证书，临时使用 HTTP 引导配置（仅 ACME 挑战可用）"
        envsubst '${DOMAIN}' < "$TEMPLATE_DIR/edge-bootstrap.conf.template" > "$CONF.tmp"
    fi
    # 原子替换，避免 reload 读到写了一半的文件。
    mv "$CONF.tmp" "$CONF"
}

render

# certbot 续期会更新 /etc/letsencrypt 下的证书文件，但 nginx 不会自动感知；
# 这里周期性地重新渲染并 reload，让新证书生效（不依赖 docker socket）。
( while :; do sleep 6h; render; nginx -s reload 2>/dev/null || true; done ) &

exec nginx -g 'daemon off;'
