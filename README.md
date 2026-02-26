# cnt-scripts

Build scripts and helper scripts for [CondaTainer](https://github.com/Justype/condatainer).

## Repository Layout

```
cnt-scripts/
├── build-scripts/              # Build recipes
│   ├── <distro>/<name>.def     # OS: Apptainer definition files
│   ├── <name>/<version>        # Apps: Custom tools
│   └── <assembly|project>/<datatype>/<version>  # Data
├── helpers/                # Interactive service helpers
│   ├── headless/           # on the current server
│   ├── slurm/              # on SLURM clusters
│   ├── pbs/                # on PBS clusters
│   ├── lsf/                # on LSF clusters
│   └── htcondor/           # on HTCondor servers/clusters
└── metadata/               # Auto-generated index files
```

> [!NOTE]
> If the tool is available on conda-forge/bioconda, no need to add it to `build-script`. **CondaTainer** will query the Conda channels if no custom script is found.

> [!IMPORTANT]
> Build scripts always run as **single-task jobs**. Do not set multi-task scheduler directives. Writable overlay (`.img`) can only be mounted by **one process at a time**.

## Usage

Scripts are discovered automatically by **CondaTainer** — no manual configuration needed for the common cases below.

**CondaTainer** fetches scripts directly from this repo at runtime.

### Local clone (portable install)

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

Point `scripts_link` to any raw-content URL:

```bash
condatainer config set scripts_link https://somewhere.com/custom-cnt-scripts/
```

Or set the env `CNT_SCRIPTS_LINK` to override the config value.

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

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for how to add build scripts or helper scripts.

You can overwrite the `CNT_SCRIPTS_LINK` env to point to your own repo for testing.

```
CNT_SCRIPTS_LINK=https://raw.githubusercontent.com/Justype/cnt-scripts/refs/heads/helper/add-headless-state \
    condatainer helper --update
```
