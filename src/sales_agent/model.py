from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from openai import APIConnectionError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from sales_agent.adapter import ToolSpec
from sales_agent.config import provider_max_retries, require_provider_settings


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    argument_error: dict[str, Any] | None = None


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
    def __init__(self, error: Exception, retries: list[dict[str, Any]], *, transient: bool):
        self.error = error
        self.retries = retries
        self.transient = transient
        super().__init__(f"{type(error).__name__}: {error}")


class OpenAIModelClient:
    """Direct adapter that reuses one explicitly bounded provider client."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        retry_delays: tuple[float, float] = (0.05, 0.1),
        max_retries: int | None = None,
    ) -> None:
        self._client = client
        self._retry_delays = retry_delays
        self._max_retries = provider_max_retries() if max_retries is None else max_retries
        if not 0 <= self._max_retries <= 4:
            raise ValueError("max_retries must be between 0 and 4")

    async def respond(self, request: ModelRequest) -> ModelReply:
        if self._client is None:
            self._client = self._client_from_environment()
        client = self._client
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
        for attempt in range(self._max_retries + 1):
            try:
                if request.response_model is None:
                    response = await client.responses.create(**values)
                else:
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
                if attempt == self._max_retries or not self._is_transient(error):
                    raise ProviderFailure(
                        error, retries, transient=self._is_transient(error)
                    ) from error
                retries.append(
                    {
                        "retry": attempt + 1,
                        "max_retries": self._max_retries,
                        "error_type": type(error).__name__,
                        "status_code": self._status_code(error),
                    }
                )
                delay = self._retry_delays[min(attempt, len(self._retry_delays) - 1)]
                await asyncio.sleep(delay)
        calls = []
        for response_item in response.output:
            item = cast(Any, response_item)
            if getattr(item, "type", None) != "function_call":
                continue
            raw_arguments = item.arguments
            argument_error = None
            try:
                arguments = json.loads(raw_arguments)
            except (json.JSONDecodeError, TypeError) as error:
                arguments = {}
                argument_error = {
                    "type": "malformed_arguments_json",
                    "message": f"{type(error).__name__}: {error}",
                    "raw_arguments": raw_arguments,
                }
            calls.append(
                ToolCall(
                    id=item.call_id,
                    name=item.name,
                    arguments=arguments,
                    argument_error=argument_error,
                )
            )
        parsed = getattr(response, "output_parsed", None)
        content = (
            parsed.model_dump(mode="json")
            if parsed is not None
            else getattr(response, "output_text", None)
        )
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
        settings = require_provider_settings()
        return AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            max_retries=0,
        )
