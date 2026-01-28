#!/bin/bash
# Database restore script for UTrack backend
# Usage: ./scripts/restore_database.sh <backup_file>

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file>"
    echo "Example: $0 ./backups/utrack_backup_20240101_120000.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"

# Check if backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Confirm restore
echo "WARNING: This will replace the current database with the backup!"
echo "Backup file: $BACKUP_FILE"
read -p "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Restore cancelled."
    exit 0
fi

# Decompress if needed
if [[ "$BACKUP_FILE" == *.gz ]]; then
    echo "Decompressing backup..."
    TEMP_FILE="${BACKUP_FILE%.gz}"
    gunzip -c "$BACKUP_FILE" > "$TEMP_FILE"
    RESTORE_FILE="$TEMP_FILE"
else
    RESTORE_FILE="$BACKUP_FILE"
fi

# Check if running in Docker
if [ -f /.dockerenv ] || [ -n "$DOCKER_CONTAINER" ]; then
    echo "Running inside Docker container..."
    
    if [ -n "$POSTGRES_USER" ] && [ -n "$POSTGRES_PASSWORD" ] && [ -n "$POSTGRES_DB" ]; then
        # Drop and recreate database
        docker-compose exec -T db psql -U "$POSTGRES_USER" -c "DROP DATABASE IF EXISTS $POSTGRES_DB;"
        docker-compose exec -T db psql -U "$POSTGRES_USER" -c "CREATE DATABASE $POSTGRES_DB;"
        
        # Restore from backup
        cat "$RESTORE_FILE" | docker-compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB"
    else
        echo "Error: Database credentials not set in environment"
        exit 1
    fi
else
    # Running on host machine
    if [ -n "$DATABASE_URL" ]; then
        # Extract database name from DATABASE_URL
        DB_NAME=$(echo "$DATABASE_URL" | sed -n 's/.*\/\([^?]*\).*/\1/p')
        # Create new DATABASE_URL without database name for drop/create
        BASE_URL=$(echo "$DATABASE_URL" | sed 's/\/[^/]*$/\/postgres/')
        
        # Drop and recreate database
        psql "$BASE_URL" -c "DROP DATABASE IF EXISTS $DB_NAME;"
        psql "$BASE_URL" -c "CREATE DATABASE $DB_NAME;"
        
        # Restore from backup
        psql "$DATABASE_URL" < "$RESTORE_FILE"
    elif [ -n "$POSTGRES_USER" ] && [ -n "$POSTGRES_PASSWORD" ] && [ -n "$POSTGRES_DB" ]; then
        PGHOST="${DB_HOST:-localhost}"
        PGPORT="${DB_PORT:-5432}"
        export PGPASSWORD="$POSTGRES_PASSWORD"
        
        # Drop and recreate database
        psql -h "$PGHOST" -p "$PGPORT" -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS $POSTGRES_DB;"
        psql -h "$PGHOST" -p "$PGPORT" -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE $POSTGRES_DB;"
        
        # Restore from backup
        psql -h "$PGHOST" -p "$PGPORT" -U "$POSTGRES_USER" "$POSTGRES_DB" < "$RESTORE_FILE"
    else
        echo "Error: Database credentials not configured"
        exit 1
    fi
fi

# Clean up temporary file if we created one
if [ -n "$TEMP_FILE" ] && [ -f "$TEMP_FILE" ]; then
    rm "$TEMP_FILE"
fi

echo "Database restored successfully from: $BACKUP_FILE"
