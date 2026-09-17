
==================================================
MILESTONE 1 — MAKE THE REPOSITORY HEALTHY
==================================================

First establish a clean baseline.

Run the appropriate commands for this repository:

install
lint
typecheck
test
build

Examples only:

npm install
pnpm install
pnpm lint
pnpm typecheck
pnpm test
pnpm build

Determine the correct package manager from the repo.

Fix:

- dependency issues
- compilation failures
- TypeScript errors
- lint errors that reveal real bugs
- broken imports
- invalid environment handling
- startup errors

Do not blindly suppress TypeScript or lint errors.

Avoid:

any
@ts-ignore
eslint-disable

unless there is a documented technical necessity.

Commit when the foundation is stable.

Suggested commit:

chore: stabilize project baseline

