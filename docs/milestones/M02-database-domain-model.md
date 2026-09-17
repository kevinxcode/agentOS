
==================================================
MILESTONE 2 — DATABASE AND DOMAIN MODEL
==================================================

Audit the data model.

The system should support coherent entities for concepts such as:

User
Workspace
Project
Agent
Conversation
Message
Provider
ModelConfig
Task
TaskRun
Pipeline
PipelineNode
PipelineRun
Tool
Integration
GitHubConnection
TelegramConnection
Artifact
ExecutionLog

Use the repository's existing ORM/database stack.

Do not introduce another ORM unless absolutely necessary.

Validate:

- schema
- migrations
- relations
- indexes
- timestamps
- cascade rules
- transaction boundaries
- uniqueness
- foreign keys

Ensure migrations work from a fresh environment.

Never destroy user data casually.

