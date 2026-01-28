#!/bin/bash
# Database backup script for UTrack backend
# Usage: ./scripts/backup_database.sh

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS="${RETENTION_DAYS:-30}"

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Generate backup filename
BACKUP_FILE="$BACKUP_DIR/utrack_backup_$TIMESTAMP.sql"

# Check if running in Docker
if [ -f /.dockerenv ] || [ -n "$DOCKER_CONTAINER" ]; then
    echo "Running inside Docker container..."
    
    # Use docker exec to run pg_dump
    if [ -n "$POSTGRES_USER" ] && [ -n "$POSTGRES_PASSWORD" ] && [ -n "$POSTGRES_DB" ]; then
        docker-compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$BACKUP_FILE"
    else
        echo "Error: Database credentials not set in environment"
        exit 1
    fi
else
    # Running on host machine
    if [ -n "$DATABASE_URL" ]; then
        # Extract connection details from DATABASE_URL
        # Format: postgres://user:password@host:port/dbname
        pg_dump "$DATABASE_URL" > "$BACKUP_FILE"
    elif [ -n "$POSTGRES_USER" ] && [ -n "$POSTGRES_PASSWORD" ] && [ -n "$POSTGRES_DB" ]; then
        PGHOST="${DB_HOST:-localhost}"
        PGPORT="${DB_PORT:-5432}"
        export PGPASSWORD="$POSTGRES_PASSWORD"
        pg_dump -h "$PGHOST" -p "$PGPORT" -U "$POSTGRES_USER" "$POSTGRES_DB" > "$BACKUP_FILE"
    else
        echo "Error: Database credentials not configured"
        exit 1
    fi
fi

# Compress backup
gzip "$BACKUP_FILE"
BACKUP_FILE="${BACKUP_FILE}.gz"

echo "Backup created: $BACKUP_FILE"

# Remove old backups (older than RETENTION_DAYS)
find "$BACKUP_DIR" -name "utrack_backup_*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete
echo "Removed backups older than $RETENTION_DAYS days"

# List current backups
echo ""
echo "Current backups:"
ls -lh "$BACKUP_DIR"/utrack_backup_*.sql.gz 2>/dev/null || echo "No backups found"
