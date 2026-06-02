#!/usr/bin/env python3
"""
Update helpers after unified_auto.py runs:

  BiocVersions - queries https://bioconductor.org/config.yaml,
                 rewrites bioc_to_p3m_date / bioc_to_r_local in helpers/*/.Rprofile.

CONDA_* and POSIT_R values are handled by unified_auto.py via #AUTOUPDATE: headers.

Run from the repo root or from within helpers/:
    python3 helpers/auto.py
"""

import os
import re
import ssl
import sys
import urllib.request


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


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

        self._update_rprofile(
            os.path.join(SCRIPT_DIR, ".Rprofile"), date_entries, r_entries
        )


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    BiocVersions().run()
