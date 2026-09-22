#!/bin/sh
# 同机已部署项目的一键接入；默认目录为 yorozuya 与 FF14Push 并列。
set -eu

ROOT_DIR=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd)
GAME_DIR=${FF14_DIR:-"$ROOT_DIR/../FF14Push"}
log() { printf '[FF14 HTTPS] %s\n' "$*"; }
fail() { log "错误：$*" >&2; exit 1; }

for cmd in docker python3 curl; do
    command -v "$cmd" >/dev/null 2>&1 || fail "缺少 $cmd，请先安装。"
done
[ -d "$GAME_DIR" ] || fail "未找到游戏目录 $GAME_DIR，可通过 FF14_DIR 指定。"
GAME_DIR=$(CDPATH= cd -P "$GAME_DIR" && pwd)
[ "$GAME_DIR" != "$ROOT_DIR" ] || fail "游戏目录不能与万事屋目录相同。"
for dir in "$ROOT_DIR" "$GAME_DIR"; do
    [ -f "$dir/.env" ] || fail "缺少 $dir/.env；请保留已部署项目的原配置。"
    [ -f "$dir/docker-compose.yml" ] || fail "缺少 $dir/docker-compose.yml。"
    python3 - "$dir/.env" <<'PY' || fail "$dir/.env 设置了 COMPOSE_FILE，请先移除此设置，确保自动覆盖配置生效。"
import re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text()
sys.exit(1 if re.search(r"^\s*(?:export\s+)?COMPOSE_FILE\s*=", text, re.M) else 0)
PY
done

# 本脚本显式使用两份配置；不默默忽略环境中的第三份部署配置。
[ -z "${COMPOSE_FILE:-}" ] || fail "请先取消当前 shell 的 COMPOSE_FILE，再运行脚本。"
[ -z "${COMPOSE_PROJECT_NAME:-}" ] || fail "请将各项目的 COMPOSE_PROJECT_NAME 放在各自 .env，而非共享 shell 环境。"
docker info >/dev/null 2>&1 || fail "无法连接 Docker，请检查 Docker 服务和当前账号权限。"
docker compose version --short | python3 -c '
import re, sys
m = re.search(r"(\d+)\.(\d+)\.(\d+)", sys.stdin.read())
sys.exit(0 if m and tuple(map(int, m.groups())) >= (2, 24, 4) else 1)
' || fail "需要 Docker Compose >= 2.24.4。"

main_compose() (
    cd "$ROOT_DIR"
    docker compose --env-file "$ROOT_DIR/.env" -f "$ROOT_DIR/docker-compose.yml" \
        -f "$ROOT_DIR/deploy/docker-compose.ff14.yml" "$@"
)
game_compose() (
    cd "$GAME_DIR"
    docker compose --env-file "$GAME_DIR/.env" -f "$GAME_DIR/docker-compose.yml" \
        -f "$ROOT_DIR/deploy/docker-compose.ff14-game.yml" "$@"
)

# 仅允许本脚本管理的自动覆盖文件；不修改已有的用户定制。
check_override() {
    dir=$1
    source_file=$2
    for name in compose.yaml compose.yml docker-compose.yaml compose.override.yaml compose.override.yml docker-compose.override.yaml; do
        [ ! -e "$dir/$name" ] || fail "$dir/$name 已存在，请先人工合并部署配置。"
    done
    if [ -e "$dir/docker-compose.override.yml" ]; then
        cmp -s "$source_file" "$dir/docker-compose.override.yml" \
            || fail "$dir/docker-compose.override.yml 已存在且内容不同，未覆盖。"
    fi
    [ -w "$dir" ] || fail "目录不可写：$dir。"
}
check_override "$ROOT_DIR" "$ROOT_DIR/deploy/docker-compose.ff14.yml"
check_override "$GAME_DIR" "$ROOT_DIR/deploy/docker-compose.ff14-game.yml"

