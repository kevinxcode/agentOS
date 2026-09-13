#!/usr/bin/env bash
set -euo pipefail
if (($# != 4)); then
  echo 'Usage: backup.sh /absolute/output-directory age1recipient agentos-project /absolute/.env' >&2
  exit 2
fi
# shellcheck source=scripts/operations_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/operations_common.sh"
output=$1
recipient=$2
[[ $output == /* && -d $output && ! -L $output && $output != / ]] || fail "Explicit existing output directory required"
[[ $recipient == age1* ]] || fail "An age public recipient is required"
configure_target "$3" "$4"
require_stopped_writers
command -v age >/dev/null || fail "Install age before backup"
private_temp
# shellcheck disable=SC2016
"${compose[@]}" exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' > "$work/database.dump"
"${compose[@]}" run --rm --no-deps -T api python /app/scripts/backup_archive.py export > "$work/objects.tar"
python3 "$repo_root/scripts/backup_archive.py" pack "$work" "$work/backup.tar"
python3 "$repo_root/scripts/backup_archive.py" validate "$work/backup.tar" "$work/validated"
archive="$output/agentos-$(date -u +%Y%m%dT%H%M%SZ)-${work##*.}.tar.age"
age --recipient "$recipient" --output "$work/encrypted.age" "$work/backup.tar"
# Reserve a unique destination without replacing an existing archive.
(set -o noclobber; umask 077; : > "$archive") || fail "Backup destination already exists"
if ! cp -- "$work/encrypted.age" "$archive"; then
  fail "Encrypted backup copy failed; incomplete destination retained for inspection"
fi
echo "Encrypted backup created: $archive"
