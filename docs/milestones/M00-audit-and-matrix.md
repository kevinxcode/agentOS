==================================================
MILESTONE 0 — CODEBASE AUDIT + COMPLETION MATRIX
==================================================

GOAL
Produce docs/PROJECT_COMPLETION.md: an accurate map of what exists,
what is partial, and what is missing. No feature code in this milestone.

--------------------------------------------------
CRITICAL: WRITE AS YOU GO
--------------------------------------------------

Your conversation context is compressed periodically. Anything you only
hold "in your head" WILL be lost, and you will re-read the same files
forever without making progress.

Therefore: after auditing each area below, IMMEDIATELY append your
findings to docs/PROJECT_COMPLETION.md before moving to the next area.
Never audit two areas before writing.

If docs/PROJECT_COMPLETION.md already has a section for an area, that
area is DONE. Skip it. Do not re-read its files.

Start each session by reading docs/PROJECT_COMPLETION.md first to see
how far you already got.

--------------------------------------------------
AREAS TO AUDIT — IN THIS ORDER
--------------------------------------------------

Do them one at a time. Write after each.

1. Repo layout and tooling
   Files: package.json, pnpm-workspace.yaml, Makefile, pytest.ini,
   .editorconfig, .github/
   Record: build commands, test commands, lint commands, CI status.

2. Backend: config, db, crypto
   Files: services/api/src/agentos/config.py, db.py, crypto.py
   Record: settings shape, DB session handling, migration setup.

3. Backend: auth
   Files: services/api/src/agentos/auth/*
   Record: what auth flows exist and work end to end.

4. Backend: audit + api surface
   Files: services/api/src/agentos/audit/*, api/app.py, api/routes/*
   Record: every route that exists today, with method and path.

5. Frontend
   Files: apps/web/app/**, apps/web/lib/**, apps/web/components/**
   Record: every page and API route that exists, and what it does.

6. Infrastructure
   Files: compose.yaml, infra/compose/*, scripts/*, Dockerfiles
   Record: how to run it locally, what services are defined.

7. Tests
   Files: tests/**, services/api/tests/**, apps/web/tests/**, e2e/
   Record: what is actually covered.

--------------------------------------------------
REQUIRED OUTPUT FORMAT
--------------------------------------------------

docs/PROJECT_COMPLETION.md must contain, per area:

## <area name>

### Exists and works
- <fact, with file path>

### Partial / stubbed
- <fact, with file path, and what is missing>

### Missing entirely
- <what the AgentOS goal needs that is absent>

Every line must cite a real file path you actually opened.
Do not write a line you cannot point to in the repo.

--------------------------------------------------
FINAL STEP
--------------------------------------------------

After all 7 areas are written, append one last section:

## Completion matrix

A table: feature | status (DONE / PARTIAL / MISSING) | which milestone covers it

Cover every capability named in AGENTS.md PRIMARY OBJECTIVE:
providers, agents, orchestration, tasks/kanban, pipelines, GitHub,
Telegram, content/image, projects/workspaces, history, web UI.

--------------------------------------------------
VERIFICATION
--------------------------------------------------

Before marking DONE in QUEUE.md, confirm:
- docs/PROJECT_COMPLETION.md is non-empty and has all 7 area sections
- it has the completion matrix
- every file path cited actually exists (spot check at least 10)
- committed locally

Then STOP. Do not start M01.
