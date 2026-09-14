# Ubuntu deployment runbook

## Prerequisites and trust boundary

Use a maintained Ubuntu 24.04 LTS host, synchronized time (`timedatectl status`),
adequate persistent disk, outbound registry access, Docker Engine with Compose v2,
Python 3.12+ for operational helpers, `age`, and an HTTPS hostname. Install Docker
using the [official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/)
and verify `docker version` and `docker compose version`. Docker group membership
is root-equivalent; restrict it to operators. Do not attach the Docker socket to
any AgentOS service. No GPU is required for this foundation milestone.

Clone the reviewed repository into `/opt/agentos` and checkout an approved commit
or release tag. Record `git rev-parse HEAD`. Run commands below from that directory.
Do not use a mutable branch as an unattended deployment source.

## Create protected configuration

As the deployment operator, create `/etc/agentos` with mode 0700 and operator
ownership. The generator refuses to overwrite an existing file and writes mode
0600. It generates independent PostgreSQL/MinIO credentials, a valid Fernet
master key, session pepper, and independent web-to-API proxy secret without
printing them.

```bash
python3 scripts/generate_env.py /etc/agentos/production.env https://agentos.example.com
stat -c '%a %U %n' /etc/agentos/production.env
```

Replace the hostname with yours. The file contains all Compose-required variables
(including PostgreSQL database/user/password absent from the API-only `.env.example`).
Keep it outside the repository. Never run `set -x`, paste it into tickets, or run
plain `docker compose config` in shared logs: resolved configuration includes secrets.
Retain an encrypted offline copy; losing `AGENTOS_MASTER_KEY` loses access to TOTP
seeds. Keep the original session pepper with a restored database; deliberate pepper
rotation invalidates existing sessions. This file is not included in application backups.

Use the checked-in wrapper so every operation targets the exact environment and
project. It launches Compose with an allowlisted process environment: inherited
`AGENTOS_*`, `COMPOSE_FILE`, and `COMPOSE_PROFILES` values cannot override the
protected file or checked-in Compose contract.

```bash
dc() { /opt/agentos/scripts/agentos-compose.sh agentos /etc/agentos/production.env "$@"; }
dc config --quiet
dc build --pull
dc up -d --wait postgres redis minio
dc run --rm -T minio-init
dc run --rm --no-deps -T api alembic -c /app/alembic.ini upgrade head
dc run --rm --no-deps api python /app/scripts/bootstrap_admin.py --email admin@example.com
dc up -d --wait
```

Bootstrap prompts without echo for a 12–1024 character password. Repeating the
same email is a no-op; a different email is refused. There is no registration API
or command-line password option. For controlled automation use a private mounted
password file with `AGENTOS_BOOTSTRAP_PASSWORD_FILE`, then remove that exact file.

Configure [the tunnel](cloudflare-tunnel.md) before first browser login. Password
alone creates a five-minute pre-auth session, not a dashboard session. Enroll TOTP,
save the ten recovery codes privately, acknowledge storage, then enter Mission
Control. Codes are shown once, stored as hashes and usable once. Use synchronized
authenticator time; replayed codes are rejected. Full sessions expire after 12 hours
or 30 minutes idle. Do not disable Secure cookies to troubleshoot HTTPS.

## Health and network checks

```bash
mapfile -t container_ids < <(dc ps --all --quiet)
((${#container_ids[@]} > 0)) || { echo 'Compose returned no containers' >&2; exit 1; }
docker inspect "${container_ids[@]}" | python3 scripts/check_ports.py
dc exec -T api python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/health/ready").read().decode())'
dc exec -T api alembic -c /app/alembic.ini current
```

Only web publishes a host port, and the base Compose binds it to `127.0.0.1`.
The live port check fails if that publication changes to a wildcard or non-loopback
address. Never publish API, PostgreSQL, Redis or MinIO as a shortcut. The containerized
tunnel reaches `web:3000` through Docker networking, not a database/API port; a
host-managed tunnel may use the loopback publication.
Readiness reports only up/down dependency names. During a maintenance rehearsal,
stop each of postgres/redis/minio in turn, verify readiness returns 503 with that
dependency down and no credentials, restart it and verify recovery. Do not run
failure injection on a live production installation.

## Upgrade and rollback

1. Announce maintenance; stop the tunnel, web and API (and any future writers).
2. Make and validate an encrypted backup; retain the prior Git commit, image IDs,
   production environment, and migration revision. Do not prune old images/volumes.
3. Checkout the approved new revision; review schema changes and rollback notes.
   Build images, run migrations with writers stopped, then `dc up -d --wait`.
4. Check readiness, published ports, login/TOTP/logout and Audit through HTTPS.
   Reopen the tunnel only after the checks pass.
5. On failure keep writers stopped. If schema-compatible, select the recorded old
   revision/images and restart. Otherwise restore the pre-upgrade backup into a
   **fresh explicitly named project**, validate it and switch the tunnel. Do not
   blindly downgrade a migration or overwrite production volumes.

## Troubleshooting

- Unhealthy API: inspect readiness and private `dc logs --tail 100 api`; never paste
  raw logs without reviewing redaction. Confirm credentials privately and bucket init.
- Migration/bootstrap failure: confirm command uses the same `dc` project/env; API
  image now includes `/app/alembic.ini`, migrations and operational scripts.
- Browser mutation rejected: `AGENTOS_PUBLIC_ORIGIN` must match exactly the external
  scheme/host/non-default-port, not `http://web:3000` or the API URL. The generator
  lowercases the host, removes a trailing slash, and removes default ports (`:443`
  for HTTPS and `:80` for HTTP); the web validator applies the same normalization.
  HTTPS is required except for loopback-only disposable tests. Only one origin is
  supported. Hostnames use a deliberately narrow ASCII DNS grammar; non-ASCII,
  percent-encoded or trailing-dot authorities, backslashes, and ambiguous
  abbreviated/numeric IPv4 forms such as `127.1` are rejected rather than
  interpreted differently across runtimes. HTTP accepts only exact `localhost`,
  `127.0.0.1`, or `[::1]` loopback authorities.
- Login clients unexpectedly share a rate limit: Cloudflare must provide its
  `CF-Connecting-IP` header to the web container. The web proxy discards any browser
  attempt to set AgentOS internal identity headers, replaces them with the validated
  Cloudflare address, and authenticates that value to the private API with
  `AGENTOS_AUTH_PROXY_SECRET`. Keep that generated value identical in web and API;
  rotate it by updating the protected environment and recreating both services.
- TOTP failure: check host/authenticator clocks, rate limits (five attempts/minute)
  and whether that time-step's code was already used. Use a saved recovery code
  after password login when needed; there is no unaudited bypass.
- Space shortage: stop writers before backup. Plaintext temporary staging and
  encrypted output require additional space; do not delete named volumes blindly.
