import asyncio
from types import SimpleNamespace

from mock_agent.baseline import BaselineRuntime
from mock_agent.contract import EventKind, ExitStatus, RuntimeRequest, TerminationReason
from mock_agent.model import ModelReply, ModelRequest, OpenAIModelClient


class FinalReplyModel:
    def __init__(self):
        self.requests = []

    async def respond(self, request):
        self.requests.append(request)
        return ModelReply(
            content="Baseline final response.",
            usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
        )


class FakeResponses:
    def __init__(self):
        self.create_calls = []

    async def create(self, **values):
        self.create_calls.append(values)
        return SimpleNamespace(
            id="baseline-response",
            status="completed",
            output=[],
            output_text="Direct baseline response.",
            usage=SimpleNamespace(input_tokens=4, output_tokens=2, total_tokens=6),
        )


def test_baseline_runtime_uses_the_contract_without_emitting_plan_events():
    model = FinalReplyModel()
    emitted = []
    outcome = asyncio.run(
        BaselineRuntime(model_client=model).run(
            RuntimeRequest(
                task_id="sales.zoom_calendar_conflict",
                model_name="baseline-test",
                max_steps=3,
            ),
            event_sink=emitted.append,
        )
    )

    assert outcome.status is ExitStatus.COMPLETED
    assert outcome.termination_reason is TerminationReason.GOAL_COMPLETED
    assert outcome.final_response == "Baseline final response."
    assert outcome.usage == {
        "input_tokens": 5,
        "output_tokens": 3,
        "total_tokens": 8,
    }
    assert [event.kind for event in outcome.events] == [
        EventKind.MODEL_TURN,
        EventKind.COMPLETION,
    ]
    assert emitted == list(outcome.events)
    assert model.requests[0].role == "baseline"
    assert model.requests[0].tools
    assert all(
        event.kind not in {EventKind.PLAN_CREATED, EventKind.STEP_STARTED}
        for event in outcome.events
    )


def test_openai_model_client_uses_unstructured_responses_for_the_baseline():
    responses = FakeResponses()
    client = OpenAIModelClient(client=SimpleNamespace(responses=responses))

    reply = asyncio.run(
        client.respond(
            ModelRequest(
                role="baseline",
                model_name="baseline-test",
                instructions="Solve directly.",
                input=({"role": "user", "content": "Do the task."},),
            )
        )
    )

    assert reply.content == "Direct baseline response."
    assert reply.usage == {
        "input_tokens": 4,
        "output_tokens": 2,
        "total_tokens": 6,
    }
    assert len(responses.create_calls) == 1
    assert "text_format" not in responses.create_calls[0]
