# Cloudflare Tunnel

The only public route is `https://agentos.example.com` → `http://web:3000`.
The web same-origin proxies call the private API. Never map the public hostname
to `api:8000`, MinIO, Redis or PostgreSQL. Cloudflare Access may be an additional
restriction but does not replace AgentOS password/TOTP authentication.

Production Compose publishes the web port only on `127.0.0.1`; it is not a second
public entry point. Cloudflare supplies `CF-Connecting-IP` at the web boundary.
The web proxy validates that address, ignores browser-supplied AgentOS internal
identity headers, and sends it to the private API with the generated
`AGENTOS_AUTH_PROXY_SECRET`. The API trusts the client address only when that secret
matches; direct or spoofed forwarded headers fall back to the actual network peer.

Create a locally managed named tunnel following
[Cloudflare's configuration-file guide](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/local-management/configuration-file/).
Use its UUID and credentials JSON; protect files outside Git with mode 0600.
Create the DNS route for your hostname. A minimal `config.yml` is:

On the operator's trusted machine with cloudflared installed:

```bash
cloudflared tunnel login
cloudflared tunnel create agentos
cloudflared tunnel route dns agentos agentos.example.com
```

Transfer only the created tunnel's credentials JSON to the server over your
approved secure channel; the account-wide `cert.pem` stays on the operator machine.
Record the returned tunnel UUID in the configuration below.

```yaml
tunnel: YOUR-TUNNEL-UUID
credentials-file: /etc/cloudflared/credentials.json
ingress:
  - hostname: agentos.example.com
    service: http://web:3000
  - service: http_status:404
```

Run cloudflared in its own operator-managed Compose project using a reviewed,
pinned image digest. Mount the config and credentials read-only, drop capabilities,
set `no-new-privileges:true`, and attach it to both:

- external network `agentos_agentos_private` (created by production Compose);
- its own normal bridge network for outbound Cloudflare connectivity.

The private network is `internal: true`; a connector attached only to it cannot
reach Cloudflare. The second network is for the connector only; do not add egress
or host ports to the API/database. The connector needs no Docker socket or published
port. Explicitly review its UID and credentials-file permissions before starting.
The cloudflared container command is `tunnel --config /etc/cloudflared/config.yml run`.

For example, place this operator-owned file at `/etc/agentos/tunnel-compose.yaml`,
with a reviewed `CLOUDFLARED_IMAGE` digest in `/etc/agentos/tunnel.env` (mode 0600).
Both mounted files must be readable by the explicitly selected non-root UID;
use a dedicated group or narrowly scoped ACL, not world-readable credentials.

```yaml
name: agentos-tunnel
services:
  cloudflared:
    image: ${CLOUDFLARED_IMAGE:?Set reviewed cloudflare/cloudflared@sha256 digest}
    command: tunnel --config /etc/cloudflared/config.yml run
    user: "65532:65532"
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    restart: unless-stopped
    volumes:
      - /etc/agentos/cloudflared/config.yml:/etc/cloudflared/config.yml:ro
      - /etc/agentos/cloudflared/credentials.json:/etc/cloudflared/credentials.json:ro
    networks: [private, egress]
networks:
  private:
    external: true
    name: agentos_agentos_private
  egress: {}
```

```bash
tunnel_dc() {
  env -i PATH="$PATH" HOME="$HOME" docker compose --project-name agentos-tunnel \
    --env-file /etc/agentos/tunnel.env -f /etc/agentos/tunnel-compose.yaml "$@"
}
tunnel_dc config --quiet
tunnel_dc up -d
```

The allowlisted environment ensures an inherited `CLOUDFLARED_IMAGE` or Compose
override cannot shadow the protected tunnel environment and exact Compose file.

Generate the production env with the external origin (for example,
`https://agentos.example.com:443/`); it is stored canonically as
`https://agentos.example.com`. Recreate web after changes. Keep HTTPS at Cloudflare,
do not disable origin checks, and do not rely on untrusted `Host`/forwarded headers
for CSRF validation.

Verify from outside the server: HTTPS certificate, anonymous redirect to `/login`,
password → enrollment/verification → Mission Control, Audit page, logout and renewed
login requirement. A cross-origin mutation must be rejected. Verify the tunnel's
fallback returns 404 for other hostnames. Verify no private port is reachable from
outside. Keep login screens/recovery codes out of screenshots and shared logs.

For rollback to a restored project, stop both connectors/writers first and attach
the connector to that project's explicit private network. Avoid attaching to two
networks that both advertise `web`, which makes service-name routing ambiguous.
