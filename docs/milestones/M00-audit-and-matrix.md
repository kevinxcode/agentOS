
==================================================
PHASE 0 — READ PROJECT INSTRUCTIONS FIRST
==================================================

Before modifying any code:

1. Inspect repository root.
2. Read:
   - README.md
   - AGENTS.md
   - CLAUDE.md
   - GEMINI.md
   - CONTRIBUTING.md
   - package.json
   - workspace configuration
   - Docker files
   - compose files
   - environment examples
   - docs/
   - architecture documents
   - TODO documents
   - roadmap files
3. Search for repository-specific agent instructions.
4. Inspect current git status.
5. Inspect recent commits.

Run commands such as:

pwd
git status
git log --oneline -20

and repository-appropriate file discovery commands.

Repository instructions take priority over assumptions in this prompt where they describe current architecture.

==================================================
PHASE 1 — FULL CODEBASE AUDIT
==================================================

Perform a systematic audit before major implementation.

Identify:

- current architecture
- apps/packages
- frontend
- backend
- API layer
- database
- authentication
- AI provider abstraction
- agent runtime
- task engine
- workflow/pipeline engine
- GitHub integration
- Telegram integration
- persistence layer
- streaming infrastructure
- WebSocket/SSE usage
- queue/job infrastructure
- file handling
- logging
- tests
- Docker configuration
- deployment configuration
- documentation

Search specifically for:

TODO
FIXME
HACK
XXX
TEMP
placeholder
mock
not implemented
coming soon
throw new Error
console.log
hardcoded
any
ts-ignore
eslint-disable

Also search for:

- empty handlers
- fake API responses
- buttons with no actions
- unfinished routes
- missing server actions
- unhandled promises
- swallowed exceptions
- temporary database implementations
- fake provider implementations
- incomplete forms
- unreachable UI
- dead navigation
- broken imports
- disabled tests

==================================================
PHASE 2 — BUILD A COMPLETION MATRIX
==================================================

Before large changes, create or update:

docs/PROJECT_COMPLETION.md

It must contain a table similar to:

Area | Current State | Missing | Priority | Verification | Status

Include at minimum:

- authentication
- users
- workspaces
- projects
- agents
- AI providers
- Ollama
- OpenRouter
- OpenAI
- Anthropic
- conversations
- model selector
- agent execution
- tool execution
- streaming
- tasks
- Kanban
- pipelines
- multi-agent orchestration
- pipeline retries
- GitHub
- Telegram
- content generation
- file/context handling
- settings
- secrets
- database
- logging
- error handling
- security
- tests
- Docker
- documentation
- deployment

Status values:

NOT STARTED
PARTIAL
BLOCKED
COMPLETE
VERIFIED

Do not mark anything VERIFIED until tested.

==================================================
PHASE 3 — DEFINE IMPLEMENTATION ORDER
==================================================

Use this dependency-aware priority unless repository architecture requires a justified variation:

P0 — Build health and foundation
P1 — Database and backend integrity
P2 — LLM provider system
P3 — Agent runtime
P4 — Task/Kanban system
P5 — Pipeline orchestration
P6 — GitHub integration
P7 — Telegram integration
P8 — UI/UX completion
P9 — Reliability and security
P10 — Testing and documentation
P11 — Production verification

Do NOT jump randomly between unrelated areas.

Finish coherent milestones.

