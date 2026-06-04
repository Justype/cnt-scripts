# CondaTainer Scripts

Build scripts and helper scripts for [CondaTainer](https://github.com/Justype/condatainer).

## Repository Layout

```
cnt-scripts/
├── build-scripts/              # Build recipes
│   ├── <distro>/<name>.def     # OS: Apptainer definition files
│   ├── <name>/<version>        # Apps: one file per version
│   ├── <name>                  # Apps (PL template): one file, #PL: expands all versions
│   └── <assembly>/<datatype>/… # Data: reference genomes, indexes, annotations
├── helpers/                    # Interactive service helpers
└── metadata/                   # Auto-generated index files
```

> [!NOTE]
> If the tool is available on conda-forge/bioconda, no need to add it to `build-script`. **CondaTainer** will query the Conda channels if no custom script is found.

> [!IMPORTANT]
> Build scripts always run as **single-task jobs**. Do not set multi-task scheduler directives. Writable overlay (`.img`) can only be mounted by **one process at a time**.

## Usage

Scripts are discovered automatically by **CondaTainer** — no manual configuration needed for the common cases below.

**CondaTainer** fetches scripts directly from this repo at runtime.

### Local clone (standalone install)

Clone this repo next to the **CondaTainer** binary and it is auto-detected:

```
/shared/condatainer/
├── bin/condatainer
└── cnt-scripts/        ← git clone of this repo; auto-detected
    ├── build-scripts/
    ├── helpers/
    └── metadata/
```

### Custom or private repo

You just need to have the same structure as this repo and you can host it anywhere (e.g., GitHub, GitLab, S3).

Point `extra_scripts_links` to any raw-content URL:

```bash
condatainer config prepend extra_scripts_links https://somewhere.com/custom-cnt-scripts/
```

Or set the env `CNT_EXTRA_SCRIPTS_LINKS` to override the config value. (`|` seprated if multiple)

If your repo also ships **prebuilt** OS overlay images, create `metadata/prebuilt_link` — a plain-text file with the base download URL (one line, no trailing slash):

```
https://somewhere.com/custom-cnt-scripts/download
```

**CondaTainer** fetches this file automatically and uses it as the base URL when downloading prebuilt overlays for scripts from that source.

## Building OS overlays locally

The `Makefile` builds OS overlay outputs from `build-scripts/ubuntu*/`:

```bash
make            # build base_image SIFs (default = sif)
make all        # build all: base_image SIFs + other defs as prefix dirs
make ubuntu24   # build only ubuntu24 targets
make list       # show discovered .def files and planned targets
make clean      # remove build/ directory
```

- `base_image.def` → `build/<distro>/base_image_<arch>.sif`
- other `.def` → `build/<distro>/<name>_<arch>.sqf` (except posit R and code-server)
- Override variables: `CONDATINER`, `APPTAINER`, `COND_FLAGS`, `APPT_FLAGS`

## Automatic Version Maintenance

Version lists in build scripts and helpers are kept up to date by a CI workflow that runs on the 1st and 15th of each month.

### `#AUTOUPDATE:` header

Add this header to any build script or helper to opt into automatic updates:

```
#AUTOUPDATE:{key}:{source}:{identifier}[>={min_version}]
```

| Source | Identifier | Example |
|---|---|---|
| `github` | `org/repo` | `github:cytoscape/cytoscape>=3.9.0` |
| `bioconda` | `package` | `bioconda:star>=2.7.0b` |
| `conda-forge` | `package` | `conda-forge:python>=3.8.0` |
| `docker` | `image:tag_pattern` | `docker:posit/r-base:^(\d+\.\d+\.\d+)-noble(?:-[^-]+)?$>=4.0.0` |

The `key` matches an existing header in the same file. The target type is detected automatically:

- **`#PL:key:`** (build scripts) — rewrites the full version list
- **`#DEP:key/`** (build scripts) — rewrites only the latest version, preserving `>=constraint`
- **`#VALUE: key=`** (helpers) — rewrites the value list, newest first

The unified updater (`.github/scripts/unified_auto.py`) groups entries by source and fetches each API once, even if the same package appears in multiple scripts.

### Per-directory `auto.py`

Scripts that need custom logic (e.g., GENCODE releases from EBI FTP) keep a per-directory `auto.py`. These run after the unified updater in the same CI job.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for how to add build scripts or helper scripts.

You can overwrite the `CNT_EXTRA_SCRIPTS_LINKS` env to point to your own repo for testing.

```
CNT_EXTRA_SCRIPTS_LINKS=https://raw.githubusercontent.com/Justype/cnt-scripts/refs/heads/helper/add-headless-state \
    condatainer helper --update
```
