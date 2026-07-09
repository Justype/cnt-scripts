#!/usr/bin/env python3
"""
Query Docker Hub and GitHub to update ubuntu20/*.def files

- R related => query posit/r-base tags
    - For tags like 4.4.3-focal-{arch} => updates #PL:version: in posit-r.def
    python3 build-scripts/ubuntu20/auto.py  # to update posit-r.def
- Apptainer => query apptainer/apptainer latest GitHub release
    - Updates the .deb download URL in base_image.def
- RStudio Server => query Posit downloads.json for the {CODE_NAME} stable build
    - Updates the .deb download URLs in rstudio-server.def
- TurboVNC / VirtualGL / KasmVNC => query latest GitHub releases
    - Updates the pinned versions in xfce4.def (Node.js stays pinned by hand per distro)
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

CODE_NAME = "focal"


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


class ApptainerVersion:
    """Discover the latest Apptainer release and update the base_image.def download URL."""

    def __init__(self):
        self.def_file = os.path.join(BASE_DIR, "base_image.def")

    def query_latest_version(self):
        """Return the latest GitHub release version (without 'v' prefix) whose
        apptainer_{version}_amd64.deb asset exists, or None."""
        url = "https://api.github.com/repos/apptainer/apptainer/releases/latest"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                data = json.load(resp)
        except Exception as e:
            print(f"Warning: failed to query {url}: {e}", file=sys.stderr)
            return None
        m = re.match(r"^v?(\d+\.\d+\.\d+)$", data.get("tag_name", ""))
        if not m:
            return None
        version = m.group(1)
        deb_name = f"apptainer_{version}_amd64.deb"
        if deb_name not in {a.get("name") for a in data.get("assets", [])}:
            print(f"Warning: {deb_name} missing from latest release assets, skipping.", file=sys.stderr)
            return None
        return version

    def update_def_file(self, version):
        """Rewrite the apptainer .deb download URL in base_image.def with the given version."""
        if not os.path.exists(self.def_file):
            print(f"Error: {self.def_file} not found.", file=sys.stderr)
            return False

        with open(self.def_file, "r") as f:
            content = f.read()

        pattern = re.compile(
            r"apptainer/releases/download/v(\d+\.\d+\.\d+)/apptainer_\d+\.\d+\.\d+_amd64\.deb"
        )
        m = pattern.search(content)
        if not m:
            print(f"Warning: no apptainer download URL in {self.def_file}.", file=sys.stderr)
            return False
        if m.group(1) == version:
            print(f"[SKIP] {os.path.basename(self.def_file)}: apptainer {version} up to date")
            return True

        new_url = f"apptainer/releases/download/v{version}/apptainer_{version}_amd64.deb"
        with open(self.def_file, "w") as f:
            f.write(pattern.sub(new_url, content))

        print(f"[UPDATED] {os.path.basename(self.def_file)}: apptainer {m.group(1)} → {version}")
        return True

    def run(self):
        version = self.query_latest_version()
        if not version:
            print("[SKIP] apptainer/apptainer: no release version found")
            return
        self.update_def_file(version)


class RStudioServerVersion:
    """Discover the stable RStudio Server release for CODE_NAME from Posit's
    downloads.json and update the .deb download URLs in rstudio-server.def."""

    DOWNLOADS_JSON = "https://www.rstudio.com/wp-content/downloads.json"
    VERSION_RE = re.compile(r"rstudio-server-(\d+\.\d+\.\d+-\d+)-")

    def __init__(self):
        self.def_file = os.path.join(BASE_DIR, "rstudio-server.def")

    def query_latest_version(self):
        """Return the stable server version for CODE_NAME (e.g. '2026.06.0-242'), or None."""
        try:
            with urllib.request.urlopen(self.DOWNLOADS_JSON, timeout=15, context=_SSL_CTX) as resp:
                data = json.load(resp)
        except Exception as e:
            print(f"Warning: failed to query {self.DOWNLOADS_JSON}: {e}", file=sys.stderr)
            return None
        installer = (data.get("rstudio", {}).get("open_source", {})
                     .get("stable", {}).get("server", {}).get("installer", {}))
        entry = installer.get(CODE_NAME) or {}
        if not entry.get("url"):
            print(f"[SKIP] rstudio-server.def: no stable Posit build for {CODE_NAME}")
            return None
        m = self.VERSION_RE.search(entry["url"])
        if not m:
            print(f"Warning: cannot parse version from {entry['url']}", file=sys.stderr)
            return None
        return m.group(1)

    def url_exists(self, url):
        """Return True if a HEAD request to url succeeds."""
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                return resp.status == 200
        except Exception:
            return False

    def update_def_file(self, version):
        """Rewrite the version in rstudio-server.def's download URLs after
        verifying every new URL exists (arm64 builds live on S3 and may lag)."""
        if not os.path.exists(self.def_file):
            print(f"Error: {self.def_file} not found.", file=sys.stderr)
            return False

        with open(self.def_file, "r") as f:
            content = f.read()

        urls = re.findall(r'https://[^"\s]*rstudio-server-[^"\s]+\.deb', content)
        if not urls:
            print(f"Warning: no rstudio-server download URLs in {self.def_file}.", file=sys.stderr)
            return False
        old_version = self.VERSION_RE.search(urls[0]).group(1)
        if old_version == version:
            print(f"[SKIP] {os.path.basename(self.def_file)}: rstudio-server {version} up to date")
            return True

        new_content = content
        for url in urls:
            new_url = url.replace(old_version, version)
            if not self.url_exists(new_url):
                print(f"Warning: {new_url} not available yet, keeping {old_version}.", file=sys.stderr)
                return False
            new_content = new_content.replace(url, new_url)

        with open(self.def_file, "w") as f:
            f.write(new_content)

        print(f"[UPDATED] {os.path.basename(self.def_file)}: rstudio-server {old_version} → {version}")
        return True

    def run(self):
        version = self.query_latest_version()
        if version:
            self.update_def_file(version)


class Xfce4Versions:
    """Update pinned TurboVNC, VirtualGL, and KasmVNC versions in xfce4.def from
    their latest GitHub releases, verifying the needed .deb assets exist first."""

    # repo, pinned-version pattern in xfce4.def, replacement, required asset template
    TOOLS = [
        dict(repo="TurboVNC/turbovnc",
             pattern=re.compile(r"turbovnc/releases/download/[\d.]+/turbovnc_([\d.]+)_"),
             replace="turbovnc/releases/download/{v}/turbovnc_{v}_",
             asset="turbovnc_{v}_{arch}.deb"),
        dict(repo="VirtualGL/virtualgl",
             pattern=re.compile(r"virtualgl/releases/download/[\d.]+/virtualgl_([\d.]+)_"),
             replace="virtualgl/releases/download/{v}/virtualgl_{v}_",
             asset="virtualgl_{v}_{arch}.deb"),
        dict(repo="kasmtech/KasmVNC",
             pattern=re.compile(r'KASMVNC_VERSION="([\d.]+)"'),
             replace='KASMVNC_VERSION="{v}"',
             asset="kasmvncserver_{codename}_{v}_{arch}.deb"),
    ]
    ARCHS = ("amd64", "arm64")

    def __init__(self):
        self.def_file = os.path.join(BASE_DIR, "xfce4.def")

    def query_latest_release(self, repo):
        """Return (version without 'v' prefix, set of asset names) for repo's
        latest GitHub release, or (None, empty set)."""
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                data = json.load(resp)
        except Exception as e:
            print(f"Warning: failed to query {url}: {e}", file=sys.stderr)
            return None, set()
        m = re.match(r"^v?(\d+(?:\.\d+)*)$", data.get("tag_name", ""))
        if not m:
            return None, set()
        return m.group(1), {a.get("name") for a in data.get("assets", [])}

    def run(self):
        if not os.path.exists(self.def_file):
            print(f"Error: {self.def_file} not found.", file=sys.stderr)
            return

        with open(self.def_file, "r") as f:
            content = f.read()

        changed = False
        for tool in self.TOOLS:
            name = tool["repo"].split("/")[1]
            m = tool["pattern"].search(content)
            if not m:
                print(f"Warning: no pinned {name} version in {self.def_file}.", file=sys.stderr)
                continue
            old_version = m.group(1)

            version, assets = self.query_latest_release(tool["repo"])
            if not version:
                continue
            if version == old_version:
                print(f"[SKIP] xfce4.def: {name} {version} up to date")
                continue

            needed = {tool["asset"].format(v=version, arch=a, codename=CODE_NAME) for a in self.ARCHS}
            missing = needed - assets
            if missing:
                print(f"Warning: {name} {version} missing assets ({', '.join(sorted(missing))}), "
                      f"keeping {old_version}.", file=sys.stderr)
                continue

            content = tool["pattern"].sub(tool["replace"].format(v=version), content)
            print(f"[UPDATED] xfce4.def: {name} {old_version} → {version}")
            changed = True

        if changed:
            with open(self.def_file, "w") as f:
                f.write(content)


if __name__ == "__main__":
    RVersions().run()
    ApptainerVersion().run()
    RStudioServerVersion().run()
    Xfce4Versions().run()
