#!/usr/bin/env python3
"""
Query the Docker Hub to update ubuntu22/*.def files

- R related => query posit/r-base tags
    - For tags like 4.4.3-jammy-{arch} => updates #PL:version: in posit-r.def
    python3 build-scripts/ubuntu22/auto.py  # to update posit-r.def
"""

import json
import os
import re
import ssl
import sys
import urllib.request

# Some HPC systems have SSL cert issues; Docker Hub tags are public read-only data.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

SCRIPT_PATH = __file__
BASE_DIR = os.path.dirname(SCRIPT_PATH)

CODE_NAME = "jammy"

class RVersions:
    """Discover r-base versions and update posit-r.def placeholder list."""

    # expose the code name at class level as well for easy access
    CODE_NAME = CODE_NAME

    def __init__(self):
        self.base_dir = BASE_DIR
        self.pl_file = os.path.join(self.base_dir, "posit-r.def")

    def query_docker_tags(self, url):
        """Return all tag names from the Docker Hub API, following pagination."""
        tags = []
        while url:
            try:
                with urllib.request.urlopen(url, timeout=10, context=_SSL_CTX) as resp:
                    data = json.load(resp)
            except Exception as e:
                print(f"Warning: failed to query {url}: {e}", file=sys.stderr)
                break
            for entry in data.get("results", []):
                name = entry.get("name")
                if name:
                    tags.append(name)
            url = data.get("next")
        return tags

    def filter_versions(self, tag_list, pattern=None):
        """Extract semver versions from tags matching major.minor.patch-{CODE_NAME}[-arch]."""
        if pattern is None:
            pattern = rf"^(\d+\.\d+\.\d+)-{self.CODE_NAME}(?:-[^-]+)?$"
        regex = re.compile(pattern)
        vers = set()
        for t in tag_list:
            m = regex.match(t)
            if m:
                vers.add(m.group(1))

        def keyfn(v):
            return tuple(int(x) for x in v.split("."))

        return sorted(vers, key=keyfn)

    def update_pl_file(self, versions):
        """Rewrite the #PL:version: line in posit-r.def with the given version list."""
        if not os.path.exists(self.pl_file):
            print(f"Error: {self.pl_file} not found.", file=sys.stderr)
            return False

        with open(self.pl_file, "r") as f:
            lines = f.readlines()

        new_pl_line = "#PL:version:" + ",".join(versions) + "\n"
        for i, line in enumerate(lines):
            if line.startswith("#PL:version:"):
                if lines[i] == new_pl_line:
                    print(f"[SKIP] {os.path.basename(self.pl_file)}: versions up to date")
                    return True
                lines[i] = new_pl_line
                break
        else:
            print(f"Warning: no #PL:version: line found in {self.pl_file}.", file=sys.stderr)
            return False

        with open(self.pl_file, "w") as f:
            f.writelines(lines)

        print(f"[UPDATED] {os.path.basename(self.pl_file)}: {len(versions)} versions "
              f"({versions[0]}–{versions[-1]}).")
        return True

    def run(self):
        tags = self.query_docker_tags(
            "https://hub.docker.com/v2/repositories/posit/r-base/tags?page_size=100"
        )
        if not tags:
            print("[SKIP] posit/r-base: no tags retrieved")
            return

        versions = self.filter_versions(tags)
        if not versions:
            print(f"[SKIP] posit/r-base: no {self.CODE_NAME} versions found")
            return

        print(f"[INFO] posit/r-base ({self.CODE_NAME}): {len(versions)} versions ({versions[0]}–{versions[-1]})")
        self.update_pl_file(versions)


if __name__ == "__main__":
    RVersions().run()
