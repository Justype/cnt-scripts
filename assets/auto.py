#!/usr/bin/env python3
"""
Template for auto.py scripts that update build script metadata.

Core helpers:
  _update_dep_version  - rewrite #DEP:{package}/X.Y.Z[>=min] with a new version
  _update_pl_key       - rewrite a #PL:{key}: line with a new value
  BiocondaVersions     - query all versions of a bioconda package
  LatestDepVersion     - update #DEP: lines to the latest bioconda release

Usage example:
  class SamtoolsLatestVersion(LatestDepVersion):
      PACKAGE = "samtools"
      DEP_FILES = ["transcript-gencode", "genome/gencode"]
      MIN_VERSION = (1, 0, 0)

  if __name__ == "__main__":
      SamtoolsLatestVersion().run()
"""

import json
import os
import re
import ssl
import sys
import urllib.request

SCRIPT_PATH = __file__
BASE_DIR = os.path.dirname(SCRIPT_PATH)

# Some HPC systems have SSL cert issues; remote sources are public read-only data.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _update_dep_version(dep_file: str, package: str, new_version: str) -> bool:
    """Rewrite a #DEP:{package}/X.Y.Z[>=min] line to use new_version, preserving any constraint suffix. Returns True if changed."""
    if not os.path.exists(dep_file):
        print(f"Error: {dep_file} not found.", file=sys.stderr)
        return False

    prefix = f"#DEP:{package}/"

    with open(dep_file) as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        if line.startswith(prefix):
            rest = line[len(prefix):].rstrip("\n")
            # Preserve any version constraint suffix (e.g. ">=1.10" or ">1.10")
            constraint = ""
            for op in (">=", ">"):
                idx = rest.find(op)
                if idx >= 0:
                    constraint = rest[idx:]
                    break
            new_line = f"{prefix}{new_version}{constraint}\n"
            if lines[i] == new_line:
                print(f"No changes to {os.path.basename(dep_file)} #DEP:{package} (up to date).")
                return False
            lines[i] = new_line
            break
    else:
        print(f"Warning: no {prefix} line in {dep_file}.", file=sys.stderr)
        return False

    with open(dep_file, "w") as f:
        f.writelines(lines)
    print(f"Updated {os.path.basename(dep_file)} #DEP:{package} => {new_version}{constraint}")
    return True


def _update_pl_key(pl_file: str, key: str, pl_value: str) -> bool:
    """Rewrite a single #PL:{key}: line in pl_file. Returns True if changed."""
    if not os.path.exists(pl_file):
        print(f"Error: {pl_file} not found.", file=sys.stderr)
        return False

    prefix = f"#PL:{key}:"
    new_line = f"{prefix}{pl_value}\n"

    with open(pl_file) as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        if line.startswith(prefix):
            if lines[i] == new_line:
                print(f"No changes to {os.path.basename(pl_file)} #{key} (up to date).")
                return False
            lines[i] = new_line
            break
    else:
        print(f"Warning: no {prefix} line in {pl_file}.", file=sys.stderr)
        return False

    with open(pl_file, "w") as f:
        f.writelines(lines)
    print(f"Updated {os.path.basename(pl_file)} #{key} => {pl_value}")
    return True


class BiocondaVersions:
    """
    Query a bioconda package via the Anaconda API.

    Subclass and set PACKAGE and optionally MIN_VERSION.
    """

    PACKAGE = ""            # bioconda package name, e.g. "samtools"
    MIN_VERSION = (0, 0, 0) # minimum version tuple to include, e.g. (1, 10, 0)

    def _parse_version(self, v: str):
        """Parse version strings (e.g. '2.7.11b', '2.3', '1.21') into a sortable tuple."""
        m = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?([a-z]?)$", v)
        if not m:
            return None
        parts = [int(m.group(i)) if m.group(i) is not None else 0 for i in range(1, 5)]
        return (parts[0], parts[1], parts[2], parts[3], m.group(5))

    def query_versions(self) -> list:
        """Return ascending sorted list of version strings from bioconda."""
        try:
            url = f"https://api.anaconda.org/package/bioconda/{self.PACKAGE}"
            with urllib.request.urlopen(url, timeout=15, context=_SSL_CTX) as resp:
                data = json.load(resp)
        except Exception as e:
            print(f"Warning: failed to query Anaconda API for {self.PACKAGE}: {e}", file=sys.stderr)
            return []

        parsed = []
        for v in data.get("versions", []):
            key = self._parse_version(v)
            if key is not None and key[:3] >= self.MIN_VERSION:
                parsed.append((key, v))

        parsed.sort()
        return [v for _, v in parsed]


class LatestDepVersion(BiocondaVersions):
    """Update #DEP:{PACKAGE}/X.Y.Z[>=min] to the latest bioconda release in DEP_FILES."""

    DEP_FILES: list = []  # file paths relative to BASE_DIR

    def run(self):
        versions = self.query_versions()
        if not versions:
            print(f"No {self.PACKAGE} versions found; aborting.")
            return
        latest = versions[-1]
        print(f"Found {len(versions)} bioconda {self.PACKAGE} versions; latest: {latest}")
        for name in self.DEP_FILES:
            _update_dep_version(os.path.join(BASE_DIR, name), self.PACKAGE, latest)
