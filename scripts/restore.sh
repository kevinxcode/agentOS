#!/usr/bin/env bash
set -euo pipefail
if (($# != 4)); then
  echo 'Usage: restore.sh /absolute/backup.tar.age /absolute/age-identity agentos-project /absolute/.env' >&2
  exit 2
fi
# shellcheck source=scripts/operations_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/operations_common.sh"
archive=$1
identity=$2
explicit_file "$archive"
explicit_file "$identity"
configure_target "$3" "$4"
require_stopped_writers
require_restore_volumes_absent
command -v age >/dev/null || fail "Install age before restore"
private_temp
owned_restore_volumes=()
compose_start_attempted=0
restore_exit() {
  status=$?
  trap - EXIT
  if ((status != 0 && ${#owned_restore_volumes[@]} != 0)); then
    echo "Restore failed; removing only volumes created by this restore invocation." >&2
    if ! remove_owned_restore_volumes "$compose_start_attempted"; then
      echo "CRITICAL: automatic rollback failed; keep project $project isolated and inspect it." >&2
    fi
  fi
  cleanup_private_temp
  exit "$status"
}
trap restore_exit EXIT
age --decrypt --identity "$identity" --output "$work/backup.tar" "$archive"
python3 "$repo_root/scripts/backup_archive.py" validate "$work/backup.tar" "$work/validated"
echo "Validated archive: $archive"
echo "Target: project=$project compose=$repo_root/compose.yaml env=$envfile"
echo "Target volumes: ${project}_postgres_data and ${project}_minio_data (must be empty)"
echo "This imports the database and current objects. Existing populated targets are refused."
[[ -t 0 ]] || fail "Restore requires an interactive terminal"
read -r -p "Type RESTORE $project to continue: " confirmation
[[ $confirmation == "RESTORE $project" ]] || fail "Restore cancelled"
require_stopped_writers
require_restore_volumes_absent
claim_restore_volumes
compose_start_attempted=1
"${compose[@]}" up -d --wait postgres minio redis
"${compose[@]}" run --rm -T minio-init
# Check emptiness before any data import; never clean/drop an existing database.
# shellcheck disable=SC2016
count=$("${compose[@]}" exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema = '\''public'\''"')
[[ $count == 0 ]] || fail "Restore database must be empty; use a fresh explicit project"
"${compose[@]}" run --rm --no-deps -T api python /app/scripts/backup_archive.py check-empty
# shellcheck disable=SC2016
"${compose[@]}" exec -T postgres sh -c 'exec pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --exit-on-error --single-transaction --no-owner --no-acl' < "$work/validated/database.dump"
"${compose[@]}" run --rm --no-deps -T --user "$(id -u):$(id -g)" -v "$work/validated:/restore:ro" api python /app/scripts/backup_archive.py import /restore/objects.tar
echo "Restore rehearsal imported successfully. Application services remain stopped; verify migrations, objects and authentication before startup."
