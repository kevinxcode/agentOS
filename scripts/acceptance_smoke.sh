#!/usr/bin/env bash
# Explicit disposable project only; never accepts a production project name.
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
command -v docker >/dev/null || { echo 'Docker is required for Compose acceptance' >&2; exit 1; }
umask 077
work=$(mktemp -d /tmp/agentos-acceptance.XXXXXXXX)
COMPOSE_PROJECT_NAME="agentos-acceptance-$(date +%s)-$$"
acceptance_origin=http://127.0.0.1:3000
python3 scripts/generate_env.py "$work/environment" "$acceptance_origin"
printf 'AGENTOS_WEB_PORT=3300\n' >> "$work/environment"
# shellcheck source=scripts/operations_common.sh
source scripts/operations_common.sh
configure_target "$COMPOSE_PROJECT_NAME" "$work/environment"
browser_image="${COMPOSE_PROJECT_NAME}-browser"
cleanup() {
  status=$?
  trap - EXIT
  "${compose[@]}" down --remove-orphans || true
  "${clean_environment[@]}" docker image rm "$browser_image" >/dev/null 2>&1 || true
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
mapfile -t container_ids < <("${compose[@]}" ps --all --quiet)
if ((${#container_ids[@]} == 0)); then
  echo 'Compose returned no containers' >&2
  exit 1
fi
"${clean_environment[@]}" docker inspect "${container_ids[@]}" | python3 scripts/check_ports.py
web_container_id=$("${compose[@]}" ps --quiet web)
[[ -n $web_container_id ]] || { echo 'Web container is missing' >&2; exit 1; }
"${clean_environment[@]}" docker build -f apps/web/Dockerfile.acceptance -t "$browser_image" .
"${clean_environment[@]}" docker run --rm \
  --network "container:$web_container_id" \
  -e AGENTOS_PUBLIC_ORIGIN="$acceptance_origin" \
  "$browser_image"
# shellcheck disable=SC2016
events=$("${compose[@]}" exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT action FROM audit_events WHERE outcome = '\''success'\''"')
for action in auth.login auth.totp.enrolled auth.logout; do
  [[ $'\n'$events$'\n' == *$'\n'"$action"$'\n'* ]] || { echo "Missing audit event: $action" >&2; exit 1; }
done
echo 'Compose foundation acceptance passed'
