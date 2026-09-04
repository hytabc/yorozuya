#!/bin/sh
set -e

LE_LIVE=/etc/letsencrypt/live/yorozuya

# If no real certificate exists yet, generate a temporary self-signed one so
# nginx can boot. The certbot container will replace it with a real
# Let's Encrypt certificate later.
if [ ! -f "$LE_LIVE/fullchain.pem" ] || [ ! -f "$LE_LIVE/privkey.pem" ]; then
  echo "[entrypoint] generate temporary self-signed certificate ..."
  mkdir -p "$LE_LIVE"
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout "$LE_LIVE/privkey.pem" \
    -out "$LE_LIVE/fullchain.pem" \
    -subj "/CN=yorozuya-temp" >/dev/null 2>&1
fi

# Reload nginx within ~30s whenever the certificate file changes, so newly
# issued / renewed Let's Encrypt certificates take effect automatically.
( while :; do
    cur=$(md5sum "$LE_LIVE/fullchain.pem" 2>/dev/null | awk '{print $1}')
    if [ -n "$cur" ] && [ "$cur" != "$prev" ]; then
      if [ -n "$prev" ]; then nginx -s reload 2>/dev/null || true; fi
      prev="$cur"
    fi
    sleep 30
  done ) &

exec /docker-entrypoint.sh "$@"