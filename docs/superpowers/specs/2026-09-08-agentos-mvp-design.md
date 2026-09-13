# AgentOS MVP Design

Date: 2026-09-08  
Status: Approved design

## 1. Product Goal

AgentOS is a personal, local-first hybrid mission-control application for running AI-assisted software development tasks. The MVP focuses on a single administrator, a universal task model, a Kanban workflow, multiple model providers, isolated coding execution, GitHub pull-request delivery, and explicit human approval for consequential actions.

The deployment target is an Ubuntu server that runs continuously. The model layer is modular: Ollama may run on the same server when an NVIDIA GPU is available, or on a private remote inference node such as the user's RTX 5090 workstation. OpenRouter, Anthropic Claude, and OpenAI are supported cloud providers.

## 2. MVP Scope

### Included

- Single-user administration with local password authentication and TOTP 2FA.
- Mission Control showing active, queued, failed, paused, and completed work.
- Universal tasks and a Kanban board.
- Configurable agent registry and provider/model selection.
- Coding pipeline: Plan, Code, Test, Review, Approval, Commit, Push, and Pull Request.
- OpenHands as the first coding runtime behind a replaceable adapter interface.
- Per-run Docker sandbox and repository workspace.
- GitHub App integration restricted to selected repositories.
- LiteLLM gateway for Ollama, OpenRouter, Anthropic Claude, and OpenAI.
- PostgreSQL with pgvector for durable application data and memory.
- Redis-backed job queue and worker execution.
- MinIO artifact storage.
- Real-time progress and logs.
- Cost, token, duration, iteration, and resource limits.
- Cloudflare Tunnel for HTTPS dashboard access.
- Docker Compose deployment on Ubuntu.
- Audit logging and encrypted secret storage.

### Deferred

- Content Studio and Image Studio.
- Telegram remote control and approvals.
- n8n integration.
- Visual pipeline builder.
- Scheduled and recurring agent loops.
- Browser automation.
- Multi-user and multi-tenant operation.
- Automatic merge and deployment.
- Native mobile applications.
- Public marketplace and billing.

The task, run, agent, artifact, approval, and provider boundaries must allow deferred capabilities to be added without replacing the control plane.

## 3. System Architecture

### Frontend

Next.js with TypeScript provides login, Mission Control, Kanban, task creation and detail, live run visibility, approval screens, GitHub configuration, and model/provider settings. Tailwind CSS and shadcn/ui provide the component system. Drag-and-drop behavior uses dnd-kit. Code and diff presentation use Monaco Editor.

### Control Plane

FastAPI owns authentication, authorization, task APIs, agent configuration, provider policy, approvals, GitHub App integration, audit events, and real-time event delivery. SSE is the primary transport for streamed task status and logs; ordinary mutations use HTTP APIs.

### Agent Runtime

LangGraph owns durable pipeline state, checkpoints, transitions, bounded retries, pause/resume, and human-in-the-loop gates. It does not directly embed vendor-specific coding behavior.

A `CodingRuntimeAdapter` boundary exposes operations for starting, observing, cancelling, and collecting results from a coding engine. OpenHands is the first implementation. Additional adapters, including Codex or Claude Code, can be added later without changing task or pipeline contracts.

### Execution Plane

Workers consume queued jobs from Redis. Each coding run receives an isolated Docker container, a dedicated repository workspace, explicit CPU/RAM/disk/time/process limits, and a non-privileged runtime. A stop request terminates the actual sandbox process and records the terminal state.

### Model Gateway

LiteLLM presents one model interface and routes requests to Ollama, OpenRouter, Anthropic Claude, or OpenAI. Provider and model configuration supports enable/disable, health checks, usage tracking, local/cloud classification, primary/fallback order, and per-agent selection.

Model routing policies are:

- `local_only`: no request may leave the private Ollama endpoint.
- `hybrid`: local is preferred; approved cloud fallbacks may be used within budget.
- `cloud_allowed`: configured cloud or local models may be selected.

The system never silently switches to a more expensive model after a budget or provider-policy failure. It pauses and requests user input.

### Persistence

- PostgreSQL stores users, sessions, TOTP metadata, agents, provider metadata, repositories, tasks, dependencies, runs, steps, checkpoints, approvals, usage, budgets, audit events, and artifact metadata.
- pgvector supports semantic task, project, and agent memory.
- MinIO stores patches, generated files, exported logs, and other large artifacts.
- Redis stores transient queue, lock, heartbeat, and streaming state only and is not a source of record.

