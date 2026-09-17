
==================================================
MILESTONE 3 — AI PROVIDER ABSTRACTION
==================================================

Implement a clean provider abstraction.

Supported provider targets:

1. Ollama
2. OpenRouter
3. OpenAI
4. Anthropic / Claude

Providers must not leak implementation details throughout the application.

Use a common interface approximately equivalent to:

LLMProvider
- listModels()
- generate()
- stream()
- toolCall()
- healthCheck()

Use the existing architecture if already present.

Configuration must support:

provider
model
base URL
API key reference
temperature
max tokens
context configuration where supported

API secrets must remain server-side.

Never expose provider API keys in browser bundles.

==================================================
OLLAMA SUPPORT
==================================================

Ollama is an important target.

Default endpoint:

http://localhost:11434

Support OpenAI-compatible endpoint where appropriate:

http://localhost:11434/v1

The system should be capable of working with models such as:

qwen3-coder-next:latest
qwen3-coder:30b
qwen3.8:27b
qwen3.6:27b
qwen3-vl:8b

Do NOT hardcode these as the only available models.

Prefer model discovery from Ollama.

Support:

- connection testing
- model discovery
- provider health
- readable error messages
- configurable endpoint

