#!/usr/bin/env python3
"""
Query remote sources to update grch38_grcm39/* build script files

- GENCODE human releases (EBI FTP) => updates #PL:human_gencode_version: in:
    - gtf-gencode  (release 22+)
    - star-gencode (synced from gtf-gencode)
- GENCODE mouse releases (EBI FTP) => updates #PL:mouse_gencode_version: in:
    - gtf-gencode  (release M5+)
    - star-gencode (synced from gtf-gencode)
    python3 build-scripts/grch38_grcm39/auto.py  # to update all

#PL: and #DEP: bioconda/github updates are handled by unified_auto.py via #AUTOUPDATE: headers.
"""

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
                print(f"[SKIP] {os.path.basename(pl_file)}: #PL:{key} up to date")
                return False
            lines[i] = new_line
            break
    else:
        print(f"Warning: no {prefix} line in {pl_file}.", file=sys.stderr)
        return False

    with open(pl_file, "w") as f:
        f.writelines(lines)
    print(f"[UPDATED] {os.path.basename(pl_file)}: #PL:{key} => {pl_value}")
    return True


class GencodeVersions:
    """
    Discover GENCODE human + mouse releases from EBI FTP and update:
      - gtf-gencode  #PL:human_gencode_version: (release 22+)
      - gtf-gencode  #PL:mouse_gencode_version: (release M5+)
      - star-gencode #PL:human_gencode_version: (synced from gtf-gencode)
      - star-gencode #PL:mouse_gencode_version: (synced from gtf-gencode)
    """

    HUMAN_FTP_BASE = "https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/"
    MOUSE_FTP_BASE = "https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_mouse/"

    def query_ftp_releases(self, ftp_base: str, pattern: str, min_version: int) -> list:
        """Return sorted int list of release numbers >= min_version from EBI FTP."""
        try:
            with urllib.request.urlopen(ftp_base, timeout=10, context=_SSL_CTX) as resp:
                txt = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"Warning: failed to query {ftp_base}: {e}", file=sys.stderr)
            return []

        found = set(re.findall(pattern, txt))
        return sorted(int(v) for v in found if int(v) >= min_version)

    def run(self):
        human_versions = self.query_ftp_releases(
            self.HUMAN_FTP_BASE, r"release_([0-9]+)[/\"'>]", min_version=22
        )
        mouse_versions = self.query_ftp_releases(
            self.MOUSE_FTP_BASE, r"release_M(\d+)[/\"'>]", min_version=5
        )

        if not human_versions:
            print("[SKIP] GENCODE human: no releases found")
        else:
            print(f"[INFO] GENCODE human: {len(human_versions)} versions ({human_versions[0]}–{human_versions[-1]})")
            human_pl = _versions_to_pl_value(human_versions)
            _update_pl_key(os.path.join(BASE_DIR, "gtf-gencode"), "human_gencode_version", human_pl)
            _update_pl_key(os.path.join(BASE_DIR, "star-gencode"), "human_gencode_version", human_pl)

        if not mouse_versions:
            print("[SKIP] GENCODE mouse: no releases found")
        else:
            print(f"[INFO] GENCODE mouse: {len(mouse_versions)} versions (M{mouse_versions[0]}–M{mouse_versions[-1]})")
            mouse_pl = _versions_to_pl_value(mouse_versions)
            _update_pl_key(os.path.join(BASE_DIR, "gtf-gencode"), "mouse_gencode_version", mouse_pl)
            _update_pl_key(os.path.join(BASE_DIR, "star-gencode"), "mouse_gencode_version", mouse_pl)


if __name__ == "__main__":
    GencodeVersions().run()
