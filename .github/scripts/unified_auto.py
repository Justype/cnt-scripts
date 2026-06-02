#!/usr/bin/env python3
"""
Unified auto-updater for build scripts.

Scans all build scripts for #AUTOUPDATE: headers, groups by source:identifier
to fetch each remote source only once, applies per-file >=min filters, then
rewrites #PL:key: lines.

Supported sources:
  github:{org}/{repo}           - GitHub release tags
  bioconda:{package}            - Anaconda API (bioconda channel)
  conda-forge:{package}         - Anaconda API (conda-forge channel)
  docker:{image}:{tag_filter}   - Docker Hub tags filtered by a suffix

Header format:
  #AUTOUPDATE:{pl_key}:{source}:{identifier}[>={min}][<{max}|<={max}]

Examples:
  #AUTOUPDATE:cytoscape_version:github:cytoscape/cytoscape>=3.9.0
  #AUTOUPDATE:star_version:bioconda:star>=2.7.0b
  #AUTOUPDATE:version:conda-forge:r-base>=4.0.0
  #AUTOUPDATE:version:docker:posit/r-base:^(\d+\.\d+\.\d+)-noble(?:-[^-]+)?$>=4.0.0
  #AUTOUPDATE:openjdk:bioconda:openjdk>=17<18

Output tags (stdout):
  [UPDATED] file: #PL:key delta   - file was modified
  [INFO]    context: summary      - useful info when no change
Errors go to stderr.
"""

import json
import os
import re
import ssl
import sys
import urllib.request
from collections import defaultdict

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

SCRIPTS_DIR       = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT         = os.path.dirname(os.path.dirname(SCRIPTS_DIR))
BUILD_SCRIPTS_DIR = os.path.join(REPO_ROOT, "build-scripts")
HELPERS_DIR       = os.path.join(REPO_ROOT, "helpers")


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def _parse_semver(v: str):
    """Parse X[.Y[.Z[.W]]][a-z] into a sortable tuple, or None."""
    m = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?([a-z]?)$", v)
    if not m:
        return None
    parts = [int(m.group(i)) if m.group(i) else 0 for i in range(1, 5)]
    return (parts[0], parts[1], parts[2], parts[3], m.group(5) or "")


def _versions_to_pl_value(versions: list) -> str:
    """Encode sorted version list as a range string if contiguous integers, else CSV."""
    try:
        ints = [int(v) for v in versions]
        if ints == list(range(ints[0], ints[-1] + 1)):
            return f"{ints[0]}-{ints[-1]}"
    except ValueError:
        pass
    return ",".join(versions)


def _pl_delta(old_val: str, new_val: str) -> str:
    """Concise delta string for a #PL: value change."""
    old_val, new_val = old_val.strip(), new_val.strip()
    if re.match(r"^\d+-\d+$", old_val) and re.match(r"^\d+-\d+$", new_val):
        return f"{old_val} → {new_val}"
    old_set = {v.strip() for v in old_val.split(",") if v.strip()}
    new_set = {v.strip() for v in new_val.split(",") if v.strip()}
    added   = new_set - old_set
    removed = old_set - new_set

    def _key(v):
        m = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?([a-z]?)$", v)
        return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0), m.group(4) or "") if m else (0, 0, 0, v)

    parts = []
    if added:   parts.append("+" + ",".join(sorted(added,   key=_key)))
    if removed: parts.append("-" + ",".join(sorted(removed, key=_key)))
    return " ".join(parts) if parts else new_val


def _update_pl_key(pl_file: str, key: str, pl_value: str) -> bool:
    """Rewrite #PL:{key}: line in pl_file. Returns True if changed."""
    prefix   = f"#PL:{key}:"
    new_line = f"{prefix}{pl_value}\n"
    with open(pl_file) as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            old_val = line[len(prefix):].rstrip("\n")
            if lines[i] == new_line:
                return False
            lines[i] = new_line
            break
    else:
        print(f"Warning: no {prefix} line in {pl_file}.", file=sys.stderr)
        return False
    with open(pl_file, "w") as f:
        f.writelines(lines)
    rel = os.path.relpath(pl_file, REPO_ROOT)
    print(f"[UPDATED] {rel}: #PL:{key} {_pl_delta(old_val, pl_value)}")
    return True


# ---------------------------------------------------------------------------
# Source classes
# ---------------------------------------------------------------------------

class GitHubSource:
    def __init__(self, repo: str):
        self.repo = repo

    def fetch_versions(self) -> list:
        versions, page = [], 1
        while True:
            url = f"https://api.github.com/repos/{self.repo}/releases?per_page=100&page={page}"
            try:
                req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                    data = json.load(resp)
            except Exception as e:
                print(f"Warning: GitHub API error ({self.repo}): {e}", file=sys.stderr)
                break
            if not data:
                break
            for r in data:
                tag = r.get("tag_name", "")
                if _parse_semver(tag) is not None:
                    versions.append(tag)
            if len(data) < 100:
                break
            page += 1
        versions.sort(key=lambda v: _parse_semver(v) or (0,))
        return versions


