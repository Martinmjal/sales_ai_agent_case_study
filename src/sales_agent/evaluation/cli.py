from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from sales_agent.config import load_repository_environment, require_provider_settings
from sales_agent.evaluation.records import EvaluationConfiguration, EvaluationManifest
from sales_agent.evaluation.report import write_report
from sales_agent.evaluation.runner import RuntimeFactory, run_evaluations
from sales_agent.model import OpenAIModelClient
from sales_agent.plan_state_runtime import PlanStateRuntime


def parser(*, prog: str | None = None, run_command: str = "run") -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        prog=prog, description="Run and report offline agent evaluations"
    )
    commands = value.add_subparsers(dest="command", required=True)
    run = commands.add_parser(run_command, help="Run or resume a preregistered task panel")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--repetitions", type=int, required=True)
    run.add_argument("--artifacts-dir", type=Path, required=True)
    report = commands.add_parser("report", help="Build deterministic offline reports")
    report.add_argument("--manifest", type=Path, required=True)
    report.add_argument("--config", type=Path, required=True)
    report.add_argument("--repetitions", type=int, required=True)
    report.add_argument("--artifacts-dir", type=Path, required=True)
    report.add_argument("--markdown", type=Path, required=True)
    report.add_argument("--json", type=Path, required=True)
    report.add_argument("--exploratory", action="store_true")
    report.add_argument("--task-id", dest="task_ids", action="append")
    report.add_argument("--viewer-base-url", default="http://127.0.0.1:8000")
    return value


def main(
    argv: list[str] | None = None,
    *,
    runtime_factory: RuntimeFactory | None = None,
    prog: str | None = None,
    run_command: str = "run",
) -> None:
    args = parser(prog=prog, run_command=run_command).parse_args(argv)
    manifest = EvaluationManifest.read(args.manifest)
    config = EvaluationConfiguration.read(args.config)
    if args.command == run_command:
        load_repository_environment()
        if runtime_factory is None:
            require_provider_settings()
        factory = runtime_factory or (lambda: PlanStateRuntime(model_client=OpenAIModelClient()))
        asyncio.run(
            run_evaluations(manifest, config, args.repetitions, args.artifacts_dir, factory)
        )
    else:
        write_report(
            args.artifacts_dir,
            args.markdown,
            args.json,
            manifest,
            config,
            args.repetitions,
            task_ids=args.task_ids,
            exploratory=args.exploratory,
            viewer_base_url=args.viewer_base_url,
        )


if __name__ == "__main__":
    main()
