from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from mock_agent.artifacts import (
    ArtifactValidationError,
    ImmutableArtifactError,
    RunArtifact,
    RunArtifactStore,
    artifact_to_session_view,
    read_artifact,
    session_view_to_artifact,
)


class SessionNotFoundError(LookupError):
    """Raised when a run artifact cannot be found."""


class ImmutableSessionError(ImmutableArtifactError):
    """Compatibility name for an attempted terminal artifact mutation."""


class SessionStore:
    """UI adapter over the canonical store; it never writes the legacy schema."""

    def __init__(
        self, directory: Path, *, read_directories: Iterable[Path] | None = None
    ):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.read_directories = tuple(read_directories or (directory,))
        self._store = RunArtifactStore(directory)

    def create(
        self, artifact: RunArtifact | dict[str, Any]
    ) -> dict[str, Any]:
        canonical = (
            artifact
            if isinstance(artifact, RunArtifact)
            else session_view_to_artifact(artifact)
        )
        filename = f"{canonical.run_id}.json"
        self._store.write(canonical, filename=filename)
        return artifact_to_session_view(canonical, artifact_filename=filename)

    def save(self, session: dict[str, Any]) -> None:
        canonical = session_view_to_artifact(session)
        filename = str(session.get("artifact_filename") or f"{canonical.run_id}.json")
        try:
            self._store.write(canonical, filename=filename)
        except ImmutableArtifactError as error:
            raise ImmutableSessionError(str(error)) from error

    def read(self, session_id: str) -> dict[str, Any]:
        for session in self.list():
            if session.get("session_id") == session_id:
                return session
        raise SessionNotFoundError(f"Unknown run ID: {session_id}")

    def list(self) -> list[dict[str, Any]]:
        sessions_by_id: dict[str, dict[str, Any]] = {}
        canonical_by_id: dict[str, bool] = {}
        seen_paths: set[Path] = set()
        for directory in self.read_directories:
            if not directory.exists():
                continue
            for path in directory.rglob("*.json"):
                resolved = path.resolve()
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                try:
                    artifact = read_artifact(path, enrich_task=True)
                except ArtifactValidationError:
                    continue
                is_canonical = _is_canonical_file(path)
                if artifact.run_id in sessions_by_id and (
                    canonical_by_id[artifact.run_id] or not is_canonical
                ):
                    continue
                sessions_by_id[artifact.run_id] = artifact_to_session_view(
                    artifact, artifact_filename=path.name
                )
                canonical_by_id[artifact.run_id] = is_canonical
        return sorted(
            sessions_by_id.values(),
            key=lambda session: session["lifecycle"]["created_at"],
            reverse=True,
        )

    @staticmethod
    def _is_supported(session: Any) -> bool:
        if not isinstance(session, dict):
            return False
        try:
            session_view_to_artifact(session)
        except (ArtifactValidationError, KeyError, TypeError, ValueError):
            return False
        return True


def _is_canonical_file(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8") as stream:
            prefix = stream.read(240)
    except OSError:
        return False
    return '"artifact_type": "run_artifact"' in prefix
