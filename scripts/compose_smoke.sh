#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

[[ ${COMPOSE_PROJECT_NAME:-agentos-smoke} == agentos-smoke* ]] || {
  echo 'Smoke requires a disposable agentos-smoke project' >&2; exit 1;
}
command -v docker >/dev/null || { echo 'Docker is required for Compose smoke' >&2; exit 1; }
COMPOSE_PROJECT_NAME="agentos-smoke-$(date +%s)-$$"
# Generate a protected explicit file; inherited AGENTOS_* values never reach Compose.
umask 077
work=$(mktemp -d /tmp/agentos-compose-smoke.XXXXXXXX)
python3 scripts/generate_env.py "$work/environment" http://localhost:3400
printf 'AGENTOS_WEB_PORT=3400\n' >> "$work/environment"
# shellcheck source=scripts/operations_common.sh
source scripts/operations_common.sh
configure_target "$COMPOSE_PROJECT_NAME" "$work/environment"

services=(web api postgres redis minio)

cleanup() {
  status=$?
  trap - EXIT

  if ((status != 0)); then
    "${compose[@]}" ps || true
  fi

  "${compose[@]}" down --remove-orphans || true
  echo "Disposable volumes retained: ${COMPOSE_PROJECT_NAME}_postgres_data and ${COMPOSE_PROJECT_NAME}_minio_data"
  [[ $work == /tmp/agentos-compose-smoke.* ]] && rm -r -- "$work"

  exit "$status"
}
trap cleanup EXIT

"${compose[@]}" config --quiet
"${compose[@]}" up --detach --build

deadline=$(($(date +%s) + 120))
while (($(date +%s) < deadline)); do
  all_healthy=1
  for service in "${services[@]}"; do
    container_id=$("${compose[@]}" ps --quiet "$service")
    if [[ -z $container_id ]]; then
      all_healthy=0
      break
    fi

    health=$("${clean_environment[@]}" docker inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      "$container_id" 2>/dev/null || true)
    if [[ $health != healthy ]]; then
      all_healthy=0
      break
    fi
  done

  if ((all_healthy == 1)); then
    break
  fi
  sleep 2
done

if ((all_healthy != 1)); then
  echo "Compose services did not become healthy within 120 seconds" >&2
  exit 1
fi

liveness=$("${compose[@]}" exec --no-TTY web \
  wget --quiet --output-document=- http://api:8000/health/live)
if [[ $liveness != *'"status":"alive"'* ]]; then
  echo "Unexpected API liveness response: $liveness" >&2
  exit 1
fi

echo "All AgentOS Compose services are healthy; API liveness is reachable from web."
