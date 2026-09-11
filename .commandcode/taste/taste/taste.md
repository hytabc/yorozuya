# Taste
- Deploys projects via Docker Compose and expects deployment changes to be made directly in the compose setup. Confidence: 0.8
- Wants environment-specific values (server IP, frpc domain, etc.) kept in a `.env` file rather than hardcoded in configs. Confidence: 0.85
- Expects HTTPS via Let's Encrypt with automatic renewal (certbot-style) when exposing a site. Confidence: 0.75
- Wants database data persisted locally and preserved across updates, restorable/openable via an external path (bind mount / dump). Confidence: 0.7
- Asks that operational/deployment procedures be written into the project README. Confidence: 0.8
- Wants prototype/sub-project features integrated into the main project as a new page rendered inside the existing app layout, and explicitly open to all logged-in users rather than gated to specific roles. Confidence: 0.65
- Prefers user/game progress persisted server-side as a per-user record (mirroring existing similar features) over browser localStorage. Confidence: 0.6
- Communicates in Chinese and expects code comments, docs (README/AGENTS), and UI copy written in Chinese. Confidence: 0.7
