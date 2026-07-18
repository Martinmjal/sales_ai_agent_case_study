import asyncio
from types import SimpleNamespace

import pytest

from sales_agent.adapter import ToolSpec
from sales_agent.model import ModelRequest, OpenAIModelClient, ProviderFailure


class TransientProviderError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


def response(output=None):
    return SimpleNamespace(
        id="provider-response",
        status="completed",
        output=output or [],
        output_text="Done",
        output_parsed=None,
        usage=SimpleNamespace(input_tokens=2, output_tokens=1, total_tokens=3),
    )


def test_model_boundary_preserves_malformed_function_json_as_a_recoverable_call():
    class Responses:
        async def create(self, **_):
            return SimpleNamespace(
                id="malformed-response",
                status="completed",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        call_id="malformed-call",
                        name="zoom_list_meetings",
                        arguments="{not-json",
                    )
                ],
                output_text="",
                output_parsed=None,
                usage=SimpleNamespace(
                    input_tokens=2,
                    output_tokens=1,
                    total_tokens=3,
                ),
            )

    reply = asyncio.run(
        OpenAIModelClient(client=SimpleNamespace(responses=Responses())).respond(
            ModelRequest(
                role="executor",
                model_name="test-model",
                instructions="Use the tool.",
                input=({"role": "user", "content": "Inspect meetings."},),
                tools=(
                    ToolSpec(
                        name="zoom_list_meetings",
                        description="List meetings",
                        input_schema={"type": "object"},
                    ),
                ),
            )
        )
    )

    call = reply.tool_calls[0]
    assert call.id == "malformed-call"
    assert call.arguments == {}
    assert call.argument_error["type"] == "malformed_arguments_json"
    assert call.argument_error["raw_arguments"] == "{not-json"


def test_provider_timeout_rate_limit_and_server_retries_are_visible_and_bounded():
    class Responses:
        def __init__(self, values):
            self.values = iter(values)

        async def create(self, **_):
            value = next(self.values)
            if isinstance(value, BaseException):
                raise value
            return value

    request = ModelRequest(
        role="executor",
        model_name="test-model",
        instructions="Respond.",
        input=({"role": "user", "content": "Continue."},),
    )
    recovered = asyncio.run(
        OpenAIModelClient(
            client=SimpleNamespace(
                responses=Responses(
                    [TimeoutError("timed out"), TransientProviderError(429), response()]
                )
            ),
            retry_delays=(0, 0),
        ).respond(request)
    )

    assert [item["status_code"] for item in recovered.metadata["provider_retries"]] == [
        None,
        429,
    ]

    with pytest.raises(ProviderFailure) as caught:
        asyncio.run(
            OpenAIModelClient(
                client=SimpleNamespace(
                    responses=Responses(
                        [
                            TransientProviderError(500),
                            TransientProviderError(502),
                            TransientProviderError(503),
                        ]
                    )
                ),
                retry_delays=(0, 0),
            ).respond(request)
        )

    assert caught.value.transient is True
    assert len(caught.value.retries) == 2
    assert caught.value.error.status_code == 503
