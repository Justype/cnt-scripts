---
name: 🚀 Helper Script Feature Request
about: Request a new helper script or an improvement to an existing one
title: "[Helper Request] <script-name or new service>"
labels: enhancement, helper
assignees: ""
---

## Request Type

- [ ] **New helper script** — a new interactive service to run on HPC (e.g. Jupyter, Shiny Server)
- [ ] **Improvement to existing script** — add a flag, fix UX, extend scheduler support
- [ ] **New scheduler support** — port an existing helper to a new scheduler
- [ ] **Other**

## Script / Service Name

- **Script name** (existing or proposed): <!-- e.g. jupyter, rstudio-server -->
- **Affected schedulers**: <!-- headless / SLURM / PBS / LSF / HTCondor / All -->

## Problem / Motivation

<!-- What limitation or need is driving this request? -->

## Proposed Solution

<!-- Describe the change or new script. Include proposed flags, behavior, or overlay requirements. -->

## Overlay / Dependency Requirements

### OS Overlay
<!-- Specify any OS overlay needed, e.g. ubuntu24/build-essential -->

### Workspace Overlay
<!-- Packages to install inside the conda environment overlay via mm-install, e.g. mm-install jupyter -->

## Tested On

- [ ] headless
- [ ] SLURM
- [ ] PBS
- [ ] LSF
- [ ] HTCondor

## Additional Notes

<!-- Links to upstream docs, example scripts from other tools, or related issues -->
