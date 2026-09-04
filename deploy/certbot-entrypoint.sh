#!/bin/sh
set -eu

if [ -z "${DOMAIN:-}" ]; then
  echo "[certbot] DOMAIN is not set in .env, skip."
  while :; do sleep 3600; done
fi
if [ -z "${LETSENCRYPT_EMAIL:-}" ]; then
  echo "[certbot] LETSENCRYPT_EMAIL is not set in .env, skip."
  while :; do sleep 3600; done
fi

mkdir -p /var/www/certbot

# Wait until the first certificate is issued (retry every 60s so DNS / frps
# port-80 forwarding / firewall have time to become ready).
while [ ! -f "/etc/letsencrypt/renewal/yorozuya.conf" ]; do
  echo "[certbot] issuing certificate for $DOMAIN ..."
  if certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" \
      --cert-name yorozuya --email "$LETSENCRYPT_EMAIL" \
      --agree-tos --no-eff-email --non-interactive --force-renewal; then
    break
  fi
  echo "[certbot] issuance failed, retry in 60s (check DNS / frps port 80 / firewall) ..."
  sleep 60
done

echo "[certbot] certificate ready, entering auto-renew loop (every 12h) ..."
trap 'exit 0' TERM INT
while :; do
  certbot renew --webroot -w /var/www/certbot --quiet || true
  sleep 12h & wait $!
done