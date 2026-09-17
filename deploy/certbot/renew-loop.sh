#!/bin/sh
# certbot 常驻容器：每 12 小时尝试续期一次。
# Let's Encrypt 证书有效期 90 天，certbot 只在到期前 30 天内才真正续期，因此空跑是正常的。
# 续期后的新证书由 edge 容器定期 reload 加载，本容器无需通知它。
#
# ⚠️ 续期失败必须留下痕迹：本容器静默失败的话，直到证书过期站点整体掉线才会被发现。
# 因此每次运行的结果都写进 bind mount 的 renew.log（重启后仍可查），
# 失败时额外写 renew-failed 标记文件，成功时清除 —— 巡检/监控只需看这两个文件。
set -u

LOG=/etc/letsencrypt/renew.log
FAILED_FLAG=/etc/letsencrypt/renew-failed

log() {
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$1" >> "$LOG"
}

trap 'exit 0' TERM INT

while :; do
    # 不吞掉退出码：失败要写日志并留标记文件（成功时清除）。
    # --deploy-hook 只在真正续期成功后执行，用于记录续期时间。
    if certbot renew --webroot --webroot-path /var/www/certbot \
        --deploy-hook /opt/renew-hook.sh >/dev/null 2>>"$LOG"; then
        log "renew ok"
        rm -f "$FAILED_FLAG"
    else
        status=$?
        log "renew FAILED (exit $status)"
        printf '%s renew failed with exit %s\n' \
            "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$status" > "$FAILED_FLAG"
    fi
    # 用 wait 而不是直接 sleep，保证收到 TERM 时能立刻退出。
    sleep 12h &
    wait $!
done