class AnacondaSource:
    def __init__(self, channel: str, package: str):
        self.channel = channel
        self.package = package

    def fetch_versions(self) -> list:
        url = f"https://api.anaconda.org/package/{self.channel}/{self.package}"
        try:
            with urllib.request.urlopen(url, timeout=15, context=_SSL_CTX) as resp:
                data = json.load(resp)
        except Exception as e:
            print(f"Warning: Anaconda API error ({self.channel}/{self.package}): {e}", file=sys.stderr)
            return []
        parsed = [(k, v) for v in data.get("versions", []) if (k := _parse_semver(v)) is not None]
        return [v for _, v in sorted(parsed)]


class DockerSource:
    def __init__(self, image: str, tag_pattern: str):
        self.image   = image
        self.pattern = re.compile(tag_pattern)

    def fetch_versions(self) -> list:
        tags, url = [], f"https://hub.docker.com/v2/repositories/{self.image}/tags?page_size=100"
        while url:
            try:
                with urllib.request.urlopen(url, timeout=15, context=_SSL_CTX) as resp:
                    data = json.load(resp)
            except Exception as e:
                print(f"Warning: Docker Hub API error ({self.image}): {e}", file=sys.stderr)
                break
            tags.extend(e.get("name", "") for e in data.get("results", []))
            url = data.get("next")

        versions = {m.group(1) for t in tags if (m := self.pattern.match(t))}
        return sorted(versions, key=lambda v: tuple(int(x) for x in v.split(".")))


def _make_source(source_type: str, identifier: str):
    if source_type == "github":
        return GitHubSource(repo=identifier)
    if source_type in ("bioconda", "conda-forge"):
        return AnacondaSource(channel=source_type, package=identifier)
    if source_type == "docker":
        image, _, tag_pattern = identifier.partition(":")
        if not tag_pattern:
            raise ValueError(f"docker identifier must be 'image:tag_pattern', got: {identifier!r}")
        return DockerSource(image=image, tag_pattern=tag_pattern)
    raise ValueError(f"Unknown source type: {source_type!r}")


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

_AU_RE = re.compile(r"^#AUTOUPDATE:([^:]+):([^:]+):(.+)$")


def _parse_autoupdate(line: str):
    """Return (pl_key, source_type, identifier, min_str, max_str, max_inclusive) or None.

    Format: #AUTOUPDATE:{key}:{source}:{identifier}[>={min}][<{max}|<={max}]
    """
    m = _AU_RE.match(line.rstrip())
    if not m:
        return None
    pl_key, source_type, rest = m.group(1), m.group(2), m.group(3)
    min_str = ""
    max_str = ""
    max_inclusive = False

    # Extract <=max or <max from end (check <= before < to avoid partial match)
    lte = re.search(r'<=([^<>=]+)$', rest)
    lt  = re.search(r'<([^<>=]+)$',  rest) if not lte else None
    if lte:
        max_str, max_inclusive = lte.group(1), True
        rest = rest[:lte.start()]
    elif lt:
        max_str, max_inclusive = lt.group(1), False
        rest = rest[:lt.start()]

    # Extract >=min from end
    ge = re.search(r'>=([^<>=]+)$', rest)
    if ge:
        min_str = ge.group(1)
        rest    = rest[:ge.start()]

    return pl_key, source_type, rest, min_str, max_str, max_inclusive


def _update_dep_key(pl_file: str, package: str, new_version: str) -> bool:
    """Rewrite #DEP:{package}/X.Y.Z[>=min] with new_version, preserving constraint."""
    prefix = f"#DEP:{package}/"
    with open(pl_file) as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            rest = line[len(prefix):].rstrip("\n")
            constraint = ""
            for op in (">=", ">"):
                idx = rest.find(op)
                if idx >= 0:
                    constraint = rest[idx:]
                    break
            old_version = rest[:len(rest) - len(constraint)]
            new_line = f"{prefix}{new_version}{constraint}\n"
            if lines[i] == new_line:
                return False
            lines[i] = new_line
            break
    else:
        print(f"Warning: no {prefix} line in {pl_file}.", file=sys.stderr)
        return False
    with open(pl_file, "w") as f:
        f.writelines(lines)
    rel = os.path.relpath(pl_file, REPO_ROOT)
    print(f"[UPDATED] {rel}: #DEP:{package} {old_version} → {new_version}{constraint}")
    return True


