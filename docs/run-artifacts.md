# Run artifacts

`run_artifact` schema version 1 is the only run format written by the CLI, evaluator, and Agent UI.
The typed boundary model and atomic serializer live in
`mock-agent/src/mock_agent/artifacts.py`; runtime controller state remains separate.

Each artifact contains one stable run ID, a complete task snapshot, model/runtime/prompt/protocol
configuration identity, lifecycle state and termination reason, a monotonic correlated trace,
usage and retry/call summaries, response and terminal errors, initial/final worlds, official score
and assertion evidence, plus evaluation repetition/resumption/infrastructure-replacement metadata
when applicable.

## Authoritative locations

- `mock-agent/results/runs/` contains standalone CLI and Agent UI runs. New filenames are
  `<run-id>.json`.
- `mock-agent/results/evaluation/` contains one authoritative artifact per accepted evaluation
  configuration/task/repetition. Its configuration-derived filenames remain stable across resume.
- `mock-agent/results/development/` contains the representative partial development artifact.
- `report.md` and `report.json` are derived outputs, not run artifacts.

The retired `sessions/` evaluation copies were deleted. Agent UI scans the canonical result store
directly and adapts artifacts to its existing HTTP response shape only in memory. A viewer link is
`http://127.0.0.1:8000/?run_id=<stable-run-id>`.

The evaluator indexes configuration/task/repetition triples by reading these artifacts through the
same compatibility boundary; it neither rewrites nor copies them. Final reporting requires the
expected manifest, configuration, and repetition count and rejects incomplete or ambiguous
coverage. Filtered subsets require explicit exploratory mode and are labeled incomplete in both
Markdown and JSON. Artifact links point directly to the canonical JSON files.

## Persistence invariants

Writes use a temporary file, `fsync`, and atomic replacement. Active snapshots may append events,
but existing events cannot change and sequence numbers must increase. Once an artifact is
completed, stopped, failed, or interrupted, the store refuses every mutation.

## Historical compatibility

The reader supports canonical schema version 1 plus these historical inputs:

- `agent_evaluation_run` schema version 1;
- Agent UI session schema version 1;
- raw `RuntimeOutcome` JSON;
- the earlier configured-run evidence record.

Compatibility is strictly “read old, write one”: all shared serializers emit only
`run_artifact` version 1. `mock-agent/scripts/migrate_run_artifacts.py` is the deterministic
repository migration used for the committed evidence. Malformed files and unknown canonical or
legacy schema versions are rejected rather than guessed. Historical terminal sessions that never
recorded a reason are explicitly marked `legacy_unknown` with configuration metadata noting that
the original reason was unavailable.
