
==================================================
MILESTONE 5 — MULTI-AGENT ORCHESTRATION
==================================================

Implement practical multi-agent workflows.

Required patterns:

SEQUENTIAL

Agent A
→ Agent B
→ Agent C


REVIEW

Coder
→ Reviewer
→ Coder correction
→ Complete


PARALLEL

Research Agent
Content Agent
Code Agent

→ Aggregator


ROUTER

Request
→ Planner
→ choose specialist
→ specialist execution


LOOP

Generate
→ Review
→ failed?
→ revise
→ review again

Loops MUST have:

maxIterations

to prevent infinite execution.

