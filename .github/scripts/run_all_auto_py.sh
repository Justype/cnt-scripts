#!/bin/bash
# Run all auto.py scripts under build-scripts/ and helpers/
set -e

# Run unified auto-updater first (handles #AUTOUPDATE: headers across all scripts)
UNIFIED="$(dirname "$0")/unified_auto.py"
echo "Running unified auto-updater..."
python3 "$UNIFIED"

# Run per-directory auto.py scripts (for specialized sources not covered by unified)
find "$(dirname "$0")/../../build-scripts" -type f -name 'auto.py' | while read -r script; do
    echo "Running $script..."
    python3 "$script"
done

# Update helper .Rprofile Bioconductor/CRAN mapping tables
HELPERS_AUTO="$(dirname "$0")/../../helpers/auto.py"
if [ -f "$HELPERS_AUTO" ]; then
    echo "Running $HELPERS_AUTO..."
    python3 "$HELPERS_AUTO"
fi
