# Taste
- Requires authorization/permission checks to be enforced server-side; treats client-side role checks (localStorage user, locally-decoded JWT, JS-visible permission flags) as a vulnerability to be removed, not trusted. Confidence: 0.92
- Wants security risks hunted down and fixed in a comprehensive full sweep across the whole project rather than one issue at a time. Confidence: 0.65
- Objects to storing sensitive data (auth tokens, user info) in plaintext in browser localStorage; wants client-side credentials encrypted, and prefers an insecure-fallback-free degrade (memory-only) over ever writing plaintext. Confidence: 0.85
- Wants human verification (captcha) on login AND registration, and wants the verification mechanism designed as a pluggable/config-switchable provider so third-party captcha services can be dropped in later. Confidence: 0.8
- Wants persistent-login ("自动登录"/remember-me) convenience, but only with a bounded hard expiry on the token (e.g., must not be usable after 7 days) — convenience must not mean indefinite sessions. Confidence: 0.6
