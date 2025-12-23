#!/bin/bash

# Back up entire Deluge SD card contents to a .zip file
#
# Creates a complete archive of the SD card for cloud backup.
# This is the FIRST point of backup - captures everything before selective sync to the repository.
#
# Safety guarantees:
#   - Read-only access to SD card (zip reads, never writes)
#   - Creates new file at destination (never modifies existing backups without confirmation)
#   - Validates paths before any operations
#   - Only includes .xml and .wav files (warns about any other files found)
#
# Output: deluge-backup-YYYY-MM-DD.zip in the configured backup destination
# Logs:   Appends execution summary to logs/scripts.log

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$REPO_DIR/logs/scripts.log"
ENV_FILE="$SCRIPT_DIR/.env"

# Track start time for elapsed calculation
START_TIME=$(date +%s)
START_TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

# Load config
if [[ -f "$ENV_FILE" ]]; then
    source "$ENV_FILE"
else
    echo "Error: .env file not found at $ENV_FILE"
    echo "Copy .env.example to .env and configure your paths."
    exit 1
fi

# Validate required environment variables
if [[ -z "$SD_CARD_PATH" ]]; then
    echo "Error: SD_CARD_PATH must be set in .env"
    echo "Example: SD_CARD_PATH=\"/media/\$USER/DELUGE\""
    exit 1
fi

if [[ -z "$ZIP_BACKUP_PATH" ]]; then
    echo "Error: ZIP_BACKUP_PATH must be set in .env"
    echo "Example: ZIP_BACKUP_PATH=\"/mnt/c/Users/YourName/OneDrive/Deluge-Backup/\""
    exit 1
fi

# Validate SD card is mounted and accessible
if [[ ! -d "$SD_CARD_PATH" ]]; then
    echo "Error: SD card not found at: $SD_CARD_PATH"
    echo "Please insert the Deluge SD card and verify the mount path."
    exit 1
fi

# Check for expected Deluge folder structure
if [[ ! -d "$SD_CARD_PATH/SAMPLES" && ! -d "$SD_CARD_PATH/KITS" && ! -d "$SD_CARD_PATH/SONGS" && ! -d "$SD_CARD_PATH/SYNTHS" ]]; then
    echo "Error: SD card at $SD_CARD_PATH doesn't look like a Deluge card."
    echo "Expected folders: SAMPLES/, KITS/, SONGS/, SYNTHS/"
    exit 1
fi

# Create backup directory if needed
mkdir -p "$ZIP_BACKUP_PATH"

# Generate dated filename
DATE_STAMP=$(date +%Y-%m-%d)
ZIP_FILENAME="deluge-backup-${DATE_STAMP}.zip"
ZIP_FULLPATH="$ZIP_BACKUP_PATH/$ZIP_FILENAME"

# Check if backup already exists for today
if [[ -f "$ZIP_FULLPATH" ]]; then
    EXISTING_SIZE=$(du -h "$ZIP_FULLPATH" | cut -f1)
    echo "Warning: Backup already exists for today:"
    echo "  $ZIP_FULLPATH ($EXISTING_SIZE)"
    read -p "Overwrite? (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Aborted. Existing backup preserved."
        exit 0
    fi
    rm "$ZIP_FULLPATH"
fi

# Check available disk space at destination
SD_SIZE=$(du -sm "$SD_CARD_PATH" 2>/dev/null | cut -f1)
DEST_FREE=$(df -m "$ZIP_BACKUP_PATH" 2>/dev/null | tail -1 | awk '{print $4}')

if [[ -n "$SD_SIZE" && -n "$DEST_FREE" ]]; then
    # Compressed size is usually smaller, but check we have at least the raw size
    if [[ "$DEST_FREE" -lt "$SD_SIZE" ]]; then
        echo "Warning: Destination may not have enough space."
        echo "  SD card size: ${SD_SIZE}MB"
        echo "  Destination free: ${DEST_FREE}MB"
        read -p "Continue anyway? (y/N): " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            echo "Aborted."
            exit 1
        fi
    fi
