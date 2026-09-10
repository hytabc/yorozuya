# Taste

## Deployment & Infrastructure
- Deploys projects via Docker Compose and expects deployment changes to be made directly in the compose setup. Confidence: 0.8
- Wants environment-specific values (server IP, frpc domain, etc.) kept in a `.env` file rather than hardcoded in configs. Confidence: 0.85
- Expects HTTPS via Let's Encrypt with automatic renewal (certbot-style) when exposing a site. Confidence: 0.75
- Wants database data persisted locally and preserved across updates, restorable/openable via an external path (bind mount / dump). Confidence: 0.7

## Documentation
- Asks that operational/deployment procedures be written into the project README. Confidence: 0.8
