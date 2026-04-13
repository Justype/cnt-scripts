#!/usr/bin/env python3
"""
Update helpers after build-script auto.py runs:

  RVersions   - reads #PL:version: from build-scripts/ubuntu*/posit-r.def,
                rewrites AVAIL_R_VERSIONS in helpers/*/rstudio-server.

  BiocVersions - queries https://bioconductor.org/config.yaml,
                 rewrites bioc_to_p3m_date / bioc_to_r_local in helpers/*/.Rprofile.

Run from the repo root or from within helpers/:
    python3 helpers/auto.py
"""

import glob
import json
import os
import re
import ssl
import sys
import urllib.request


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEDULER_DIRS = ["headless", "slurm", "pbs", "lsf", "htcondor"]

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


# ---------------------------------------------------------------------------
# R versions  →  helpers/*/rstudio-server
# ---------------------------------------------------------------------------

class RVersions:
    """
    Collect available R versions from posit-r.def build scripts and
    rewrite AVAIL_R_VERSIONS in every rstudio-server helper.
    """

    # Only include R 4.x+ (posit-r images go back to 3.x but the
    # rstudio-server helper only needs modern versions).
    MIN_VERSION = (4, 0, 0)

    def read_versions(self) -> list:
        """Union of all #PL:version: entries across ubuntu*/posit-r.def, filtered and sorted."""
        pattern = os.path.join(SCRIPT_DIR, "..", "build-scripts", "ubuntu*", "posit-r.def")
        versions = set()
        for def_file in glob.glob(pattern):
            with open(def_file) as f:
                for line in f:
                    if line.startswith("#PL:version:"):
                        for v in line.split(":", 2)[2].strip().split(","):
                            v = v.strip()
                            if v:
                                versions.add(v)
        filtered = [v for v in versions if self._key(v) >= self.MIN_VERSION]
        return sorted(filtered, key=self._key)

    def _key(self, ver: str):
        parts = re.split(r"[.-]", ver)
        return tuple(int(x) for x in parts if x.isdigit())

    def run(self) -> list:
        """Returns sorted version list (ascending) for use by VersionsInCommon."""
        versions = self.read_versions()
        if not versions:
            print("[SKIP] RVersions: no R versions found in posit-r.def files", file=sys.stderr)
            return []
        print(f"[INFO] RVersions: {len(versions)} versions ({versions[0]}–{versions[-1]})")
        return versions


# ---------------------------------------------------------------------------
# Bioconductor versions + P3M snapshot dates  →  helpers/*/.Rprofile
# ---------------------------------------------------------------------------