### External Access

Cloudflare Tunnel exposes only the HTTPS dashboard/API entry point. PostgreSQL, Redis, MinIO, LiteLLM, workers, and sandboxes do not publish public ports. Ollama is addressed through configuration and can resolve either to a same-server service or a private remote inference node.

## 4. Core Domain Model

### Task

A task represents user intent and is the universal unit shown on the Kanban board. It contains instructions, success criteria, repository/project, selected agent/model policy, priority, limits, current status, dependencies, artifacts, usage, and timestamps.

### Run and Step

A task may have multiple runs. A run is one execution attempt and contains ordered or conditional steps, checkpoints, runtime identifiers, resource consumption, logs, errors, and results. Steps use stable idempotency keys.

### Agent

An agent defines a role, system instructions, permitted tools, repository and file access, model policy, runtime adapter, limits, approval rules, and a version. A run records the exact agent version used.

### Approval

An approval records the requested action, risk context, proposed diff or artifact, test result, cost, requester, decision, decision timestamp, and audit linkage. Approval is action-specific and cannot authorize unrelated subsequent actions.

### Artifact

An artifact is an immutable versioned output reference stored in MinIO or Git. Examples include patches, reports, logs, and test results. Metadata in PostgreSQL links it to tasks, runs, and steps.

## 5. Coding Task Flow

1. The administrator creates a task and selects a repository, instructions, model policy, and budget.
2. The control plane validates the GitHub App installation and repository allowlist.
3. A worker creates a dedicated workspace, branch, and sandbox.
4. The Planner produces an explicit plan and success criteria.
5. The OpenHands adapter executes the coding step and records commands, changed files, model use, and progress.
6. The worker executes repository-configured lint, test, and build commands.
7. A Reviewer Agent evaluates the diff, test evidence, security impact, and request alignment.
8. On a correctable failure, the pipeline returns to coding, up to three total code-review iterations.
9. On success, the task enters `Approval` and presents the plan, diff, test/build results, cost, and identified risk.
10. After explicit approval, the system creates a commit, pushes the task branch, and opens a pull request.
11. The user merges through GitHub. AgentOS does not merge or deploy in the MVP.

## 6. State Model

Primary Kanban states are:

`Inbox -> Planned -> Running -> Review -> Approval -> Done`

Alternative states are:

- `Paused`: resumable by the user.
- `Needs Input`: blocked on a user decision or information.
- `Failed`: terminated unsuccessfully with retained evidence.
- `Cancelled`: stopped intentionally and not automatically resumed.

State transitions are validated by the backend. UI drag-and-drop requests a transition; it does not directly overwrite state. A restart reconstructs active execution from PostgreSQL/LangGraph checkpoints and worker heartbeats.

## 7. GitHub Integration

AgentOS uses a GitHub App because it provides repository-scoped installation permissions and short-lived tokens.

MVP permissions must be limited to the operations required for repository metadata, content, branches, commits, status checks, issues when needed for task context, pull requests, and webhook processing. The installation is further constrained by an AgentOS repository allowlist.

Rules:

- Never push directly to the default branch.
- Create a unique task branch and isolated workspace.
- Require approval before commit, push, and PR creation. The approval screen groups these three known delivery actions into one explicit request for the reviewed commit candidate.
- Do not merge or deploy.
- Verify GitHub webhook signatures and deduplicate webhook deliveries.
- Mint installation tokens only when required and never persist them as durable plaintext secrets.

## 8. Security Design

### Authentication and Sessions

- One local administrator account in the MVP.
- Password hashing uses Argon2id.
- TOTP 2FA is mandatory after enrollment.
- Session cookies are `HttpOnly`, `Secure`, and `SameSite` protected.
- Login and TOTP verification are rate-limited and audited.
- Recovery codes are one-time, hashed at rest, and shown only during enrollment.

### Secret Handling

OpenRouter, Anthropic, OpenAI, GitHub App, TOTP, and other durable credentials are envelope-encrypted before database storage. The master encryption key is supplied through a Docker Secret or protected server environment and is never committed to Git.

