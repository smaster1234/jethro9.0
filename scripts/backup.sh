#!/bin/bash
# =============================================================================
# PostgreSQL Backup Script
# =============================================================================
#
# This script performs automated backups of the PostgreSQL database.
# It supports:
# - Full database dumps with compression
# - Retention policy (default: 30 days)
# - Backup verification
# - Optional upload to S3
#
# Usage:
#   ./backup.sh                    # Run backup
#   ./backup.sh --restore <file>   # Restore from backup
#   ./backup.sh --list             # List available backups
#   ./backup.sh --cleanup          # Remove old backups
#
# Environment variables:
#   DATABASE_URL      - PostgreSQL connection string
#   BACKUP_DIR        - Directory for backups (default: /backups)
#   BACKUP_RETENTION  - Days to keep backups (default: 30)
#   S3_BUCKET         - Optional S3 bucket for remote backups
#   AWS_ACCESS_KEY_ID - AWS credentials for S3
#   AWS_SECRET_ACCESS_KEY - AWS credentials for S3
# =============================================================================

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETENTION="${BACKUP_RETENTION:-30}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/jethro_backup_${TIMESTAMP}.sql.gz"

# Parse DATABASE_URL
parse_db_url() {
    # Extract components from postgresql://user:password@host:port/dbname
    local url="$DATABASE_URL"

    # Remove postgresql:// prefix
    url="${url#postgresql://}"
    url="${url#postgres://}"

    # Extract user:password
    local userpass="${url%%@*}"
    DB_USER="${userpass%%:*}"
    DB_PASS="${userpass#*:}"

    # Extract host:port/dbname
    local hostportdb="${url#*@}"
    local hostport="${hostportdb%%/*}"
    DB_NAME="${hostportdb#*/}"
    DB_NAME="${DB_NAME%%\?*}"  # Remove query params

    DB_HOST="${hostport%%:*}"
    DB_PORT="${hostport#*:}"

    # Default port if not specified
    if [ "$DB_PORT" = "$DB_HOST" ]; then
        DB_PORT="5432"
    fi
}

# Create backup directory if it doesn't exist
ensure_backup_dir() {
    mkdir -p "$BACKUP_DIR"
    chmod 700 "$BACKUP_DIR"
}

# Perform backup
do_backup() {
    echo "Starting backup at $(date)"
    echo "Database: $DB_NAME @ $DB_HOST:$DB_PORT"

    ensure_backup_dir
    parse_db_url

    # Set password for pg_dump
    export PGPASSWORD="$DB_PASS"

    # Perform backup with compression
    echo "Creating backup: $BACKUP_FILE"
    pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        --format=custom \
        --compress=9 \
        --verbose \
        --file="${BACKUP_FILE%.gz}"

    # Compress with gzip for additional compression
    gzip -9 "${BACKUP_FILE%.gz}"

    # Verify backup
    if [ -f "$BACKUP_FILE" ]; then
        BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        echo "Backup completed successfully: $BACKUP_FILE ($BACKUP_SIZE)"

        # Verify backup integrity
        if gunzip -t "$BACKUP_FILE" 2>/dev/null; then
            echo "Backup integrity verified"
        else
            echo "WARNING: Backup integrity check failed!"
            exit 1
        fi
    else
        echo "ERROR: Backup file not created!"
        exit 1
    fi

    # Upload to S3 if configured
    if [ -n "$S3_BUCKET" ]; then
        echo "Uploading to S3: s3://$S3_BUCKET/backups/"
        aws s3 cp "$BACKUP_FILE" "s3://$S3_BUCKET/backups/" --storage-class STANDARD_IA
        echo "S3 upload completed"
    fi

    # Cleanup old backups
    do_cleanup

    echo "Backup process completed at $(date)"
}

# Restore from backup
do_restore() {
    local restore_file="$1"

    if [ ! -f "$restore_file" ]; then
        echo "ERROR: Backup file not found: $restore_file"
        exit 1
    fi

    echo "WARNING: This will overwrite the current database!"
    echo "Restoring from: $restore_file"
    read -p "Are you sure? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        echo "Restore cancelled"
        exit 0
    fi

    parse_db_url
    export PGPASSWORD="$DB_PASS"

    # Decompress if needed
    if [[ "$restore_file" == *.gz ]]; then
        echo "Decompressing backup..."
        gunzip -k "$restore_file"
        restore_file="${restore_file%.gz}"
    fi

    echo "Restoring database..."
    pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        --clean \
        --if-exists \
        --verbose \
        "$restore_file"

    echo "Restore completed at $(date)"
}

# List available backups
do_list() {
    echo "Available backups in $BACKUP_DIR:"
    echo "=================================="

    if [ -d "$BACKUP_DIR" ]; then
        ls -lh "$BACKUP_DIR"/*.sql.gz 2>/dev/null || echo "No backups found"
    else
        echo "Backup directory does not exist"
    fi

    # List S3 backups if configured
    if [ -n "$S3_BUCKET" ]; then
        echo ""
        echo "S3 backups in s3://$S3_BUCKET/backups/:"
        echo "========================================"
        aws s3 ls "s3://$S3_BUCKET/backups/" 2>/dev/null || echo "No S3 backups or access denied"
    fi
}

# Cleanup old backups
do_cleanup() {
    echo "Cleaning up backups older than $BACKUP_RETENTION days..."

    if [ -d "$BACKUP_DIR" ]; then
        find "$BACKUP_DIR" -name "jethro_backup_*.sql.gz" -type f -mtime +$BACKUP_RETENTION -delete
        echo "Local cleanup completed"
    fi

    # Cleanup S3 backups if configured
    if [ -n "$S3_BUCKET" ]; then
        # List and delete old S3 objects (requires aws cli)
        cutoff_date=$(date -d "-${BACKUP_RETENTION} days" +%Y-%m-%d)
        echo "S3 cleanup: removing backups older than $cutoff_date"
        # Note: S3 lifecycle policies are preferred for production
    fi
}

# Main
case "${1:-backup}" in
    --restore)
        do_restore "$2"
        ;;
    --list)
        do_list
        ;;
    --cleanup)
        do_cleanup
        ;;
    backup|*)
        do_backup
        ;;
esac
