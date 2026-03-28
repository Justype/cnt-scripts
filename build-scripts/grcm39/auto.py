#!/usr/bin/env python3
"""
Query remote sources to update grcm39/* build script files

- GENCODE releases (EBI FTP) => updates #PL:gencode_version: in:
    - gtf-gencode        (release M5+)
    - transcript-gencode (release M6+)
    - star-gencode       (synced from gtf-gencode)
    - salmon-gencode     (synced from transcript-gencode, M6+)
- bioconda packages (all versions) => updates #PL:*_version: in:
    - star-gencode, star-cellranger  (star_version)
    - salmon-gencode                 (salmon_version)
- bioconda packages (pin latest) => updates #DEP:*/ in:
    - transcript-gencode, genome/gencode  (samtools)
    python3 build-scripts/grcm39/auto.py  # to update all
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


def _versions_to_pl_value(versions: list) -> str:
    """Encode a sorted int list as a range string if contiguous, else comma-separated."""
    if versions == list(range(versions[0], versions[-1] + 1)):
        return f"{versions[0]}-{versions[-1]}"
    return ",".join(str(v) for v in versions)


def _update_dep_version(dep_file: str, package: str, new_version: str) -> bool:
    """Rewrite a #DEP:{package}/X.Y.Z line to use new_version. Returns True if changed."""
    if not os.path.exists(dep_file):
        print(f"Error: {dep_file} not found.", file=sys.stderr)
        return False

    prefix = f"#DEP:{package}/"
    new_line = f"{prefix}{new_version}\n"

    with open(dep_file) as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        if line.startswith(prefix):
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
    print(f"Updated {os.path.basename(dep_file)} #DEP:{package} => {new_version}")
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


class GencodeVersions:
    """
    Discover GENCODE mouse releases from EBI FTP and update:
      - gtf-gencode        #PL:gencode_version: (M5+, stored as integers 5,6,...)
      - transcript-gencode #PL:gencode_version: (M6+)
      - star-gencode       #PL:gencode_version: (synced from gtf-gencode)
      - salmon-gencode     #PL:gencode_version: (synced from transcript-gencode)

    Mouse GENCODE releases are named M5, M6, ..., M38.
    The #PL: lines store the integer part only (e.g. 5-38); scripts prepend
    'M' in their template strings (e.g. release_M{gencode_version}).
    """

    FTP_BASE = "https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_mouse/"

    def query_ftp_releases(self, min_version: int) -> list:
        """Return sorted int list of M-release numbers >= min_version from EBI FTP."""
        try:
            with urllib.request.urlopen(self.FTP_BASE, timeout=10, context=_SSL_CTX) as resp:
                txt = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"Warning: failed to query {self.FTP_BASE}: {e}", file=sys.stderr)
            return []

        # Find directories like release_M5/, release_M38/
        found = set(re.findall(r"release_M(\d+)[/\"'>]", txt))
        return sorted(int(v) for v in found if int(v) >= min_version)

    def run(self):
        gtf_versions = self.query_ftp_releases(min_version=5)
        if not gtf_versions:
            print("No GENCODE mouse releases found; aborting.")
            return

        transcript_versions = [v for v in gtf_versions if v >= 6]
        print(f"Found {len(gtf_versions)} GENCODE mouse versions: M{gtf_versions[0]}–M{gtf_versions[-1]}")

        gtf_pl = _versions_to_pl_value(gtf_versions)
        _update_pl_key(os.path.join(BASE_DIR, "gtf-gencode"), "gencode_version", gtf_pl)
        _update_pl_key(os.path.join(BASE_DIR, "star-gencode"), "gencode_version", gtf_pl)

        transcript_pl = _versions_to_pl_value(transcript_versions)
        _update_pl_key(os.path.join(BASE_DIR, "transcript-gencode"), "gencode_version", transcript_pl)
        _update_pl_key(os.path.join(BASE_DIR, "salmon-gencode"), "gencode_version", transcript_pl)


class BiocondaVersions:
    """
    Query a bioconda package via the Anaconda API and update a #PL: key
    in one or more template files.

    Subclass and set PACKAGE, PL_KEY, PL_FILES, and optionally MIN_VERSION.
    """

    PACKAGE = ""                 # bioconda package name, e.g. "star"
    PL_KEY = ""                  # placeholder key to update, e.g. "star_version"
    PL_FILES: list = []          # template file names relative to BASE_DIR
    MIN_VERSION = (0, 0, 0)      # minimum version tuple to include

    def _parse_version(self, v: str):
        """Parse version strings (e.g. '2.7.11b', '2.3', '2025b', '2.3.5.1') into a sortable tuple."""
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

    def run(self):
        versions = self.query_versions()
        if not versions:
            print(f"No {self.PACKAGE} versions found; aborting.")
            return

        print(f"Found {len(versions)} bioconda {self.PACKAGE} versions: {versions[0]}–{versions[-1]}")
        pl_value = ",".join(versions)
        for name in self.PL_FILES:
            _update_pl_key(os.path.join(BASE_DIR, name), self.PL_KEY, pl_value)


class StarVersions(BiocondaVersions):
    PACKAGE = "star"
    PL_KEY = "star_version"
    PL_FILES = ["star-gencode", "star-cellranger"]
    MIN_VERSION = (2, 7, 0)


class SalmonVersions(BiocondaVersions):
    PACKAGE = "salmon"
    PL_KEY = "salmon_version"
    PL_FILES = ["salmon-gencode"]
    MIN_VERSION = (1, 0, 0)


class LatestDepVersion(BiocondaVersions):
    """Update #DEP:{PACKAGE}/X.Y.Z to the latest bioconda release in DEP_FILES."""

    DEP_FILES: list = []

    def run(self):
        versions = self.query_versions()
        if not versions:
            print(f"No {self.PACKAGE} versions found; aborting.")
            return
        latest = versions[-1]
        print(f"Found {len(versions)} bioconda {self.PACKAGE} versions; latest: {latest}")
        for name in self.DEP_FILES:
            _update_dep_version(os.path.join(BASE_DIR, name), self.PACKAGE, latest)


class SamtoolsLatestVersion(LatestDepVersion):
    PACKAGE = "samtools"
    DEP_FILES = ["transcript-gencode", "genome/gencode"]
    MIN_VERSION = (1, 0, 0)


if __name__ == "__main__":
    GencodeVersions().run()
    StarVersions().run()
    SalmonVersions().run()
    SamtoolsLatestVersion().run()