Secrets are redacted from prompts, application logs, command output, traces, and artifacts. The UI displays only masked identifiers. Temporary GitHub installation credentials are scoped, short-lived, injected only for the required operation, and removed afterward.

### Sandbox Policy

- Non-privileged containers with no host Docker socket.
- Read/write access only to the task workspace and approved artifact mount.
- Explicit CPU, RAM, PID, duration, and disk limits.
- Network denied by default; a task may request restricted egress for dependencies.
- Sensitive paths, `.env` files, private keys, credential stores, production configuration, and unrelated host files are denied unless a separately audited approval permits access.
- Destructive host operations are impossible from the sandbox by construction.

### Audit

Append-only application audit records capture actor, time, task/run, action, target, policy result, approval, and outcome. Audit records never store secret values. Administrative retention and export are supported; ordinary task deletion does not remove audit history.

## 9. Cost and Resource Controls

AgentOS enforces per-task, daily, and monthly limits for tokens and estimated provider cost. It also limits agent iterations, execution duration, sandbox CPU/RAM/disk, and concurrent runs.

Before a run starts, the UI shows the selected routing policy and configured limits. When a limit is reached, execution pauses or fails safely and explains the required user action. Usage is attributable by provider, model, agent, repository/project, task, run, and step.

## 10. Failure Handling and Recovery

- Steps use idempotency keys so retries do not create duplicate branches, commits, or pull requests.
- Transient provider, GitHub, queue, worker, and sandbox startup failures use bounded exponential backoff.
- Authentication failures, exhausted budgets, merge conflicts, policy violations, and repeated test failures are not blindly retried; they enter `Needs Input` or `Failed`.
- Workers and sandboxes emit heartbeats. Stale execution is reconciled against durable state.
- Partial artifacts, diffs, logs, and test results are retained after failure.
- Each error includes a user-readable explanation, technical evidence, last successful step, and available recovery actions.
- Cancellation is propagated to the real running process and records whether termination succeeded.

## 11. Testing Strategy

### Unit Tests

Cover state transitions, policy decisions, budget calculations, model routing, encryption boundaries, secret redaction, permission checks, and idempotency.

### Integration Tests

Exercise PostgreSQL, Redis, MinIO, workers, a mocked LiteLLM/provider layer, and mocked GitHub App APIs. Verify persistence, recovery, and deduplication.

### Pipeline Tests

Use a fixture repository to execute plan, modification, lint/test/build, review, approval, and simulated pull-request delivery. Include failed tests, iteration exhaustion, cancellation, and restart recovery.

### Security Tests

Test session and TOTP behavior, webhook signatures, forbidden path access, credential masking, network policy, resource limits, and sandbox isolation controls.

### Frontend Tests

Cover login/enrollment, Mission Control, Kanban transitions, task creation/detail, live status, approvals, GitHub setup, and provider configuration.

### CI and Deployment Tests

GitHub Actions runs formatting, lint, type checking, unit/integration tests, production builds, dependency scanning, and container scanning. An Ubuntu Docker Compose smoke test requires all internal services to become healthy without publishing private service ports.

## 12. MVP Acceptance Criteria

The MVP is complete when all of the following are demonstrated:

1. An administrator can enroll, sign in with password plus TOTP, and manage recovery codes.
2. A GitHub App installation can authorize at least one allowlisted repository.
3. A coding task can run end-to-end in an isolated sandbox using the OpenHands adapter.
4. Ollama, OpenRouter, Anthropic Claude, and OpenAI can be configured through LiteLLM, individually enabled or disabled, and governed by routing and budget policy.
5. The user can see real-time progress, logs, artifacts, the proposed diff, tests, build status, cost, and review result.
6. No commit, push, or pull request occurs before explicit approval of the reviewed delivery candidate.
7. The user can pause, resume, stop, and retry supported stages, and stop terminates actual execution.
8. A run can recover consistently after a worker or server restart without duplicating external side effects.
9. Failed work retains partial artifacts and actionable diagnostics.
10. Automated tests and the Ubuntu Docker Compose smoke test pass, and no private internal service is publicly exposed.

## 13. Delivery Boundaries

The MVP will be delivered incrementally through small reviewed commits. Infrastructure, domain models, authentication, providers, task execution, GitHub delivery, and user experience are separate implementation milestones. No milestone may bypass the security and approval rules defined in this specification.
