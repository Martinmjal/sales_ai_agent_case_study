from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sales_agent.artifacts import ArtifactValidationError, RunArtifact, read_artifact


class RunNotFoundError(LookupError):
    pass


class UnsupportedRunError(LookupError):
    pass


@dataclass(frozen=True)
class ArtifactReference:
    artifact: RunArtifact
    path: Path

    @property
    def timestamp(self) -> str:
        return self.artifact.timing.updated_at or self.artifact.timing.started_at


class ArtifactRepository:
    """Read-only index derived from artifact files on every request."""

    def __init__(self, directory: Path):
        self.directory = directory

    def recent(self) -> list[ArtifactReference]:
        return sorted(
            self._index().values(),
            key=lambda reference: _timestamp(reference.timestamp),
            reverse=True,
        )

    def get(self, run_id: str) -> ArtifactReference:
        reference = self._index().get(run_id)
        if reference is not None:
            return reference
        if self._unsupported_path(run_id) is not None:
            raise UnsupportedRunError(f"Run {run_id!r} is malformed or unsupported")
        raise RunNotFoundError(f"Unknown run ID: {run_id}")

    def _index(self) -> dict[str, ArtifactReference]:
        references: dict[str, ArtifactReference] = {}
        for path in self._paths():
            try:
                artifact = read_artifact(path)
            except (ArtifactValidationError, KeyError, TypeError, ValueError, OSError):
                continue
            if artifact.run_id not in references:
                references[artifact.run_id] = ArtifactReference(
                    artifact=artifact,
                    path=path,
                )
        return references

    def _unsupported_path(self, run_id: str) -> Path | None:
        for path in self._paths():
            if path.stem == run_id:
                return path
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue
            if isinstance(value, dict) and value.get("run_id", value.get("session_id")) == run_id:
                return path
        return None

    def _paths(self):
        if self.directory.exists():
            yield from sorted(self.directory.rglob("*.json"))


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
