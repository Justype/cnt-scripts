#!/usr/bin/env python3
"""
Query remote sources to update grch38/* build script files

- GENCODE releases (EBI FTP) => updates #PL:gencode_version: in:
    - gtf-gencode        (release 22+)
    - transcript-gencode (release 23+)
    - star-gencode       (synced from gtf-gencode)
    - salmon-gencode     (synced from transcript-gencode, release 23+)
    python3 build-scripts/grch38/auto.py  # to update all

#PL: and #DEP: bioconda/github updates are handled by unified_auto.py via #AUTOUPDATE: headers.
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
    Discover GENCODE human releases from EBI FTP and update:
      - gtf-gencode        #PL:gencode_version: (release 22+)
      - transcript-gencode #PL:gencode_version: (release 23+)
      - star-gencode       #PL:gencode_version: (synced from gtf-gencode)
    """

    FTP_BASE = "https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/"

    def query_ftp_releases(self, min_version: int) -> list:
        """Return sorted int list of release numbers >= min_version from EBI FTP."""
        try:
            with urllib.request.urlopen(self.FTP_BASE, timeout=10, context=_SSL_CTX) as resp:
                txt = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"Warning: failed to query {self.FTP_BASE}: {e}", file=sys.stderr)
            return []

        found = set(re.findall(r"release_([0-9]+)[/\"'>]", txt))
        return sorted(int(v) for v in found if int(v) >= min_version)

    def run(self):
        gtf_versions = self.query_ftp_releases(min_version=22)
        if not gtf_versions:
            print("[SKIP] GENCODE: no releases found")
            return

        transcript_versions = [v for v in gtf_versions if v >= 23]
        print(f"[INFO] GENCODE: {len(gtf_versions)} versions ({gtf_versions[0]}–{gtf_versions[-1]})")

        gtf_pl = _versions_to_pl_value(gtf_versions)
        _update_pl_key(os.path.join(BASE_DIR, "gtf-gencode"), "gencode_version", gtf_pl)
        _update_pl_key(os.path.join(BASE_DIR, "star-gencode"), "gencode_version", gtf_pl)

        transcript_pl = _versions_to_pl_value(transcript_versions)
        _update_pl_key(os.path.join(BASE_DIR, "transcript-gencode"), "gencode_version", transcript_pl)
        _update_pl_key(os.path.join(BASE_DIR, "salmon-gencode"), "gencode_version", transcript_pl)


if __name__ == "__main__":
    GencodeVersions().run()
