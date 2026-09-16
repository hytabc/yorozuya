#!/bin/sh
# certbot 常驻容器：每 12 小时尝试续期一次。
# Let's Encrypt 证书有效期 90 天，certbot 只在到期前 30 天内才真正续期，因此空跑是正常的。
# 续期后的新证书由 edge 容器定期 reload 加载，本容器无需通知它。
set -e

trap 'exit 0' TERM INT

while :; do
    certbot renew --webroot --webroot-path /var/www/certbot --quiet || true
    # 用 wait 而不是直接 sleep，保证收到 TERM 时能立刻退出。
    sleep 12h &
    wait $!
done
