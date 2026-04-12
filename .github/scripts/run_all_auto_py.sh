#!/bin/bash
# Run all auto.py scripts under build-scripts/ and helpers/
set -e

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
