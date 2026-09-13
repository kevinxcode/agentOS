# Encrypted backup and guarded restore

## What is protected

`backup.sh` captures PostgreSQL `pg_dump --format=custom --no-owner --no-acl`
and current MinIO object bytes/content types, verifies nested SHA-256 manifests,
then encrypts the combined timestamped tar using an operator's age public key.
PostgreSQL includes auth/audit records. Redis is transient and is not backed up.
Bucket IAM/policies, object versions, and deployment secrets/configuration are not
included; preserve those separately. Treat archives as sensitive even when encrypted.
Only restore archives from a trusted source: age encryption is not a sender signature.

Prerequisites: Docker Compose, Python 3, `age`, free temporary/output disk, the API
image built from this revision, and an operator-owned mode-0600 environment file.
Stop the tunnel, web, API and all future workers/writers for a consistent cross-store
backup. PostgreSQL/MinIO/Redis may remain running. Scripts refuse any other running
service in the target Compose project and never stop production automatically.
The operator must also stop external writers and prevent concurrent startup.

The scripts use mode-0700 `mktemp` staging with mode-0600 files. Plaintext is staged
on `/tmp` and removed at exit; use encrypted swap/disk or encrypted tmpfs for strict
at-rest requirements. Removal is not a secure erase. Allow roughly twice the database
and objects size plus encrypted output space. The exporter spools one object at a
time to keep memory bounded; it is not an online point-in-time backup system.

## Create and keep a backup

Create an age identity once in an operator-protected location. Store its offline
recovery copy separately from the server and keep only the public recipient on
automated backup hosts. Do not pass private key content on the command line.

```bash
umask 077
age-keygen -o /etc/agentos/backup-identity.txt
# Record the printed age1... public recipient; protect the identity offline.
dc stop web api
bash scripts/backup.sh /srv/agentos-backups age1YOUR_PUBLIC_RECIPIENT agentos /etc/agentos/production.env
dc up -d --wait
```

Create `/srv/agentos-backups` with operator ownership and mode 0700 first. Backup
filenames are unique, output publication is no-clobber, and failures retain no
successful-looking plaintext artifact. An interrupted destination copy may leave
an incomplete encrypted file: validate before retention or transfer. Keep encrypted
copies off-host; apply a deliberate retention policy only after successful rehearsal.
Save the matching Git revision/image IDs and encrypted deployment environment.

## Validate without mutation

On a trusted machine, create a private temporary directory and decrypt there:

```bash
umask 077
validation_dir=$(mktemp -d /tmp/agentos-validation.XXXXXXXX)
age --decrypt --identity /etc/agentos/backup-identity.txt --output "$validation_dir/backup.tar" /srv/agentos-backups/EXACT_FILE.tar.age
python3 scripts/backup_archive.py validate "$validation_dir/backup.tar" "$validation_dir/validated"
```

Validation checks format/version, exact regular-file members, no duplicate names,
custom-format dump magic, whole-payload hashes, object manifest membership and each
object hash. Object keys are JSON values, never extracted paths. No application
mutation happens on bad decryption/checksums. Delete only the exact printed private
validation directory when finished; do not retain its plaintext files.

## Restore rehearsal (required before promotion)

Restore is **fresh-target only**. It never drops tables, deletes individual objects
or runs `pg_restore --clean`. Use a unique project such as
`agentos-rehearsal-20260912`; both exact named volumes must be absent, not merely
empty in the selected database/bucket. Prepare a separate private
environment file using the original master key/session pepper and new or retained
service credentials. Never regenerate the original encryption key for restored data.
Project names and an absolute archive/identity/env path are mandatory. Port 3000 is
irrelevant until starting web; assign a free `AGENTOS_WEB_PORT` for that later step.

```bash
bash scripts/restore.sh /srv/agentos-backups/EXACT_FILE.tar.age /etc/agentos/backup-identity.txt agentos-rehearsal-20260912 /etc/agentos/rehearsal.env
```

The script refuses a running application stack, decrypts/verifies before mutation,
prints the exact Compose file/project/env and volume targets, and requires a real
interactive terminal plus `RESTORE agentos-rehearsal-20260912`. There is no `--yes`
or environment-variable confirmation bypass. It rechecks writers and both absent
volume names after confirmation, then atomically creates-or-verifies each volume
with the Compose labels and a private nonce unique to that restore invocation. A
concurrent restore that wins either volume name has a different or absent nonce, so
this invocation stops before Compose startup. The script starts only data
services/bucket initialization and refuses a
nonempty database or bucket before import. It restores the database transactionally
before importing objects and never starts API, web, or workers. If either import stage fails after
mutation begins, it stops containers without Compose volume deletion, re-verifies
the invocation nonce on every tracked volume, and removes each exact volume only
while that proof still matches. A missing or changed label disables deletion for
that volume and is reported as critical; keep that exact project isolated for
inspection. Successful rehearsal volumes remain available for verification.

Before opening any traffic, verify with the rehearsal project's Compose function:

1. Alembic `current` equals the recorded revision; run `upgrade head` only if the
   selected application version calls for it.
2. Row counts/audit actions and selected MinIO objects match the source; compare
   manifest hashes. A new backup of the rehearsal should validate successfully.
3. Readiness, published-port inspection, real HTTPS password/TOTP login, one-time
   recovery behavior, Audit and logout succeed using the retained keys.
4. Record archive name/hash, source/target revision, operator, timestamp, validation
   and smoke outcomes without recording passwords, TOTP seeds or recovery codes.

Stop the rehearsal services afterward. Keep its exact named volumes until evidence
is approved, then delete only explicitly verified disposable volumes. The automated
local fake-service tests prove guard logic, not Docker, age interoperability or an
actual restore; this operator rehearsal remains a required promotion gate.
