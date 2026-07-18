from __future__ import annotations

import argparse
import sys

from sales_agent.evaluation.cli import main as evaluation_main
from sales_agent.main import main as run_main
from sales_agent.viewer.main import main as viewer_main


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        prog="sales-agent",
        description="Run, evaluate, report, or inspect the Sales plan-state agent.",
    )
    commands = value.add_subparsers(dest="command", metavar="COMMAND")
    commands.add_parser("run", add_help=False, help="Run one AutomationBench task")
    commands.add_parser("evaluate", add_help=False, help="Run or resume an evaluation panel")
    commands.add_parser("report", add_help=False, help="Generate deterministic evaluation reports")
    commands.add_parser("viewer", add_help=False, help="Start the read-only trace viewer")
    return value


def main(argv: list[str] | None = None) -> None:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or values[0] in {"-h", "--help"}:
        parser().print_help()
        return
    command, arguments = values[0], values[1:]
    commands = {
        "run": lambda args: run_main(args, prog="sales-agent run"),
        "evaluate": lambda args: evaluation_main(
            ["evaluate", *args], prog="sales-agent", run_command="evaluate"
        ),
        "report": lambda args: evaluation_main(["report", *args], prog="sales-agent"),
        "viewer": lambda args: viewer_main(args, prog="sales-agent viewer"),
    }
    handler = commands.get(command)
    if handler is None:
        parser().error(f"unknown command: {command}")
    handler(arguments)


if __name__ == "__main__":
    main()
