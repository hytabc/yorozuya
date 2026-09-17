#!/bin/sh
# certbot 容器健康检查：剩余有效期不足 10 天视为不健康。
#
# 续期长期失败是静默的（certbot 只在到期前 30 天内才真正续期），
# 这个检查让它在 docker ps 上直接可见，而不必等到证书过期、站点掉线。
set -u

days=$(certbot certificates 2>/dev/null | sed -n 's/.*VALID: \([0-9]*\) days.*/\1/p' | head -n 1)
if [ -z "$days" ]; then
    echo "无法读取证书剩余有效期（证书缺失或 certbot 状态异常）" >&2
    exit 1
fi
if [ "$days" -lt 10 ]; then
    echo "证书仅剩 $days 天，续期可能已失败，请检查 /etc/letsencrypt/renew.log" >&2
    exit 1
fi
echo "证书剩余 $days 天"
