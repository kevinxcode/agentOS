.PHONY: install lint typecheck test build

PNPM = COREPACK_HOME="$(CURDIR)/.corepack" corepack pnpm@10.15.1
UV = uv

install:
	$(PNPM) install --frozen-lockfile
	$(UV) sync --frozen --project services/api --extra dev

lint:
	$(PNPM) --filter @agentos/web lint
	$(UV) run --project services/api ruff check services/api tests

typecheck:
	$(PNPM) --filter @agentos/web typecheck
	$(UV) run --project services/api mypy services/api/src

test:
	$(PNPM) --filter @agentos/web test
	$(UV) run --project services/api pytest

build:
	$(PNPM) --filter @agentos/web build
