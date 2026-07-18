# Run artifacts

`run_artifact` schema version 1 is the repository's only supported run format. The typed
`RunArtifact` boundary and serializer live in `src/sales_agent/artifacts.py`; runtime controller
state remains separate.

Each artifact contains one stable run ID, a complete task snapshot, model/runtime/prompt/protocol
configuration identity, lifecycle state and termination reason, a monotonic correlated trace,
usage and retry/call summaries, response and terminal errors, initial/final worlds, official score
and assertion evidence, plus evaluation repetition/resumption/infrastructure-replacement metadata
when applicable.

The CLI, evaluator, report generator, and trace viewer read this schema directly. Session,
`agent_evaluation_run`, raw runtime-outcome, and configured-run records are unsupported. Malformed
files, other artifact types, and unknown schema versions are rejected rather than converted.

## Authoritative locations

- `results/runs/` contains standalone CLI runs. New filenames are `<run-id>.json`.
- `results/evaluation/` contains one authoritative artifact per accepted evaluation
  configuration/task/repetition. Configuration-derived filenames remain stable across resume.
- `results/development/` contains representative development artifacts.
- `report.md` and `report.json` are derived outputs, not run artifacts.

The trace viewer scans these canonical result locations directly and writes nothing. A viewer link
is `http://127.0.0.1:8000/runs/<stable-run-id>`.

The evaluator indexes configuration/task/repetition triples from canonical artifacts without
rewriting or copying them. Final reporting requires the expected manifest, configuration, and
repetition count and rejects incomplete or ambiguous coverage. Filtered subsets require explicit
exploratory mode and are labeled incomplete in both Markdown and JSON. Artifact links point
directly to the canonical JSON files.

## Write-once persistence

A `RunArtifactStore` creates each artifact once at its terminal destination. It serializes and
flushes a temporary file, installs that file atomically only if the destination does not exist,
and synchronizes the containing directory. An existing destination always causes the write to
fail. Its bytes are never modified, even when it is malformed or contains the same run ID.

CLI and evaluation runs are assembled in memory and persisted only after the runtime has produced
its terminal outcome. There are no active-artifact snapshots or in-place artifact updates.