log "1/5 校验两套部署配置与现有服务"
main_compose config --quiet
game_compose config --quiet
# 只提取公开域名，不打印 config 中的密码；不 source .env。
DOMAIN=$(main_compose config --format json | python3 -c '
import json, re, sys
domain = json.load(sys.stdin)["services"]["edge"]["environment"]["DOMAIN"]
if not re.fullmatch(r"[a-zA-Z0-9.-]+", domain):
    sys.exit("DOMAIN 必须是纯域名")
print(domain)
')
EDGE_ID=$(main_compose ps -q edge)
GAME_ID=$(game_compose ps -q frontend)
[ -n "$EDGE_ID" ] && [ -n "$GAME_ID" ] \
    || fail "未找到运行中的 edge 或游戏 frontend，请确认原 Compose 项目名及目录正确。"
for container_id in $(docker ps -q --no-trunc --filter publish=19999); do
    [ "$container_id" = "$EDGE_ID" ] || [ "$container_id" = "$GAME_ID" ] \
        || fail "19999 已被其他容器占用：$container_id。"
done
# 此处仅检查 TLS：旧版 DNS 冲突可能让主站接口已不可用，不能阻止修复。
# 不使用 --fail，允许当前错误上游返回 404/502；证书校验仍然开启。
curl --noproxy '*' --silent --show-error --connect-timeout 5 --max-time 15 \
    --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/api/health" >/dev/null \
    || fail "现有入口 TLS/证书检查失败，尚未修改部署。"

log "2/5 创建共享网络并保存自动加载配置"
docker network inspect yorozuya-ff14-https >/dev/null 2>&1 \
    || docker network create yorozuya-ff14-https >/dev/null
cp "$ROOT_DIR/deploy/docker-compose.ff14.yml" "$ROOT_DIR/docker-compose.override.yml"
cp "$ROOT_DIR/deploy/docker-compose.ff14-game.yml" "$GAME_DIR/docker-compose.override.yml"

changed=1
on_exit() {
    result=$?
    if [ "$result" -ne 0 ] && [ "$changed" = 1 ]; then
        log "切换未完成，已保留覆盖配置；修复上方错误后重跑本脚本即可。" >&2
        log "请勿删除数据库。回滚说明：$ROOT_DIR/deploy/ff14-https.md" >&2
    fi
}
trap on_exit EXIT
log "3/5 应用主站专用网络别名，游戏前端加入内网"
# 必须先更新主站 frontend 的网络别名，再启动引用新别名的 edge。
main_compose up -d --no-deps frontend
game_compose up -d --no-deps frontend
log "4/5 edge 接管 19999 HTTPS（主站连接会短暂中断）"
main_compose up -d --no-deps --force-recreate edge

check_endpoint() {
    port=$1
    endpoint=$2
    kind=$3
    body=$(curl --noproxy '*' --fail --silent --show-error --connect-timeout 2 --max-time 3 \
        --resolve "$DOMAIN:$port:127.0.0.1" "https://$DOMAIN:$port$endpoint") || {
        log "$port$endpoint 请求失败" >&2
        return 1
    }
    # SPA 回退页也会返回 200，必须解析响应内容，不能只看状态码。
    printf '%s' "$body" | python3 -c '
import json, sys
kind = sys.argv[1]
raw = sys.stdin.read()
try:
    if kind == "game-frontend":
        valid = raw.strip() == "ok"
    else:
        data = json.loads(raw)
        valid = (data == {"status": "ok"} if kind == "main" else
                 data == {"status": "ok", "service": "eorzea-idle-backend"})
except (ValueError, TypeError):
    valid = False
sys.exit(0 if valid else 1)
' "$kind" || {
        log "${port}${endpoint} 返回内容不属于预期服务 ${kind}（可能代理串站）" >&2
        return 1
    }
}
check_redirect() {
    port=$1
    expected=$2
    actual=$(curl --noproxy '*' --silent --show-error --connect-timeout 2 --max-time 3 \
        --resolve "$DOMAIN:$port:127.0.0.1" -o /dev/null -w '%{http_code} %{redirect_url}' \
        "http://$DOMAIN:$port/") || return 1
    [ "$actual" = "301 $expected" ] || {
        log "$port HTTP 跳转异常：$actual" >&2
        return 1
    }
}

log "5/5 检查主站和游戏的服务身份、HTTPS 与 HTTP 跳转（最多约 2 分钟）"
ready=0
for attempt in 1 2 3 4 5 6; do
    if check_endpoint 443 /api/health main \
        && check_endpoint 19999 /healthz game-frontend \
        && check_endpoint 19999 /health game-backend \
        && check_redirect 80 "https://$DOMAIN/" \
        && check_redirect 19999 "https://$DOMAIN:19999/"; then
        ready=1
        break
    fi
    sleep 5
done
[ "$ready" = 1 ] || fail "HTTPS 健康检查失败，请检查 edge 与游戏日志后重试。"
main_compose exec -T edge nginx -t
changed=0
log "完成：游戏 https://$DOMAIN:19999 ，主站 https://$DOMAIN"
log "已保存自动覆盖配置，今后在两个项目中普通 docker compose up 更新也会保留 HTTPS。"
log "请确保云安全组和主机防火墙允许 TCP 19999；本机检查无法验证公网规则。"
