# Contributing

Thank you for helping improve this project! This document covers contributions to `cnt-scripts`:

- Adding `build-scripts` (new app/data/genome build definitions)
- Adding or updating `helper-scripts` (interactive service helpers)

> For CLI code and docs, contribute to the [`condatainer`](https://github.com/Justype/condatainer) repo instead.

## Quick start

1. Fork this repository and create a feature branch off `main`.
2. Make changes, run tests, and verify on HPC and/or locally if applicable.
3. Push your branch to your fork and open a Pull Request targeting `main`.
4. In your PR description include testing steps, relevant logs, and any backward-compatibility notes.

## 1) Adding `build-scripts`

What this covers
- New **OS**, **Apps**, and **Data** build scripts.

Where to add
- **OS** — `build-scripts/<distro>/<name>` (e.g., `ubuntu24/igv`) — Apptainer definition files
- **Apps** — `build-scripts/<name>/<version>` (e.g., `cellranger/9.0.1`) — apps not available as conda packages, or specific versions not in conda
- **Data** — `build-scripts/<assembly|project>/<datatype>/<version>` (e.g., `grch38/star/2.7.11b/gencode47-101`) — any data, including genome reference indexes
  - Include the tool version if the index is tool-version dependent
  - E.g., `build-scripts/grch38/star/2.7.11b/gencode47-101`
  - E.g., `build-scripts/grch38/bowtie2/ucsc_no_alt`

Guidelines
- Please check the [Build Script Manual](https://github.com/Justype/condatainer/blob/main/docs/manuals/build_script.md) for naming conventions and available variables.

Testing
- Test the build script locally and on HPC if applicable.
- Ensure the resulting environment/image works as expected (paths and environment variables).

PR notes
- Please include the scheduler job log or terminal output showing successful build and test.

## 2) Adding or updating `helper-scripts`

What this covers
- New interactive service helpers (e.g., a new web-based app to run on HPC compute nodes)
- Bug fixes or updates to existing helpers

Where to add
- Scripts live in `helpers/<scheduler>/` — one directory per scheduler: `headless/`, `slurm/`, `pbs/`, `lsf/`, `htcondor/`
- **A new helper must be added to all scheduler directories.** Use an existing script (e.g., `helpers/slurm/code-server`) as a template.
- **A scheduler-specific fix** only needs to update the affected scheduler's script.
- See [`helpers/README.md`](./helpers/README.md) for the shared-library API and script structure.

Testing
- SLURM is the primary tested scheduler. Test on a SLURM cluster when possible.
- For other schedulers, include any available test output or note which cluster was used.

PR notes
- Specify which schedulers were tested in the PR description.
- Include terminal output or job logs showing successful submission and connection.

## PR checklist

- Title and description explaining change and how to test
- Small, focused commits with clear messages

## Contacts / Maintainers

- If unsure about scope or breaking changes, open an issue first describing the planned work and tag maintainers.

Thanks again — contributions make this project better!
