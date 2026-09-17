
==================================================
MILESTONE 8 — GITHUB INTEGRATION
==================================================

GitHub integration should support the architecture already chosen by the repository.

Where supported, provide:

- connect repository
- list repositories
- inspect branches
- inspect files
- inspect issues
- inspect pull requests
- create branch
- modify files
- commit changes
- optionally create PR

Security requirements:

- credentials server-side
- minimum permissions
- no token logging
- clear connection status
- graceful authorization errors

Coding agents should be able to operate against a selected repository through controlled tools.

Do not create dangerous unrestricted shell interfaces exposed to the browser.