class BiocVersions:
    """
    Fetch Bioconductor release info from bioconductor.org/config.yaml and
    rewrite bioc_to_p3m_date / bioc_to_r_local in every .Rprofile.

    The P3M CRAN snapshot for Bioc version N = release date of Bioc N+1
    (CRAN is frozen at the point the next Bioc cycle starts).
    """

    CONFIG_URL = "https://bioconductor.org/config.yaml"

    # P3M binary snapshots start around Bioc 3.5 (2017).
    MIN_VERSION = (3, 5)

    def _fetch(self) -> str:
        try:
            with urllib.request.urlopen(self.CONFIG_URL, timeout=15, context=_SSL_CTX) as resp:
                return resp.read().decode()
        except Exception as e:
            print(f"Error: failed to fetch {self.CONFIG_URL}: {e}", file=sys.stderr)
            sys.exit(1)

    def _parse_mapping(self, yaml_text: str, key: str) -> dict:
        """Extract a version→value block without a full YAML parser."""
        mapping = {}
        in_block = False
        entry_re = re.compile(
            r"""^\s+['\"]?(\d+\.\d+)['\"]?\s*:\s*['\"]?([^'\"#\n]+?)['\"]?\s*(?:#.*)?$"""
        )
        for line in yaml_text.splitlines():
            if re.match(rf"^{re.escape(key)}\s*:", line):
                in_block = True
                continue
            if in_block:
                if line and not line[0].isspace():
                    break
                m = entry_re.match(line)
                if m:
                    mapping[m.group(1)] = m.group(2).strip()
        return mapping

    def _parse_date(self, raw: str) -> str:
        """Convert M/D/YYYY or MM/DD/YYYY → YYYY-MM-DD."""
        parts = raw.strip().split("/")
        if len(parts) == 3:
            m, d, y = parts
            return f"{y}-{int(m):02d}-{int(d):02d}"
        raise ValueError(f"Unrecognised date format: {raw!r}")

    def _ver_key(self, ver: str):
        return tuple(int(x) for x in ver.split("."))

    def build_p3m_table(self, release_dates: dict) -> dict:
        versions = sorted(release_dates, key=self._ver_key)
        result = {}
        for i, ver in enumerate(versions[:-1]):
            if self._ver_key(ver) < self.MIN_VERSION:
                continue
            result[ver] = self._parse_date(release_dates[versions[i + 1]])
        return result

    def _format_table(self, mapping: dict) -> str:
        lines = []
        for ver in sorted(mapping, key=self._ver_key):
            lines.append(f'    "{ver}" = "{mapping[ver]}"')
        return ",\n".join(lines)

    def _update_rprofile(self, path: str, date_entries: str, r_entries: str) -> bool:
        if not os.path.exists(path):
            print(f"[SKIP] {path}: not found", file=sys.stderr)
            return False
        with open(path) as f:
            content = f.read()
        date_pat = re.compile(
            r"(bioc_to_p3m_date\s*<-\s*c\s*\(\s*\n)(.*?)(\n\s*\))", re.DOTALL)
        r_pat = re.compile(
            r"(bioc_to_r_local\s*<-\s*c\s*\(\s*\n)(.*?)(\n\s*\))", re.DOTALL)
        new_content = date_pat.sub(lambda m: m.group(1) + date_entries + m.group(3), content)
        new_content = r_pat.sub(lambda m: m.group(1) + r_entries + m.group(3), new_content)
        if new_content == content:
            print(f"[SKIP] {path}: up to date")
            return False
        with open(path, "w") as f:
            f.write(new_content)
        print(f"[UPDATED] {path}: bioc_to_p3m_date, bioc_to_r_local")
        return True

    def run(self):
        yaml_text = self._fetch()

        release_dates_raw = self._parse_mapping(yaml_text, "release_dates")
        bioc_to_r = self._parse_mapping(yaml_text, "r_ver_for_bioc_ver")

        if not release_dates_raw:
            print("[ERROR] BiocVersions: could not parse 'release_dates'", file=sys.stderr)
            sys.exit(1)
        if not bioc_to_r:
            print("[ERROR] BiocVersions: could not parse 'r_ver_for_bioc_ver'", file=sys.stderr)
            sys.exit(1)

        bioc_to_date = self.build_p3m_table(release_dates_raw)

        latest_bioc = max(bioc_to_date, key=self._ver_key)
        latest_r    = max(bioc_to_r,    key=self._ver_key)
        print(f"[INFO] BiocVersions: bioc_to_p3m_date {len(bioc_to_date)} entries "
              f"(latest: Bioc {latest_bioc} → {bioc_to_date[latest_bioc]})")
        print(f"[INFO] BiocVersions: bioc_to_r_local {len(bioc_to_r)} entries "
              f"(latest: Bioc {latest_r} → R {bioc_to_r[latest_r]})")

        date_entries = self._format_table(bioc_to_date)
        r_entries    = self._format_table(bioc_to_r)

        for d in SCHEDULER_DIRS:
            self._update_rprofile(
                os.path.join(SCRIPT_DIR, d, ".Rprofile"), date_entries, r_entries
            )


# ---------------------------------------------------------------------------
# Conda package versions  →  helpers/*/.common.sh
# ---------------------------------------------------------------------------

class CondaPackageVersions:
    """Base class for querying conda-forge package versions via Anaconda API."""

    PACKAGE = ""          # override in subclass
    MIN_VERSION = (0,)    # override in subclass

    API_URL = "https://api.anaconda.org/package/conda-forge/{package}"

    def _fetch_versions(self) -> list:
        url = self.API_URL.format(package=self.PACKAGE)
        try:
            with urllib.request.urlopen(url, timeout=15, context=_SSL_CTX) as resp:
                data = json.loads(resp.read().decode())
                return data.get("versions", [])
        except Exception as e:
            print(f"[WARN] {self.__class__.__name__}: failed to fetch {url}: {e}",
                  file=sys.stderr)
            return []

    def _ver_key(self, ver: str):
        parts = re.split(r"[.-]", ver)
        return tuple(int(x) for x in parts if x.isdigit())

    def filter_and_sort(self, versions: list) -> list:
        """Keep only X.Y.Z versions >= MIN_VERSION, deduplicated, descending."""
        seen = set()
        result = []
        for v in versions:
            if not re.fullmatch(r"\d+\.\d+\.\d+", v):
                continue
            if self._ver_key(v) < self.MIN_VERSION:
                continue
            if v not in seen:
                seen.add(v)
                result.append(v)
        return sorted(result, key=self._ver_key, reverse=True)

    def run(self) -> list:
        """Returns sorted version list (descending) for use by VersionsFile."""
        raise NotImplementedError


