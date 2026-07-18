"""Offline evaluation execution and deterministic reporting."""

from mock_agent.evaluation.cli import main, parser

__all__ = ["main", "parser"]


def _parser():
    """Compatibility alias for callers that previously inspected the parser."""

    return parser()
