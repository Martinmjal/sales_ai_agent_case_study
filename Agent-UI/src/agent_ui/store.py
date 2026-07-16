from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
from typing import Any


class SessionNotFoundError(LookupError):
    """Raised when a session artifact cannot be found."""


class ImmutableSessionError(RuntimeError):
    """Raised when a terminal session artifact would be changed."""


class SessionStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def create(self, session: dict[str, Any]) -> dict[str, Any]:
        stored = copy.deepcopy(session)
        timestamp = stored["lifecycle"]["created_at"].replace(":", "").replace("-", "")
        timestamp = timestamp.replace(".", "").replace("+0000", "Z")
        task_slug = stored["task"]["task_id"].replace(".", "-")
        stored["artifact_filename"] = (
            f"{timestamp}_{task_slug}_{stored['session_id'][:8]}.json"
        )
        self.save(stored)
        return stored

    def save(self, session: dict[str, Any]) -> None:
        destination = self.directory / session["artifact_filename"]
        if destination.exists():
            try:
                current = json.loads(destination.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = None
            if current and current.get("status") in {
                "Completed",
                "Stopped",
                "Failed",
                "Interrupted",
            }:
                raise ImmutableSessionError(
                    f"Terminal session cannot be changed: {session['session_id']}"
                )
        payload = json.dumps(session, indent=2, ensure_ascii=True, default=str) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.directory,
            prefix=f".{session['session_id']}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, destination)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def read(self, session_id: str) -> dict[str, Any]:
        for session in self.list():
            if session.get("session_id") == session_id:
                return session
        raise SessionNotFoundError(f"Unknown session ID: {session_id}")

    def list(self) -> list[dict[str, Any]]:
        sessions = []
        for path in self.directory.glob("*.json"):
            try:
                session = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if self._is_supported(session):
                sessions.append(session)
        return sorted(
            sessions,
            key=lambda session: session["lifecycle"]["created_at"],
            reverse=True,
        )

    @staticmethod
    def _is_supported(session: Any) -> bool:
        if not isinstance(session, dict) or session.get("schema_version") != 1:
            return False
        lifecycle = session.get("lifecycle")
        task = session.get("task")
        agent = session.get("agent")
        evaluation = session.get("evaluation")
        return (
            isinstance(session.get("session_id"), str)
            and session.get("status")
            in {"Running", "Completed", "Stopped", "Failed", "Interrupted"}
            and isinstance(lifecycle, dict)
            and isinstance(lifecycle.get("created_at"), str)
            and isinstance(task, dict)
            and isinstance(task.get("task_id"), str)
            and isinstance(task.get("name"), str)
            and isinstance(task.get("prompt"), list)
            and isinstance(agent, dict)
            and isinstance(agent.get("model"), str)
            and isinstance(agent.get("max_steps"), int)
            and isinstance(agent.get("agent_version"), str)
            and isinstance(session.get("events"), list)
            and (evaluation is None or isinstance(evaluation, dict))
        )
