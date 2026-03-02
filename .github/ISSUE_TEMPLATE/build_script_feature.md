---
name: 💡 Build Script Feature Request
about: Request a new app / data / OS build script, or an improvement to an existing one
title: "[Build Request] <category>/<name>/<version>"
labels: enhancement, build
assignees: ""
---

## Request Type

- [ ] **New App** — tool not available as a conda package (e.g. `cellranger/9.0.1`)
- [ ] **New OS image** — distro or system-level tool (e.g. `ubuntu24/igv`)
- [ ] **New Data overlay** — genome index or other dataset (e.g. `grch38/star/2.7.11b/gencode47-101`)
- [ ] **Update existing script** — bump version or fix packaging of an existing entry
- [ ] **Other**

## Name & Version

- **Name**: <!-- e.g. cellranger -->
- **Version**: <!-- e.g. 9.0.1 -->
- **Proposed path** (if known): <!-- e.g. build-scripts/cellranger/9.0.1 or build-scripts/ubuntu24/igv or build-scripts/grch38/star/2.7.11b/gencode47-101 -->

## Why It's Needed

<!-- e.g. "not available on conda-forge", "index for tool/organism not available" -->

## Upstream / Download Source

<!-- Link to the official download page or release: -->

## Dependencies

<!-- List `#DEP:name/version` entries if known, or describe runtime dependencies -->

## Scheduler Directives (if compute/data-heavy)

```bash
# Suggested #SBATCH / #PBS / #BSUB directives for the build job
```

## Environment Variables to Export

```bash
# Suggested #ENV: lines (e.g. #ENV:CELLRANGER_REF_DIR=$app_root)
```

## Additional Notes

<!-- License, install docs, known build issues, etc. -->
