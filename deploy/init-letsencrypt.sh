#!/bin/sh
# 首次申请 Let's Encrypt 证书（一次性脚本；之后的续期由 certbot 容器自动完成）。
#
# 实现说明：证书不存在时 edge 会自动使用「仅 HTTP」的引导配置（只放行 ACME 挑战），
# 因此这里不需要事先伪造占位证书；签发成功后重启 edge 即切换为 HTTPS 配置。
#
# 前置条件：
#   1. 域名 A/AAAA 记录已指向本机公网 IP；
#   2. 云厂商安全组与主机防火墙已放行 80（ACME 挑战）与 443；
#   3. 项目根目录 .env 已配置 DOMAIN 与 LETSENCRYPT_EMAIL。
#
# 用法：
#   ./deploy/init-letsencrypt.sh                    # 正式签发
#   CERTBOT_STAGING=1 ./deploy/init-letsencrypt.sh  # 先用 staging 试跑，避免触发速率限制

set -eu

ROOT_DIR=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd)
cd "$ROOT_DIR"

log() { printf '\033[32m[init-letsencrypt]\033[0m %s\n' "$1"; }
warn() { printf '\033[33m[init-letsencrypt]\033[0m %s\n' "$1"; }
fail() { printf '\033[31m[init-letsencrypt]\033[0m %s\n' "$1" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || fail "未找到 docker 命令"

# 只提取需要的键，不 source 整个 .env（避免密码含空格/特殊字符时被 shell 误当命令执行）。
read_env() {
    [ -f .env ] || return 0
    sed -n "s/^[[:space:]]*$1[[:space:]]*=//p" .env | tail -n 1 | tr -d '\r' \
        | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/"
}

# 显式传入的环境变量优先于 .env。
DOMAIN=${DOMAIN:-$(read_env DOMAIN)}
EMAIL=${LETSENCRYPT_EMAIL:-$(read_env LETSENCRYPT_EMAIL)}
STAGING=${CERTBOT_STAGING:-$(read_env CERTBOT_STAGING)}
# 默认走 staging：首次签发最容易因 DNS/防火墙/路径问题失败，直接打正式环境会消耗
# Let's Encrypt 的速率限制额度（同一域名每周 5 次），试错成本高。确认链路后再改 0 正式签发。
STAGING=${STAGING:-1}

[ -n "$DOMAIN" ] || fail "未设置域名：请在 .env 中配置 DOMAIN，或用 DOMAIN=example.com $0 传入"

case "$DOMAIN" in
    *[!a-zA-Z0-9.-]*) fail "DOMAIN 非法：'$DOMAIN'（应为纯域名，如 example.com）" ;;
esac

if [ "$STAGING" = "1" ]; then
    log "模式：staging（测试证书，浏览器不信任，仅用于验证链路）"
else
    [ -n "$EMAIL" ] || fail "请在 .env 中设置 LETSENCRYPT_EMAIL（证书到期提醒邮箱），或设置 CERTBOT_STAGING=1 仅做测试签发"
    log "模式：production"
fi
log "域名：$DOMAIN"

if command -v getent >/dev/null 2>&1; then
    getent hosts "$DOMAIN" >/dev/null 2>&1 \
        || warn "无法在本机解析 $DOMAIN，请确认 DNS 已生效，否则 ACME 挑战会失败"
fi

CHALLENGE_DIR=deploy/certbot/www/.well-known/acme-challenge
mkdir -p deploy/certbot/conf "$CHALLENGE_DIR"
PROBE=.ready-probe
printf 'ready\n' > "$CHALLENGE_DIR/$PROBE"

log "1/4 启动 edge（同时拉起 frontend 与 backend）；证书缺失时以 HTTP 引导模式运行"
docker compose up -d --build edge

# 就绪探测同时验证了 /var/www/certbot 的挂载与挑战路径可达 —— ACME 失败最常见的原因就在这里。
#
# ⚠️ 必须显式带上 Host 头：edge 配置里 `if ($host != "${DOMAIN}") { return 421; }` 会拒绝
# 一切 Host 不匹配的请求，而直连 127.0.0.1 时的默认 Host 是 127.0.0.1，会被判 421，
# 导致探测永远拿不到 "ready"（真实的 ACME 校验同样以域名为 Host，所以这样探测才与线上一致）。
log "2/4 等待 edge 就绪，并验证 ACME 挑战目录可达"
n=0
until [ "$(docker compose exec -T edge sh -c "wget -qO- --timeout=5 --header=\"Host: $DOMAIN\" http://127.0.0.1/.well-known/acme-challenge/$PROBE" 2>/dev/null)" = "ready" ]; do
    n=$((n + 1))
    [ "$n" -lt 30 ] || {
        rm -f "$CHALLENGE_DIR/$PROBE"
        fail "edge 未就绪或 ACME 挑战目录不可达，请执行 docker compose logs edge 查看"
    }
    sleep 1
done
rm -f "$CHALLENGE_DIR/$PROBE"

log "3/4 申请证书"
set --
if [ -n "$EMAIL" ]; then set -- --email "$EMAIL"; fi
if [ "$STAGING" = "1" ]; then set -- "$@" --staging; fi

docker compose run --rm --entrypoint certbot certbot certonly \
    --webroot --webroot-path /var/www/certbot \
    --domains "$DOMAIN" \
    --agree-tos --no-eff-email --non-interactive \
    "$@"

log "4/4 重启 edge 以加载证书（退出引导模式）"
docker compose restart edge

log "当前证书："
docker compose run --rm --entrypoint certbot certbot certificates

if [ "$STAGING" = "1" ]; then
    log "staging 签发成功。确认无误后用 CERTBOT_STAGING=0 ./deploy/init-letsencrypt.sh 换成正式证书"
else
    log "完成，现在可访问 https://$DOMAIN"
    log "后续续期全自动：certbot 容器每 12h 检查一次，edge 每 6h 重新加载证书"
fi
