#!/bin/sh
# Backup & recovery: nightly pg_dump with rotation (keeps $BACKUP_KEEP dumps).
#   restore:  pg_restore -h <host> -U <user> -d <db> --clean /backups/confluence-<stamp>.dump
set -eu
: "${POSTGRES_USER:?}" "${POSTGRES_DB:?}"
export PGPASSWORD="${POSTGRES_PASSWORD:-}"
HOST="${PGHOST:-timescaledb}"; KEEP="${BACKUP_KEEP:-7}"; DIR="${BACKUP_DIR:-/backups}"
run() {
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  pg_dump -h "$HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$DIR/confluence-$stamp.dump"
  echo "backup written: $DIR/confluence-$stamp.dump"
  ls -1t "$DIR"/confluence-*.dump 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
}
mkdir -p "$DIR"
if [ "${1:-}" = "--loop" ]; then
  while true; do run; sleep 86400; done
else
  run
fi
