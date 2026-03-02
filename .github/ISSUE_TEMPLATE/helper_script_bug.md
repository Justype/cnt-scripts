---
name: 🔧 Helper Script Bug Report
about: Report a problem with an existing helper script (RStudio, VS Code, xfce4, etc.)
title: "[Helper Bug] <script-name> on <scheduler>"
labels: bug, helper
assignees: ""
---

## Script Name & Scheduler

- **Script**: <!-- e.g. rstudio-server, code-server, xfce4 -->
- **Scheduler**: <!-- headless / SLURM / PBS / LSF / HTCondor -->

## CondaTainer Version

<!-- Run `condatainer --version` -->

## Expected Behavior

<!-- What should have happened? -->

## Actual Behavior

<!-- What happened instead? -->

## Environment

| Item | Value |
|------|-------|
| OS & version | |
| HPC Scheduler & version | SLURM / PBS / LSF / HTCondor / None |
| Apptainer/Singularity version | |
| CondaTainer version | |

## Job / Terminal Log

```bash
# Paste the exact condatainer helper command and full terminal output or scheduler job log here
condatainer helper <script-name> [flags]
```

## Additional Info

<!-- SSH tunnel output, browser errors, screenshots, or extra notes -->
