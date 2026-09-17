
==================================================
MILESTONE 12 — STREAMING
==================================================

AI responses should stream where supported.

Use the repository's chosen approach:

SSE
WebSocket
streaming server responses

Handle:

disconnect
abort
timeout
provider errors
partial output
reconnect where appropriate

The UI should not freeze during long inference.

This is particularly important for large local Ollama models.

