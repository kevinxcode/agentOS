
==================================================
MILESTONE 14 — SECURITY
==================================================

Audit security.

At minimum inspect:

authentication
authorization
workspace isolation
project ownership
API secret storage
input validation
server-only environment variables
GitHub tokens
Telegram bot tokens
provider API keys
dangerous command execution
path traversal
file upload validation
SSRF risks
webhook verification
rate limiting where appropriate
XSS
CSRF depending on architecture

Never log secrets.

Never send secrets to the client.

