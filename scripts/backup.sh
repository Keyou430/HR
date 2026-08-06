#!/bin/bash
# ---------------------------------------------------------------------------
# backup.sh — PostgreSQL backup with retention rotation
# ---------------------------------------------------------------------------
# Dumps the PostgreSQL database using pg_dump -Fc (custom format).
# Rotates backups older than BACKUP_RETENTION_DAYS (default 14).
#
# Environment variables expected:
#   PGHOST / PGDATABASE / PGUSER / PGPASSWORD  — connection info
#   BACKUP_DIR                                  — where to write dumps
#   BACKUP_RETENTION_DAYS                       — age threshold for deletion
# ---------------------------------------------------------------------------
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
DUMP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"

echo "[backup] Dumping database to ${DUMP_FILE}..."
pg_dump -Fc -f "${DUMP_FILE}"

echo "[backup] Rotating backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "backup_*.dump" -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true

echo "[backup] Complete — $(du -h "${DUMP_FILE}" | cut -f1)"
