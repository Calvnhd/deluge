#!/bin/bash

# Sync SAMPLES folder to another local folder
#
# Uses rsync to mirror source → destination:
#   -a (archive): preserves permissions, timestamps, symlinks, recursive
#   -v (verbose): shows files being transferred
#   --delete: removes destination files not in source
#   --include/--exclude: only sync .WAV files
#
# rsync compares size + modification time (not contents) to decide what to sync.
# Source path is validated to prevent accidental deletion of backup.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

# Load config
if [[ -f "$ENV_FILE" ]]; then
    source "$ENV_FILE"
else
    echo "Error: .env file not found at $ENV_FILE"
    echo "Copy .env.example to .env and configure your paths."
    exit 1
fi

# Validate paths
if [[ -z "$SAMPLES_SOURCE" || -z "$SAMPLES_BACKUP" ]]; then
    echo "Error: SAMPLES_SOURCE and SAMPLES_BACKUP must be set in .env"
    exit 1
fi

if [[ ! -d "$SAMPLES_SOURCE" ]]; then
    echo "Error: Source directory does not exist: $SAMPLES_SOURCE"
    exit 1
fi

# SAFETY CHECK: Ensure source has .wav files before syncing
# This prevents accidental deletion of backup if source is empty/wrong
WAV_COUNT=$(find "$SAMPLES_SOURCE" -type f -iname "*.wav" 2>/dev/null | head -1)
if [[ -z "$WAV_COUNT" ]]; then
    echo "Error: No .wav files found in source directory: $SAMPLES_SOURCE"
    echo "This safety check prevents accidental deletion of your backup."
    echo "Please verify SAMPLES_SOURCE is correct in .env"
    exit 1
fi

# Create backup directory if it doesn't exist
mkdir -p "$SAMPLES_BACKUP"

# SAFETY CHECK: If backup exists and has files, require confirmation for --delete
BACKUP_FILE_COUNT=$(find "$SAMPLES_BACKUP" -type f -iname "*.wav" 2>/dev/null | wc -l)
if [[ "$BACKUP_FILE_COUNT" -gt 0 ]]; then
    echo "Backup destination contains $BACKUP_FILE_COUNT .wav files."
    echo "Files not in source will be DELETED from backup."
    read -p "Continue? (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

echo "Syncing SAMPLES..."
echo "  From: $SAMPLES_SOURCE"
echo "  To:   $SAMPLES_BACKUP"
echo ""

# Check for non-WAV files
NON_WAV=$(find "$SAMPLES_SOURCE" -type f ! -iname "*.wav" 2>/dev/null)
if [[ -n "$NON_WAV" ]]; then
    echo "Warning: Non-WAV files found in source (will not be synced):"
    echo "$NON_WAV" | head -10
    COUNT=$(echo "$NON_WAV" | wc -l)
    if [[ $COUNT -gt 10 ]]; then
        echo "  ... and $((COUNT - 10)) more"
    fi
    echo ""
fi

# Sync only .WAV files
rsync -av --delete --delete-excluded \
    --include='*/' \
    --include='*.wav' \
    --include='*.WAV' \
    --exclude='*' \
    "$SAMPLES_SOURCE" "$SAMPLES_BACKUP"

echo ""
echo "Sync complete!"