class CondaPythonVersions(CondaPackageVersions):
    """Collect available Python versions from conda-forge."""

    PACKAGE = "python"
    MIN_VERSION = (3, 9, 0)

    def run(self) -> list:
        versions = self.filter_and_sort(self._fetch_versions())
        if not versions:
            print("[WARN] CondaPythonVersions: no versions found", file=sys.stderr)
            return []
        return versions


class CondaRVersions(CondaPackageVersions):
    """Collect available R versions from conda-forge (r-base package)."""

    PACKAGE = "r-base"
    MIN_VERSION = (4, 0, 0)

    def run(self) -> list:
        versions = self.filter_and_sort(self._fetch_versions())
        if not versions:
            print("[WARN] CondaRVersions: no versions found", file=sys.stderr)
            return []
        return versions


# ---------------------------------------------------------------------------
# Write version variables into helpers/*/.common.sh
# ---------------------------------------------------------------------------

class VersionsInCommon:
    """
    Maintain POSIT_R_VERSIONS / CONDA_PYTHON_VERSIONS / CONDA_R_VERSIONS
    inline in each helpers/<scheduler>/.common.sh via regex replacement.

    All version lists are full X.Y.Z, space-separated, newest first.
    Pattern matched: VARNAME="..."  (single line, auto-updated sentinel)
    """

    def _ver_key(self, ver: str):
        parts = re.split(r"[.-]", ver)
        return tuple(int(x) for x in parts if x.isdigit())

    def _delta(self, old_val: str, new_val: str) -> str:
        """Return '+added -removed' string, or '' if unchanged."""
        old_set = set(old_val.split())
        new_set = set(new_val.split())
        added   = sorted(new_set - old_set, key=self._ver_key, reverse=True)
        removed = sorted(old_set - new_set, key=self._ver_key, reverse=True)
        parts = [f"+{v}" for v in added] + [f"-{v}" for v in removed]
        return " ".join(parts)

    def _update_var(self, content: str, var: str, new_val: str) -> tuple:
        """Replace VAR="..." line. Returns (new_content, old_val)."""
        pat = re.compile(rf'^({re.escape(var)}=")([^"]*)(")', re.MULTILINE)
        m = pat.search(content)
        old_val = m.group(2) if m else ""
        new_content = pat.sub(lambda _: f'{var}="{new_val}"', content)
        return new_content, old_val

    def update(self, posit_r: list, conda_python: list, conda_r: list):
        """Rewrite version variables in all scheduler .common.sh files."""
        posit_val  = " ".join(reversed(posit_r))   # read_versions returns ascending
        python_val = " ".join(conda_python)
        r_val      = " ".join(conda_r)

        new_vals = {
            "POSIT_R_VERSIONS":      posit_val,
            "CONDA_PYTHON_VERSIONS": python_val,
            "CONDA_R_VERSIONS":      r_val,
        }

        for d in SCHEDULER_DIRS:
            path = os.path.join(SCRIPT_DIR, d, ".common.sh")
            if not os.path.exists(path):
                continue
            with open(path) as f:
                content = f.read()

            updated_vars = []
            for var, val in new_vals.items():
                content, old_val = self._update_var(content, var, val)
                delta = self._delta(old_val, val)
                if delta:
                    updated_vars.append(f"{var} {delta}")

            if updated_vars:
                with open(path, "w") as f:
                    f.write(content)
                for msg in updated_vars:
                    print(f"[UPDATED] {os.path.relpath(path, SCRIPT_DIR)}: {msg}")
            # Silent if up to date


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    posit_r_versions = RVersions().run()
    BiocVersions().run()
    conda_python = CondaPythonVersions().run()
    conda_r      = CondaRVersions().run()
    if posit_r_versions or conda_python or conda_r:
        VersionsInCommon().update(posit_r_versions, conda_python, conda_r)
