#!/usr/bin/env python3
"""
Scan `build-scripts/` and generate `metadata/build-scripts.json` (and a
gzip companion) with template-aware entries.

Two types of entries are emitted:

Non-PL scripts (no #PL: headers):
    "ubuntu24/igv" -> {"path": "ubuntu24/igv.def", "whatis": "...", "deps": [...]}

PL template scripts (#PL: headers present):
    Template entry keyed by the script's relative path:
        "ubuntu24/posit-r" -> {"path": "...", "is_template": true,
                               "target_template": "...", "pl": {...}, ...}
    One expanded entry per Cartesian-product combination:
        "ubuntu24/r4.5.3" -> {"path": "ubuntu24/posit-r.def",
                               "pl": {"version": ["4.5.3"]}, ...}
"""
import gzip
import json
import os
import re

REPO = os.getcwd()
BUILD_SCRIPTS_DIR = os.path.join(REPO, "build-scripts")
OUT_DIR = os.path.join(REPO, "metadata")
OUT_FILE = os.path.join(OUT_DIR, "build-scripts.json")


# ---------------------------------------------------------------------------
# Value parsing helpers
# ---------------------------------------------------------------------------

def _natural_key(s: str):
    return [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", s)]


def sort_desc(values: list) -> list:
    return sorted(values, key=_natural_key, reverse=True)


def parse_pl_values(raw: str):
    """
    Parse the value string after the second ':' of a #PL: line.
    Returns (sorted_desc_concrete_values, is_open).
    The returned list has all concrete values sorted descending;
    if open_ended, "*" is appended as the last element.
    """
    tokens = [t.strip() for t in raw.split(",")]
    open_ended = "*" in tokens
    tokens = [t for t in tokens if t != "*"]

    concrete = []
    seen = set()
    range_re = re.compile(r"^(\d+)-(\d+)$")

    for tok in tokens:
        if not tok:
            continue
        m = range_re.fullmatch(tok)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            for v in range(min(a, b), max(a, b) + 1):
                s = str(v)
                if s not in seen:
                    concrete.append(s)
                    seen.add(s)
        else:
            if tok not in seen:
                concrete.append(tok)
                seen.add(tok)

    concrete = sort_desc(concrete)
    if open_ended:
        concrete.append("*")
    return concrete, open_ended


# ---------------------------------------------------------------------------
# Script header parsing
# ---------------------------------------------------------------------------

def parse_headers(path: str) -> dict:
    """Parse all relevant metadata headers from a build script."""
    pl_defs = []
    pl_seen = set()
    target = ""
    whatis = ""
    deps = []

    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.rstrip("\n")

                if line.startswith("#PL:"):
                    rest = line[4:]
                    idx = rest.find(":")
                    if idx < 0:
                        continue
                    name = rest[:idx].strip()
                    raw = rest[idx + 1:]
                    hash_idx = raw.find("#")
                    if hash_idx >= 0:
                        raw = raw[:hash_idx]
                    raw = raw.strip()
                    if not name or name in pl_seen:
                        continue
                    values, is_open = parse_pl_values(raw)
                    if values or is_open:
                        pl_defs.append((name, values, is_open))
                        pl_seen.add(name)

                elif line.startswith("#TARGET:"):
                    if not target:
                        target = line[8:].strip()

                elif line.startswith("#WHATIS:"):
                    if not whatis:
                        whatis = line[8:].strip()

                elif line.startswith("#DEP:"):
                    dep = line[5:]
                    hash_idx = dep.find("#")
                    if hash_idx >= 0:
                        dep = dep[:hash_idx]
                    dep = dep.strip()
                    if dep:
                        deps.append(dep)

    except OSError:
        pass

    return {"pl_defs": pl_defs, "target": target, "whatis": whatis, "deps": deps}


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

metadata = {}

if not os.path.isdir(BUILD_SCRIPTS_DIR):
    print("No build-scripts directory found; writing empty metadata file.")

for root, _, files in os.walk(BUILD_SCRIPTS_DIR):
    for filename in files:
        if filename.endswith((".py", ".sh")):
            continue

        full_path = os.path.join(root, filename)

        if "template" in full_path:
            continue

        rel = os.path.relpath(full_path, BUILD_SCRIPTS_DIR)
        is_def = rel.endswith(".def")
        rel_key = rel[:-4] if is_def else rel  # strip .def from key

        if rel_key.startswith(("base_image", "base-overlay")):
            continue

        headers = parse_headers(full_path)

        if headers["pl_defs"]:
            # ---- PL template script ----
            # Only store the template entry; condatainer expands combinations at runtime.
            target = headers["target"]
            if not target:
                print(f"  WARNING: {rel_key} has #PL: but no #TARGET: — skipping")
                if rel_key not in metadata:
                    metadata[rel_key] = {
                        "path": rel,
                        "whatis": headers["whatis"] or "Missing description",
                        "deps": headers["deps"],
                    }
                continue

            pl_defs = headers["pl_defs"]
            if rel_key not in metadata:
                metadata[rel_key] = {
                    "path": rel,
                    "is_template": True,
                    "target_template": target,
                    "whatis": headers["whatis"],
                    "pl": {name: values for name, values, _ in pl_defs},
                    "pl_order": [name for name, _, _ in pl_defs],
                    "deps": headers["deps"],
                }

        else:
            # ---- Regular (non-PL) script ----
            if rel_key not in metadata:
                metadata[rel_key] = {
                    "path": rel,
                    "whatis": headers["whatis"] or "Missing description",
                    "deps": headers["deps"],
                }

# Write output
os.makedirs(OUT_DIR, exist_ok=True)

with open(OUT_FILE, "w") as f:
    json.dump(metadata, f, indent=2, sort_keys=True)

with gzip.open(OUT_FILE + ".gz", "wt") as f:
    json.dump(metadata, f, indent=2, sort_keys=True)

template_count = sum(1 for v in metadata.values() if v.get("is_template"))
plain_count = len(metadata) - template_count
print(
    f"Wrote {len(metadata)} entries to {OUT_FILE} "
    f"({plain_count} plain, {template_count} templates)"
)
