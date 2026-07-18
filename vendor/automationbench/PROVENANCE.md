# AutomationBench provenance

- Upstream: <https://github.com/zapier/AutomationBench>
- Commit: `eda214109cf891ebe8102ca826b87fb98911e103`
- License: MIT; preserved in `LICENSE`
- Snapshot verified: 2026-07-17

The `automationbench/` runtime source and `UPSTREAM_README.md` are byte-for-byte copies of that
commit. Local packaging, tests, standalone visualizer, lockfile, and repository tooling were not
vendored because this repository installs AutomationBench through its single root project. No
runtime source changes have been made.

To update the snapshot, check out the desired upstream commit in a temporary directory, compare
the full `automationbench/` tree, replace that tree and `UPSTREAM_README.md` without editing them,
retain the upstream `LICENSE`, update the commit above, regenerate the root `uv.lock`, and run all
root verification commands documented in the repository README.
