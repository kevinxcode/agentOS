#!/usr/bin/env bash
# Sourced by backup/restore. Never source an operator .env as executable shell code.
# shellcheck disable=SC2034
set -euo pipefail
umask 077
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
fail() { echo "$*" >&2; exit 1; }
explicit_file() {
  [[ $1 == /* && -f $1 && ! -L $1 ]] || fail "Expected an absolute, regular, non-symlink file"
}
configure_target() {
  local variable
  project=$1
  envfile=$2
  [[ $project =~ ^agentos(-[a-z0-9][a-z0-9-]*)?$ ]] || fail "Project must be agentos or agentos-<explicit-name>"
  explicit_file "$envfile"
  [[ $(stat -c '%a' "$envfile") == 600 || $(stat -c '%a' "$envfile") == 400 ]] || fail "Environment file must have mode 600 or 400"
  # Compose gives the calling shell precedence over --env-file. Start it with an
  # allowlisted process environment so selected-file credentials cannot be shadowed.
  clean_environment=(env -i "PATH=$PATH")
  for variable in HOME DOCKER_HOST DOCKER_CONTEXT DOCKER_CONFIG DOCKER_CERT_PATH DOCKER_TLS_VERIFY XDG_RUNTIME_DIR; do
    [[ -z ${!variable+x} ]] || clean_environment+=("$variable=${!variable}")
  done
  compose=("${clean_environment[@]}" docker compose --project-name "$project" --env-file "$envfile" -f "$repo_root/compose.yaml")
  # Also clear this shell for helpers and regression-visible fail-closed behavior.
  unset COMPOSE_FILE COMPOSE_PROFILES
  for variable in "${!AGENTOS_@}"; do unset "$variable"; done
}
require_stopped_writers() {
  local running service
  running=$("${compose[@]}" ps --services --status running) || fail "Cannot inspect target stack"
  while IFS= read -r service; do
    case "$service" in ''|postgres|redis|minio) ;; *) fail "Refusing operation: application stack is running ($service). Stop all writers first." ;; esac
  done <<< "$running"
}
require_restore_volumes_absent() {
  local existing volume
  restore_volumes=("${project}_postgres_data" "${project}_minio_data")
  for volume in "${restore_volumes[@]}"; do
    existing=$("${clean_environment[@]}" docker volume ls --quiet --filter "name=^${volume}$") || fail "Cannot inspect Docker volumes"
    [[ -z $existing ]] || fail "Restore target volume already exists: $volume"
  done
}
claim_restore_volumes() {
  local actual logical volume
  restore_nonce=${work##*/}
  owned_restore_volumes=()
  for logical in postgres_data minio_data; do
    volume="${project}_${logical}"
    "${clean_environment[@]}" docker volume create \
      --label "com.docker.compose.project=$project" \
      --label "com.docker.compose.volume=$logical" \
      --label "agentos.restore.nonce=$restore_nonce" \
      "$volume" >/dev/null || fail "Cannot create restore volume: $volume"
    actual=$("${clean_environment[@]}" docker volume inspect --format '{{ index .Labels "agentos.restore.nonce" }}|{{ index .Labels "com.docker.compose.project" }}|{{ index .Labels "com.docker.compose.volume" }}' "$volume") || fail "Cannot verify restore-created volume: $volume"
    [[ $actual == "$restore_nonce|$project|$logical" ]] || fail "Restore volume is not owned by this restore invocation: $volume"
    owned_restore_volumes+=("$volume")
  done
}
remove_owned_restore_volumes() {
  local actual cleanup_failed=0 volume
  if ((compose_start_attempted == 1)); then
    if ! "${compose[@]}" down --remove-orphans; then
      cleanup_failed=1
    fi
  fi
  for volume in "${owned_restore_volumes[@]}"; do
    actual=$("${clean_environment[@]}" docker volume inspect --format '{{ index .Labels "agentos.restore.nonce" }}' "$volume") || {
      echo "CRITICAL: cannot verify rollback ownership of volume $volume; it was not removed." >&2
      cleanup_failed=1
      continue
    }
    if [[ $actual != "$restore_nonce" ]]; then
      echo "CRITICAL: rollback ownership changed for volume $volume; it was not removed." >&2
      cleanup_failed=1
      continue
    fi
    if ! "${clean_environment[@]}" docker volume rm "$volume" >/dev/null; then
      cleanup_failed=1
    fi
  done
  return "$cleanup_failed"
}
private_temp() {
  work=$(mktemp -d /tmp/agentos-backup.XXXXXXXX)
  # Only this exact mktemp-created directory is ever removed.
  trap cleanup_private_temp EXIT
}
cleanup_private_temp() {
  [[ -n ${work:-} && $work == /tmp/agentos-backup.* ]] && rm -r -- "$work"
}
