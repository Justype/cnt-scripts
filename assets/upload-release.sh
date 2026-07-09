#!/usr/bin/env bash
# Upload build artifacts to their matching GitHub releases.
# Release tag == directory name under build/ (e.g. build/ubuntu24/ → tag ubuntu24).
# Uploads .sif and .sqf files.
# Usage: ./upload-release.sh [--repo OWNER/REPO] [--dry-run]

set -euo pipefail

REPO="${REPO:-Justype/cnt-scripts}"
DRY_RUN=0

usage() {
    cat <<EOF
Usage: $(basename "$0") [--repo OWNER/REPO] [--dry-run]

Upload build artifacts to their matching GitHub releases.
Release tag == directory name under build/ (e.g. build/ubuntu24/ → tag ubuntu24).
Uploads .sif and .sqf files.

Options:
  -r, --repo OWNER/REPO  GitHub repository (default: $REPO)
  -d, --dry-run          Print gh commands without executing them
  -h, --help         Show this help message and exit
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -r|--repo)        REPO="$2"; shift 2 ;;
        -d|--dry-run)     DRY_RUN=1; shift ;;
        -h|--help)     usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 2 ;;
    esac
done

BUILD_DIR="build"

if [[ ! -d "$BUILD_DIR" ]]; then
    echo "ERROR: build/ not found at $BUILD_DIR"
    exit 1
fi

uploaded=0
declare -A tag_files

while IFS= read -r -d '' file; do
    rel="${file#"$BUILD_DIR/"}"
    tag="${rel%%/*}"
    [[ -z "$tag" ]] && continue
    tag_files["$tag"]+=" $file"
    uploaded=$((uploaded + 1))
done < <(find "$BUILD_DIR" -type f \( -name "*.sif" -o -name "*.sqf" \) -print0 | sort -z)

if [[ $uploaded -eq 0 ]]; then
    echo "No .sif/.sqf artifacts found under $BUILD_DIR"
    exit 1
fi

for tag in "${!tag_files[@]}"; do
    read -ra files <<< "${tag_files[$tag]}"
    echo "→ [$tag] ${files[*]##*/}"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  (dry-run) gh release upload $tag ${files[*]} --clobber -R $REPO"
    else
        gh release upload "$tag" "${files[@]}" --clobber -R "$REPO"
    fi
done

echo
echo "Done: $uploaded file(s) uploaded to $REPO"