def _update_value_key(pl_file: str, key: str, pl_value: str) -> bool:
    """Rewrite #VALUE: {key}= line in a helper script. Returns True if changed."""
    prefix   = f"#VALUE: {key}="
    new_line = f"{prefix}{pl_value}\n"
    with open(pl_file) as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            old_val = line[len(prefix):].rstrip("\n")
            if lines[i] == new_line:
                return False
            lines[i] = new_line
            break
    else:
        print(f"Warning: no {prefix} line in {pl_file}.", file=sys.stderr)
        return False
    with open(pl_file, "w") as f:
        f.writelines(lines)
    rel = os.path.relpath(pl_file, REPO_ROOT)
    print(f"[UPDATED] {rel}: #VALUE: {key} {_pl_delta(old_val, pl_value)}")
    return True


def scan_scripts(dirs: list) -> list:
    """Walk dirs, return list of AUTOUPDATE entry dicts.
    helpers/  → target always 'value' (directory-based).
    build-scripts/ → target detected from file content: #PL: → 'pl', #DEP: → 'dep'.
    """
    entries = []
    for scan_dir in dirs:
        is_helpers = os.path.abspath(scan_dir) == os.path.abspath(HELPERS_DIR)
        for root, subdirs, files in os.walk(scan_dir):
            subdirs.sort()
            for filename in sorted(files):
                if filename.endswith((".py", ".sh", ".lua", ".md")):
                    continue
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                except OSError:
                    continue
                for line in content.splitlines():
                    if not line.startswith("#AUTOUPDATE:"):
                        continue
                    parsed = _parse_autoupdate(line)
                    if not parsed:
                        continue
                    pl_key, source_type, identifier, min_str, max_str, max_inclusive = parsed
                    if is_helpers:
                        target = "value"
                    elif f"#PL:{pl_key}:" in content:
                        target = "pl"
                    elif f"#DEP:{pl_key}/" in content:
                        target = "dep"
                    else:
                        print(f"Warning: #AUTOUPDATE:{pl_key} in {filepath} has no matching #PL: or #DEP: header.", file=sys.stderr)
                        continue
                    entries.append(dict(
                        file=filepath, pl_key=pl_key, target=target,
                        source_type=source_type, identifier=identifier,
                        min_str=min_str, max_str=max_str, max_inclusive=max_inclusive,
                    ))
    return entries


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(dirs: list = None):
    if dirs is None:
        dirs = [BUILD_SCRIPTS_DIR, HELPERS_DIR]
    entries = scan_scripts(dirs)
    if not entries:
        print("[INFO] No #AUTOUPDATE: headers found.")
        return

    # Group by (source_type, identifier) — one API call per unique source
    groups = defaultdict(list)
    for e in entries:
        groups[(e["source_type"], e["identifier"])].append(e)

    updated_files = set()

    for (source_type, identifier), group in sorted(groups.items()):
        label = f"{source_type}:{identifier}"
        try:
            source       = _make_source(source_type, identifier)
            all_versions = source.fetch_versions()
        except Exception as e:
            print(f"[ERROR] {label}: {e}", file=sys.stderr)
            continue

        if not all_versions:
            print(f"[INFO] {label}: no versions found", file=sys.stderr)
            continue

        print(f"[INFO] {label}: {len(all_versions)} versions ({all_versions[0]}–{all_versions[-1]})")

        for entry in group:
            versions = list(all_versions)
            min_str, max_str, max_inclusive = entry["min_str"], entry["max_str"], entry["max_inclusive"]

            if min_str:
                min_key  = _parse_semver(min_str) or (0,)
                versions = [v for v in versions if (_parse_semver(v) or (0,)) >= min_key]
            if max_str:
                max_key = _parse_semver(max_str) or (0,)
                if max_inclusive:
                    versions = [v for v in versions if (_parse_semver(v) or (0,)) <= max_key]
                else:
                    versions = [v for v in versions if (_parse_semver(v) or (0,)) < max_key]

            if not versions:
                bounds = f">={min_str}" if min_str else ""
                bounds += f"{'<=' if max_inclusive else '<'}{max_str}" if max_str else ""
                print(f"[INFO] {label}: no versions {bounds} for {os.path.relpath(entry['file'], REPO_ROOT)}", file=sys.stderr)
                continue

            target = entry["target"]
            if target == "dep":
                changed = _update_dep_key(entry["file"], entry["pl_key"], versions[-1])
            elif target == "value":
                changed = _update_value_key(entry["file"], entry["pl_key"], _versions_to_pl_value(list(reversed(versions))))
            else:
                changed = _update_pl_key(entry["file"], entry["pl_key"], _versions_to_pl_value(versions))

            if changed:
                updated_files.add(os.path.relpath(entry["file"], REPO_ROOT))

    if updated_files:
        print(f"\n[SUMMARY] {len(updated_files)} file(s) updated:")
        for path in sorted(updated_files):
            print(f"  {path}")


if __name__ == "__main__":
    run()
