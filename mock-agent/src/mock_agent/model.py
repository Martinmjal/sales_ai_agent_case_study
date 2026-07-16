from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import os
from typing import Any, Protocol

from openai import APIConnectionError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from mock_agent.adapter import ToolSpec


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelRequest:
    role: str
    model_name: str
    instructions: str
    input: tuple[dict[str, Any], ...]
    tools: tuple[ToolSpec, ...] = ()
    response_model: type[BaseModel] | None = None


@dataclass(frozen=True)
class ModelReply:
    content: Any = None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelClient(Protocol):
    async def respond(self, request: ModelRequest) -> ModelReply: ...


class ProviderFailure(RuntimeError):
    def __init__(
        self, error: Exception, retries: list[dict[str, Any]], *, transient: bool
    ):
        self.error = error
        self.retries = retries
        self.transient = transient
        super().__init__(f"{type(error).__name__}: {error}")


class OpenAIModelClient:
    """Direct, stateless adapter for the Libra-compatible Responses API."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        retry_delays: tuple[float, float] = (0.05, 0.1),
    ) -> None:
        self._client = client
        self._retry_delays = retry_delays

    async def respond(self, request: ModelRequest) -> ModelReply:
        client = self._client or self._client_from_environment()
        values: dict[str, Any] = {
            "model": request.model_name,
            "instructions": request.instructions,
            "input": [self._input_item(item) for item in request.input],
            "store": False,
        }
        if request.tools:
            values["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                    "strict": False,
                }
                for tool in request.tools
            ]
        retries = []
        for attempt in range(3):
            try:
                response = await client.responses.parse(
                    **values,
                    text_format=request.response_model,
                )
                break
            except ValidationError as error:
                return ModelReply(
                    content=None,
                    metadata={
                        "structured_output_error": error.errors(
                            include_url=False, include_input=False
                        )
                    },
                )
            except Exception as error:
                if attempt == 2 or not self._is_transient(error):
                    raise ProviderFailure(
                        error, retries, transient=self._is_transient(error)
                    ) from error
                retries.append(
                    {
                        "retry": attempt + 1,
                        "max_retries": 2,
                        "error_type": type(error).__name__,
                        "status_code": self._status_code(error),
                    }
                )
                await asyncio.sleep(self._retry_delays[attempt])
        calls = []
        for item in response.output:
            if getattr(item, "type", None) != "function_call":
                continue
            calls.append(
                ToolCall(
                    id=item.call_id,
                    name=item.name,
                    arguments=json.loads(item.arguments),
                )
            )
        parsed = getattr(response, "output_parsed", None)
        content = parsed.model_dump(mode="json") if parsed is not None else None
        usage = getattr(response, "usage", None)
        usage_values = {
            key: int(getattr(usage, key, 0) or 0)
            for key in ("input_tokens", "output_tokens", "total_tokens")
        }
        return ModelReply(
            content=content,
            tool_calls=tuple(calls),
            usage=usage_values,
            metadata={
                "response_id": response.id,
                "status": response.status,
                "provider_retries": retries,
            },
        )

    @classmethod
    def _is_transient(cls, error: Exception) -> bool:
        status_code = cls._status_code(error)
        return (
            isinstance(error, (APIConnectionError, ConnectionError, TimeoutError))
            or status_code == 429
            or (status_code is not None and 500 <= status_code < 600)
        )

    @staticmethod
    def _status_code(error: Exception) -> int | None:
        status_code = getattr(error, "status_code", None)
        if status_code is None:
            status_code = getattr(getattr(error, "response", None), "status_code", None)
        return int(status_code) if status_code is not None else None

    @staticmethod
    def _input_item(item: dict[str, Any]) -> dict[str, Any]:
        content = item.get("content")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=True, default=str)
        return {"type": "message", "role": item["role"], "content": content}

    @staticmethod
    def _client_from_environment() -> AsyncOpenAI:
        base_url = os.environ.get("LIBRA_BASE_URL")
        if not base_url:
            raise RuntimeError("Set LIBRA_BASE_URL before running the planner-executor")
        api_key = os.environ.get("LIBRA_INTERVIEW_API_KEY") or os.environ.get(
            "OPENAI_API_KEY"
        )
        if not api_key:
            raise RuntimeError("Set LIBRA_INTERVIEW_API_KEY or OPENAI_API_KEY")
        return AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)
