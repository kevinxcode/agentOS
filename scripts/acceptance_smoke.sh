#!/usr/bin/env bash
# Explicit disposable project only; never accepts a production project name.
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
command -v docker >/dev/null || { echo 'Docker is required for Compose acceptance' >&2; exit 1; }
umask 077
work=$(mktemp -d /tmp/agentos-acceptance.XXXXXXXX)
COMPOSE_PROJECT_NAME="agentos-acceptance-$(date +%s)-$$"
python3 scripts/generate_env.py "$work/environment" http://localhost:3300
printf 'AGENTOS_WEB_PORT=3300\n' >> "$work/environment"
# shellcheck source=scripts/operations_common.sh
source scripts/operations_common.sh
configure_target "$COMPOSE_PROJECT_NAME" "$work/environment"
cleanup() {
  status=$?
  trap - EXIT
  "${compose[@]}" down --remove-orphans || true
  echo "Disposable volumes retained for inspection: ${COMPOSE_PROJECT_NAME}_postgres_data and ${COMPOSE_PROJECT_NAME}_minio_data"
  [[ $work == /tmp/agentos-acceptance.* ]] && rm -r -- "$work"
  exit "$status"
}
trap cleanup EXIT
"${compose[@]}" config --quiet
"${compose[@]}" up -d --build --wait
"${compose[@]}" exec -T api alembic -c /app/alembic.ini upgrade head
printf '%s\n' acceptance-password > "$work/password"
"${compose[@]}" run --rm --no-deps -T --user "$(id -u):$(id -g)" -v "$work/password:/bootstrap-password:ro" -e AGENTOS_BOOTSTRAP_PASSWORD_FILE=/bootstrap-password api python /app/scripts/bootstrap_admin.py --email admin@example.com
"${compose[@]}" exec -T api python /app/scripts/bootstrap_admin.py --email admin@example.com
if "${compose[@]}" exec -T api python /app/scripts/bootstrap_admin.py --email other@example.com; then
  echo 'Second administrator unexpectedly accepted' >&2; exit 1
fi
"${compose[@]}" ps --format json | python3 scripts/check_ports.py
(cd apps/web && node e2e/foundation.mjs)
# shellcheck disable=SC2016
events=$("${compose[@]}" exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT action FROM audit_events WHERE outcome = '\''success'\''"')
for action in auth.login auth.totp.enrolled auth.logout; do
  [[ $'\n'$events$'\n' == *$'\n'"$action"$'\n'* ]] || { echo "Missing audit event: $action" >&2; exit 1; }
done
echo 'Compose foundation acceptance passed'
