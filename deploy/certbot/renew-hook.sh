#!/bin/sh
# certbot --deploy-hook：仅在证书真正续期成功后执行。
# 只记录一条审计日志（证书目录与时间）；新证书由 edge 容器每 6h 重新渲染并 reload，
# 本容器不接触 nginx，因此不需要 docker socket。
set -u

LOG=/etc/letsencrypt/renew.log
printf '%s renewed %s\n' \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "${RENEWED_LINEAGE:-unknown}" >> "$LOG"
