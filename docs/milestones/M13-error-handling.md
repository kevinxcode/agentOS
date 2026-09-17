
==================================================
MILESTONE 13 — ERROR HANDLING
==================================================

Replace weak error handling such as:

catch {}
console.log(error)

with structured handling.

Provide useful errors for:

provider unreachable
invalid API key
model unavailable
Ollama not running
GitHub auth failure
Telegram failure
database failure
pipeline node failure
timeout
rate limit

Frontend errors should be understandable.

Backend logs should include useful technical context without leaking secrets.