fi

# Check for unexpected file types (not .xml or .wav)
echo "Scanning for unexpected file types..."
EXCLUDED_FILES=$(find "$SD_CARD_PATH" -type f \
    ! -iname "*.xml" \
    ! -iname "*.wav" \
    2>/dev/null || true)
EXCLUDED_COUNT=0

if [[ -n "$EXCLUDED_FILES" ]]; then
    EXCLUDED_COUNT=$(echo "$EXCLUDED_FILES" | wc -l)
    echo ""
    echo "⚠ WARNING: Found $EXCLUDED_COUNT file(s) with unexpected extensions (will NOT be backed up):"
    echo "$EXCLUDED_FILES" | head -20
    if [[ $EXCLUDED_COUNT -gt 20 ]]; then
        echo "  ... and $((EXCLUDED_COUNT - 20)) more"
    fi
    echo ""
fi

echo "=========================================="
echo "Deluge SD Card Backup"
echo "=========================================="
echo "Source:      $SD_CARD_PATH"
echo "Destination: $ZIP_FULLPATH"
if [[ -n "$SD_SIZE" ]]; then
    echo "SD Size:     ~${SD_SIZE}MB (will be compressed)"
fi
echo ""

# Create the zip archive
# -r: recursive
# -i: include only matching patterns
# We cd into the SD card so paths in zip are relative
echo "Creating backup archive..."
echo "(This may take several minutes for large sample libraries)"
echo ""

cd "$SD_CARD_PATH"
zip -r "$ZIP_FULLPATH" . -i "*.xml" "*.XML" "*.wav" "*.WAV"

# Verify the archive
echo ""
echo "Verifying archive integrity..."
if zip -T "$ZIP_FULLPATH" > /dev/null 2>&1; then
    echo "✓ Archive verified successfully"
    BACKUP_STATUS="SUCCESS"
    ERROR_MSG=""
else
    echo "✗ Archive verification FAILED!"
    echo "  The backup may be corrupted. Please try again."
    BACKUP_STATUS="FAILED"
    ERROR_MSG="Archive verification failed"
fi

# Calculate elapsed time
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
ELAPSED_FMT=$(printf '%dm %ds' $((ELAPSED / 60)) $((ELAPSED % 60)))

# Report results
ZIP_SIZE=$(du -h "$ZIP_FULLPATH" 2>/dev/null | cut -f1 || echo "N/A")
FILE_COUNT=$(unzip -l "$ZIP_FULLPATH" 2>/dev/null | tail -1 | awk '{print $2}' || echo "0")

echo ""
echo "=========================================="
echo "Backup complete!"
echo "=========================================="
echo "Archive:     $ZIP_FILENAME"
echo "Size:        $ZIP_SIZE"
echo "Files:       $FILE_COUNT"
echo "Excluded:    $EXCLUDED_COUNT"
echo "Elapsed:     $ELAPSED_FMT"
echo "Location:    $ZIP_FULLPATH"
echo ""

# Append results to log file
mkdir -p "$(dirname "$LOG_FILE")"
{
    echo "---"
    echo "script: sd-to-zip.sh"
    echo "timestamp: $START_TIMESTAMP"
    echo "status: $BACKUP_STATUS"
    echo "source: $SD_CARD_PATH"
    echo "destination: $ZIP_FULLPATH"
    echo "files_backed_up: $FILE_COUNT"
    echo "files_excluded: $EXCLUDED_COUNT"
    echo "archive_size: $ZIP_SIZE"
    echo "elapsed: $ELAPSED_FMT"
    if [[ -n "$ERROR_MSG" ]]; then
        echo "error: $ERROR_MSG"
    fi
} >> "$LOG_FILE"

# Exit with error if backup failed
if [[ "$BACKUP_STATUS" == "FAILED" ]]; then
    exit 1
fi
