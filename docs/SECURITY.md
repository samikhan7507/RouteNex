# Security checklist
- PBKDF2-SHA256 password hashing with unique salts and constant-time comparison.
- Signed, expiring bearer tokens; secret comes from environment.
- Endpoint-level RBAC and ownership checks.
- OTP values are hashed, single-use and expire in five minutes. Demo phone `+91 8882846897` uses documented test code `123456`; production OTP is never returned by the API.
- Google endpoint deliberately requires provider setup outside demo mode; production must verify Google ID-token audience and issuer server-side.
- Typed validation, parameterized SQL, foreign keys, transaction boundaries and audit logs.
- For public deployment: PostgreSQL, HTTPS-only cookies or short-lived access/refresh rotation, rate limiting, CSRF controls if cookies are used, KMS secrets, encrypted PII, malware scanning for documents, provider webhooks, backups and SIEM export.