
==================================================
MILESTONE 4 — AGENT SYSTEM
==================================================

An Agent must be a real executable entity, not just UI metadata.

Each agent should support:

- name
- description
- role
- system prompt
- provider
- model
- tools
- permissions
- optional project context
- configurable execution parameters

Example agents:

Planner
Researcher
Coder
Reviewer
Content Writer
GitHub Agent
Telegram Agent

Agents must use the common provider layer.

==================================================
AGENT EXECUTION LIFECYCLE
==================================================

A clear lifecycle should exist:

CREATED
QUEUED
RUNNING
WAITING_FOR_TOOL
RETRYING
COMPLETED
FAILED
CANCELLED

Persist meaningful execution state.

Capture:

- start time
- completion time
- selected model
- output
- errors
- tool calls
- token/usage metadata where available

