#!/usr/bin/env python3
"""Generate helper metadata for scripts in `helpers/`.

Scans files directly under `helpers/` (not subfolders) and writes JSON to
`metadata/helper-scripts.json` with flat structure:
{
    "script_name": { "path": "helpers/script_name" },
    ...
}

Script is safe to run locally or in CI.
"""
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "metadata"
OUT_FILE = OUT_DIR / "helper-scripts.json"

HELPERS_ROOT = ROOT / "helpers"

BLACKLIST = {"README.md", "auto.py"}

def main():
    data = {}
    if HELPERS_ROOT.exists():
        for p in sorted(HELPERS_ROOT.iterdir()):
            if not p.is_file():
                continue
            if p.name in BLACKLIST:
                continue
            rel = p.relative_to(ROOT).as_posix()
            data[p.stem] = {"path": rel}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(data, indent=2, ensure_ascii=False)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        f.write(json_text)

    try:
        with gzip.open(str(OUT_FILE) + ".gz", "wb") as gz:
            gz.write(json_text.encode("utf-8"))
    except Exception as e:
        print(f"Warning: failed to write gzipped metadata: {e}")

    print(f"Wrote helper metadata to {OUT_FILE} and {OUT_FILE}.gz")


if __name__ == "__main__":
    main()
