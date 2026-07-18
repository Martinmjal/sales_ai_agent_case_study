from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable

from mock_agent.artifacts import ArtifactValidationError, RunArtifact, read_artifact


class RunNotFoundError(LookupError):
    pass


class UnsupportedRunError(LookupError):
    pass


@dataclass(frozen=True)
class ArtifactReference:
    artifact: RunArtifact
    path: Path
    canonical: bool

    @property
    def timestamp(self) -> str:
        return self.artifact.timing.updated_at or self.artifact.timing.started_at


class ArtifactRepository:
    """Read-only index derived from artifact files on every request."""

    def __init__(self, directories: Iterable[Path]):
        self.directories = tuple(directories)

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
        seen_paths: set[Path] = set()
        for path in self._paths():
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            try:
                artifact = read_artifact(path, enrich_task=True)
            except (ArtifactValidationError, KeyError, TypeError, ValueError, OSError):
                continue
            canonical = _is_canonical(path)
            current = references.get(artifact.run_id)
            if current is None or (canonical and not current.canonical):
                references[artifact.run_id] = ArtifactReference(
                    artifact=artifact,
                    path=path,
                    canonical=canonical,
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
            if (
                isinstance(value, dict)
                and value.get("run_id", value.get("session_id")) == run_id
            ):
                return path
        return None

    def _paths(self):
        for directory in self.directories:
            if directory.exists():
                yield from sorted(directory.rglob("*.json"))


def _is_canonical(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8") as stream:
            prefix = stream.read(256)
    except (OSError, UnicodeDecodeError):
        return False
    return '"artifact_type": "run_artifact"' in prefix


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
