
==================================================
FINAL VERIFICATION GATE
==================================================

Before declaring AgentOS complete, run the FULL verification suite.

At minimum:

dependency install/check
lint
typecheck
unit tests
integration tests
production build
database migration verification
startup verification

Also inspect:

git status
git diff
recent commits

Verify no accidental:

debug files
temporary files
secret files
.env
API tokens
logs
large generated artifacts

were committed.

==================================================
FINAL MANUAL SMOKE TEST
==================================================

Where possible, start the application and manually validate:

Dashboard loads
navigation works
agent creation works
provider selection works
Ollama model discovery works
chat works
streaming works
tasks work
Kanban works
pipeline creation works
pipeline execution works
run history works
settings work
error states render correctly

If browser automation is available, use it.

==================================================
PRODUCTION READINESS CHECK
==================================================

Check for:

build success
runtime startup
schema validity
migrations
environment documentation
health endpoints
Docker startup
safe secrets handling
reasonable logging
useful error messages
no obvious dead links
no major unfinished UI
no critical TODOs

==================================================
FINAL REPOSITORY AUDIT
==================================================

Repeat searches for:

TODO
FIXME
HACK
XXX
placeholder
mock
not implemented
coming soon

Classify remaining occurrences.

Acceptable:

documentation examples
test mocks
future non-MVP roadmap items

Unacceptable:

unfinished critical feature
fake production handler
nonfunctional UI
ignored security requirement

==================================================
WHEN ALL GATES PASS
==================================================

Update:

docs/PROJECT_COMPLETION.md

Everything actually verified should be:

VERIFIED

Then update README if needed.

Create a final local commit such as:

git add .
git commit -m "release: complete AgentOS production readiness"

==================================================
PUSH POLICY
==================================================

STOP BEFORE PUSHING.

Do not execute git push automatically.

At the very end show me:

1. final git branch
2. final git status
3. latest commits
4. build result
5. test result
6. lint result
7. typecheck result
8. migration result
9. major completed features
10. remaining limitations, if any
11. external integrations requiring real credentials
12. whether repository is SAFE TO PUSH

Then wait for my explicit command:

PUSH

Only after I explicitly say PUSH may you push to the configured remote.

==================================================
DEFINITION OF DONE
==================================================

AgentOS is NOT done merely because:

the frontend renders
or
the backend builds
or
most features exist.

DONE means:

- architecture is coherent
- critical features function end-to-end
- provider layer works
- Ollama works
- agents execute
- multi-agent workflows execute
- tasks persist
- Kanban persists
- pipelines execute
- loops are bounded
- GitHub integration is implemented
- Telegram integration is implemented
- errors are handled
- secrets are protected
- database migrations work
- tests pass
- lint passes
- typecheck passes
- production build passes
- documentation is usable
- project can be set up by another developer

==================================================
START NOW
==================================================

Do not give me a generic explanation.

Begin by inspecting the repository.

First print a concise report containing:

1. current branch
2. working tree status
3. repository architecture
4. package manager
5. framework/stack detected
6. database detected
7. existing AgentOS features
8. unfinished areas
9. current test/build health
10. proposed milestone sequence

Then create/update:

docs/PROJECT_COMPLETION.md

Then begin Milestone 1.

Continue autonomously through the milestones.

Commit each verified milestone locally.

DO NOT PUSH.

