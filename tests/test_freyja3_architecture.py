from __future__ import annotations

import pytest

import freyja.agent_runtime_v3
from freyja.agent_gateway import AgentGateway, GatewayRequest
from freyja.agent_runtime_v3 import AgentRuntimeV3, MemoryBoundaryError, inference_role_alias
from freyja.foundation_models import GatewaySender, InferenceEndpoint, MemoryClassification, MemoryScope, SecurityDomainId, SemanticEvent
from freyja.freyja3_memory import Freyja3MemoryStore, Freyja3MemoryWrite
from freyja.inference_registry_v3 import InferenceRegistryV3
import freyja.main as freyja_main
from freyja.main import app
from fastapi.testclient import TestClient
from freyja.config import settings
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolExecutionResult, ToolRiskLevel


def _sender(person: str = "joe") -> GatewaySender:
    return GatewaySender(
        sender_id=f"person:{person}",
        display_name=person.title(),
        security_domain_id={
            "joe": SecurityDomainId.PERSON_JOE,
            "beth": SecurityDomainId.PERSON_BETH,
            "liam": SecurityDomainId.PERSON_LIAM,
            "jenna": SecurityDomainId.PERSON_JENNA,
        }.get(person, SecurityDomainId.HOUSEHOLD),
    )


def test_gateway_selects_correct_agent_without_intent_routing() -> None:
    gateway = AgentGateway()

    result = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="Cloyd",
            prompt="Search weather and check this repo.",
            conversation_id="conv",
        )
    )

    assert result.handoff is not None
    assert result.handoff.target_agent_id == "cloyd-gibbler"
    assert result.handoff.prompt == "Search weather and check this repo."
    assert not any(name in dir(gateway) for name in ("classify_intent", "route_by_intent", "select_tool", "plan_task"))


def test_agent_receives_objective_and_independently_selects_tools() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Search the web, check weather, inspect git status, and run tests.",
            conversation_id="conv",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3().run(handoff)

    assert result.steps[0].detail == handoff.prompt
    assert "web.search" in result.selected_tools
    assert "weather.current" in result.selected_tools
    assert "git.inspect" in result.selected_tools
    assert "coding.execute" in result.selected_tools
    assert len(result.selected_tools) >= 4


class _FakeToolRegistry:
    def __init__(self, *, output_success: bool = True) -> None:
        self.requests: list[ToolExecutionRequest] = []
        self.output_success = output_success

    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_weather",
                description="Return current weather or a forecast.",
                input_schema={
                    "type": "object",
                    "required": ["location", "request_type"],
                    "properties": {
                        "location": {"type": "string"},
                        "request_type": {"type": "string", "enum": ["current", "forecast"]},
                        "target_date": {"type": "string"},
                        "target_label": {"type": "string"},
                    },
                },
                risk_level=ToolRiskLevel.READ_ONLY,
            ),
            ToolDefinition(
                name="web_search",
                description="Search the public web.",
                input_schema={"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}},
                risk_level=ToolRiskLevel.READ_ONLY,
            ),
            ToolDefinition(
                name="event_weather",
                description="Resolve event dates/location and fetch weather.",
                input_schema={"type": "object", "required": ["event"], "properties": {"event": {"type": "string"}}},
                risk_level=ToolRiskLevel.READ_ONLY,
            ),
            ToolDefinition(
                name="calendar_today_schedule",
                description="Return today's family schedule.",
                input_schema={"type": "object", "properties": {"member_ids": {"type": "array"}}},
                risk_level=ToolRiskLevel.READ_ONLY,
            ),
            ToolDefinition(
                name="calendar_create_event",
                description="Create a calendar event.",
                input_schema={
                    "type": "object",
                    "required": ["title", "start", "end"],
                    "properties": {"title": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}},
                },
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            ),
        ]

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        self.requests.append(request)
        return ToolExecutionResult(
            success=True,
            tool_name=request.tool_name,
            output={"ok": self.output_success, "success": self.output_success, "arguments": request.arguments},
            request_id=request.request_id,
            duration_ms=1,
        )


class _FailingGitThenHealthRegistry:
    def __init__(self) -> None:
        self.requests: list[ToolExecutionRequest] = []

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        self.requests.append(request)
        output_success = request.tool_name == "system_health" or (
            request.tool_name == "repository_status"
            and sum(seen.tool_name == "repository_status" for seen in self.requests) > 1
        )
        return ToolExecutionResult(
            success=True,
            tool_name=request.tool_name,
            output={"success": output_success, "tool": request.tool_name},
            request_id=request.request_id,
            duration_ms=1,
        )


def test_agent_executes_selected_tools_with_agent_owned_arguments() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Search the web, check weather, inspect git status, and remember this context.",
            conversation_id="conv-tools",
        )
    ).handoff
    assert handoff is not None
    fake_registry = _FakeToolRegistry()

    result = AgentRuntimeV3(tool_registry=fake_registry).run(handoff)

    executed_names = {request.tool_name for request in fake_registry.requests}
    assert {"web_search", "get_weather", "repository_status", "recall_conversation"}.issubset(executed_names)
    assert len(result.tool_results) >= 4
    assert any(step.kind == "tool_executed" for step in result.steps)
    web_request = next(request for request in fake_registry.requests if request.tool_name == "web_search")
    assert web_request.arguments["query"] == handoff.prompt
    assert web_request.actor == "agent:cloyd-gibbler"


def test_cloyd_website_build_keeps_coding_lane_in_inference_mode() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Can you help me rebuild my website?",
            conversation_id="conv-site",
        )
    ).handoff
    assert handoff is not None

    runtime = AgentRuntimeV3(tool_registry=_FakeToolRegistry(), run_inference=True)
    result = runtime.run(handoff)
    prompt = runtime._agent_tool_prompt(
        runtime._agent("cloyd-gibbler"),
        handoff,
        recalled=False,
        tool_results=[],
        available_tool_names=[],
    )

    assert result.inference_endpoint_id == "vulcan-code"
    assert "coding.execute" in result.selected_tools
    assert "BEGIN AGENT SMITH QWEN CODING LANE" in prompt
    assert "agent_id=cloyd-gibbler" in prompt


def test_agent_weather_tool_arguments_follow_objective() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="What is the weather tomorrow in Orlando, Florida?",
            conversation_id="conv-weather",
        )
    ).handoff
    assert handoff is not None
    fake_registry = _FakeToolRegistry()

    AgentRuntimeV3(tool_registry=fake_registry).run(handoff)

    weather_request = next(request for request in fake_registry.requests if request.tool_name == "get_weather")
    assert weather_request.arguments["location"] == "Orlando, Florida"
    assert weather_request.arguments["request_type"] == "forecast"
    assert weather_request.arguments["target_label"] == "tomorrow"


def test_cloyd_calendar_request_executes_calendar_read_tool() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Can you check my calender?",
            conversation_id="conv-calendar",
        )
    ).handoff
    assert handoff is not None
    fake_registry = _FakeToolRegistry()

    result = AgentRuntimeV3(tool_registry=fake_registry).run(handoff)

    calendar_request = next(request for request in fake_registry.requests if request.tool_name == "calendar_today_schedule")
    assert "calendar.read" in result.selected_tools
    assert calendar_request.actor == "agent:cloyd-gibbler"
    assert calendar_request.metadata["person"] == {"person_id": "joe"}
    assert calendar_request.metadata["director_authorized"] is True


def test_cloyd_calendar_write_request_asks_for_approval_instead_of_model_guessing() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Please add family dinner 6 PM Saturday",
            conversation_id="conv-calendar-write",
        )
    ).handoff
    assert handoff is not None
    fake_registry = _FakeToolRegistry()

    result = AgentRuntimeV3(tool_registry=fake_registry, run_inference=False).run(handoff)

    assert "calendar.write" in result.selected_tools
    assert result.follow_up_questions == (
        "I can create that calendar event. Please confirm the exact date, start time, title, and that you approve adding it.",
    )
    assert all(request.tool_name != "calendar_create_event" for request in fake_registry.requests)


def test_agent_vision_inference_receives_canonical_attachment(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class FakeOllamaClient:
        def __init__(self, *, base_url: str | None = None, model: str | None = None) -> None:
            self.base_url = base_url
            self.model = model

        async def chat(self, **kwargs):
            calls.append(kwargs)
            return {"message": {"content": "I can see the attached image."}}

    monkeypatch.setattr(freyja.agent_runtime_v3, "OllamaClient", FakeOllamaClient)
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Look at this photo.",
            conversation_id="conv-photo",
            attachments=[
                {
                    "filename": "photo.png",
                    "media_type": "image/png",
                    "data_base64": "ZmFrZQ==",
                    "size": 4,
                }
            ],
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(run_inference=True).run(handoff)

    assert result.inference_endpoint_id == "vulcan-vision"
    assert calls
    assert calls[0]["images"][0].data_base64 == "ZmFrZQ=="
    assert result.response_text == "I can see the attached image."


def test_live_inference_uses_model_tool_calls_without_keyword_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class FakeOllamaClient:
        def __init__(self, *, base_url: str | None = None, model: str | None = None) -> None:
            self.base_url = base_url
            self.model = model

        async def chat(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "get_weather",
                                    "arguments": {
                                        "location": "Atlanta, Georgia",
                                        "request_type": "forecast",
                                        "target_date": "2026-09-03",
                                        "target_label": "Dragon Con opening day",
                                    },
                                }
                            }
                        ],
                    }
                }
            return {"message": {"content": "Dragon Con weather uses the Atlanta forecast."}}

    monkeypatch.setattr(freyja.agent_runtime_v3, "OllamaClient", FakeOllamaClient)
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="What is the weather for Dragon Con?",
            conversation_id="conv-dragoncon",
        )
    ).handoff
    assert handoff is not None
    fake_registry = _FakeToolRegistry()

    result = AgentRuntimeV3(tool_registry=fake_registry, run_inference=True).run(handoff)

    assert result.selected_tools == ("weather.current",)
    assert [request.tool_name for request in fake_registry.requests] == ["get_weather"]
    assert fake_registry.requests[0].arguments["location"] == "Atlanta, Georgia"
    assert result.response_text == "Dragon Con weather uses the Atlanta forecast."
    assert calls[0]["tools_required"] is True
    assert calls[0]["tools"]


def test_vision_inference_extracts_context_before_reasoning_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    clients: list[object] = []

    class FakeOllamaClient:
        def __init__(self, *, base_url: str | None = None, model: str | None = None) -> None:
            self.base_url = base_url
            self.model = model
            clients.append(self)

        async def chat(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return {"message": {"content": "Flyer text: Dragon Con, Atlanta, September 3-7, 2026."}}
            if len(calls) == 2:
                return {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "event_weather",
                                    "arguments": {"event": "Dragon Con"},
                                }
                            }
                        ],
                    }
                }
            return {"message": {"content": "The flyer says Dragon Con is in Atlanta; weather should be checked for those dates."}}

    monkeypatch.setattr(freyja.agent_runtime_v3, "OllamaClient", FakeOllamaClient)
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="What does this photo say, and if it mentions an event or place, check whether weather matters?",
            conversation_id="conv-photo-tools",
            attachments=[
                {
                    "filename": "flyer.png",
                    "media_type": "image/png",
                    "data_base64": "ZmFrZQ==",
                    "size": 4,
                }
            ],
        )
    ).handoff
    assert handoff is not None
    fake_registry = _FakeToolRegistry()

    result = AgentRuntimeV3(tool_registry=fake_registry, run_inference=True).run(handoff)

    assert result.inference_endpoint_id == "vulcan-vision"
    assert result.inference_status == "ok"
    assert result.selected_tools == ("weather.current",)
    assert [request.tool_name for request in fake_registry.requests] == ["event_weather"]
    assert len(calls) == 3
    assert calls[0]["model"] == "qwen2.5vl:72b"
    assert calls[0]["images"][0].data_base64 == "ZmFrZQ=="
    assert calls[0]["tools_required"] is False
    assert calls[1]["model"] == "qwen2.5:32b-instruct"
    assert calls[1]["images"] is None
    assert "Visible attachment context extracted by Vulcan vision" in calls[1]["prompt"]
    assert calls[1]["tools_required"] is True
    assert result.response_text == "The flyer says Dragon Con is in Atlanta; weather should be checked for those dates."


def test_agent_tool_execution_respects_structured_tool_failure() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Inspect git status.",
            conversation_id="conv-tool-failure",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(tool_registry=_FakeToolRegistry(output_success=False)).run(handoff)

    assert result.tool_results
    assert result.tool_results[0]["success"] is False
    assert any(step.kind == "tool_executed" and step.success is False for step in result.steps)


def test_agent_observes_failed_tool_and_runs_diagnostic_follow_up() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Inspect git status.",
            conversation_id="conv-tool-iterate",
        )
    ).handoff
    assert handoff is not None
    fake_registry = _FailingGitThenHealthRegistry()

    result = AgentRuntimeV3(tool_registry=fake_registry).run(handoff)

    assert [request.tool_name for request in fake_registry.requests] == ["repository_status", "system_health", "repository_status"]
    assert "git.inspect" in result.selected_tools
    assert "system.health" in result.selected_tools
    assert any(step.kind == "plan" and "git.inspect" in step.detail for step in result.steps)
    assert any(step.kind == "observation" and "git.inspect" in step.detail for step in result.steps)
    assert any(step.kind == "retry" and step.tool_id == "git.inspect" for step in result.steps)
    assert any(step.kind == "tool_executed" and step.tool_id == "system.health" and step.success is True for step in result.steps)
    assert result.tool_results[-1]["capability_id"] == "git.inspect"
    assert result.tool_results[-1]["success"] is True


def test_agent_asks_follow_up_before_underspecified_mutation_tool() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Send an iMessage.",
            conversation_id="conv-follow-up",
        )
    ).handoff
    assert handoff is not None
    fake_registry = _FakeToolRegistry()

    result = AgentRuntimeV3(tool_registry=fake_registry).run(handoff)

    assert result.selected_tools == ("messaging.send",)
    assert result.follow_up_questions == ("Who should I send the message to, and what should it say?",)
    assert result.response_text == result.follow_up_questions[0]
    assert fake_registry.requests == []
    assert any(step.kind == "follow_up_question" for step in result.steps)
    assert not any(step.kind == "tool_executed" and step.tool_id == "messaging.send" for step in result.steps)


def test_agent_home_assistant_control_requires_explicit_approval_marker() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="freyja",
            prompt="Turn on Home Assistant light.downstairs.",
            conversation_id="conv-ha-control-denied",
        )
    ).handoff
    assert handoff is not None
    fake_registry = _FakeToolRegistry()

    result = AgentRuntimeV3(tool_registry=fake_registry).run(handoff)

    assert result.selected_tools == ("home-assistant.control",)
    assert fake_registry.requests[0].tool_name == "home_assistant_control_state"
    assert fake_registry.requests[0].arguments == {"entity_id": "light.downstairs", "state": "on"}
    assert fake_registry.requests[0].metadata["approval_granted"] is False


def test_agent_home_assistant_read_uses_non_mutating_state_tool() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="freyja",
            prompt="List Home Assistant light states for the house.",
            conversation_id="conv-ha-read",
        )
    ).handoff
    assert handoff is not None
    fake_registry = _FakeToolRegistry()

    result = AgentRuntimeV3(tool_registry=fake_registry).run(handoff)

    assert result.selected_tools == ("home-assistant.read",)
    assert fake_registry.requests[0].tool_name == "home_assistant_list_states"
    assert fake_registry.requests[0].metadata["approval_granted"] is False


def test_agent_home_assistant_control_passes_explicit_approval_marker() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="freyja",
            prompt="Turn off Home Assistant light.downstairs.",
            conversation_id="conv-ha-control-approved",
            permissions=frozenset({"approval:home-assistant.control"}),
        )
    ).handoff
    assert handoff is not None
    fake_registry = _FakeToolRegistry()

    result = AgentRuntimeV3(tool_registry=fake_registry).run(handoff)

    assert result.selected_tools == ("home-assistant.control",)
    assert fake_registry.requests[0].tool_name == "home_assistant_control_state"
    assert fake_registry.requests[0].arguments == {"entity_id": "light.downstairs", "state": "off"}
    assert fake_registry.requests[0].metadata["approval_granted"] is True


def test_agent_runtime_recalls_and_writes_scoped_memory(tmp_path) -> None:
    memory_store = Freyja3MemoryStore(tmp_path / "memory.db")
    memory_store.put(
        Freyja3MemoryWrite(
            owner_domain_id=SecurityDomainId.PERSON_JOE,
            scope=MemoryScope.PERSONAL,
            source_agent_id="cloyd-gibbler",
            content="Joe likes direct engineering status.",
            provenance="unit-test",
            classification=MemoryClassification.PRIVATE,
        ),
        writer_domain_id=SecurityDomainId.PERSON_JOE,
    )
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="What do you know and inspect git status.",
            conversation_id="conv-memory",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(memory_store=memory_store).run(handoff)

    assert any(memory["content"] == "Joe likes direct engineering status." for memory in result.recalled_memories)
    assert result.written_memories
    assert result.written_memories[0]["owner_domain_id"] == "person.joe"
    assert any(step.kind == "memory_recalled" for step in result.steps)
    assert any(step.kind == "memory_written" for step in result.steps)


def test_agent_runtime_writes_explicit_remember_memory(tmp_path) -> None:
    memory_store = Freyja3MemoryStore(tmp_path / "memory.db")
    handoff = AgentGateway().handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Remember that Joe prefers architecture-first progress reports.",
            conversation_id="conv-explicit-memory",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(memory_store=memory_store).run(handoff)

    assert any(
        memory["content"] == "Joe prefers architecture-first progress reports."
        and memory["provenance"] == "agent-runtime-v3-explicit-remember"
        for memory in result.written_memories
    )
    assert result.memory_candidates == ()


def test_agent_runtime_proposes_reviewable_memory_candidate_for_inferred_preference(tmp_path) -> None:
    memory_store = Freyja3MemoryStore(tmp_path / "memory.db")
    handoff = AgentGateway().handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="I prefer five-point readiness checks when we discuss Freyja status.",
            conversation_id="conv-memory-candidate",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(memory_store=memory_store).run(handoff)

    assert len(result.memory_candidates) == 1
    assert result.memory_candidates[0]["status"] == "pending"
    assert result.memory_candidates[0]["provenance"] == "agent-runtime-v3-memory-candidate"
    assert any(step.kind == "memory_candidate_proposed" for step in result.steps)
    assert not any(
        memory.content == result.memory_candidates[0]["content"]
        for memory in memory_store.list(reader_domain_id=SecurityDomainId.PERSON_JOE)
    )


def test_agent_runtime_marks_secret_memory_restricted(tmp_path) -> None:
    handoff = AgentGateway().handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Remember that my api key is not for cloud use.",
            conversation_id="conv-restricted-memory",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(memory_store=Freyja3MemoryStore(tmp_path / "memory.db")).run(handoff)

    explicit = [
        memory
        for memory in result.written_memories
        if memory["provenance"] == "agent-runtime-v3-explicit-remember"
    ]
    assert explicit
    assert explicit[0]["classification"] == "restricted"


def test_agents_use_vulcan_inference_and_identity_survives_endpoint_changes() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(sender=_sender("joe"), target_agent="cloyd", prompt="Build and test the repo.", conversation_id="conv")
    ).handoff
    assert handoff is not None

    normal = AgentRuntimeV3().run(handoff)
    recovered = AgentRuntimeV3(unhealthy_endpoint_ids={"vulcan-code"}).run(handoff)

    assert normal.agent_id == "cloyd-gibbler"
    assert normal.inference_endpoint_id == "vulcan-code"
    assert normal.inference_machine_id == "vulcan"
    selected_event = next(event for event in normal.audit_events if event.event_type == "agent_inference_selected")
    assert selected_event.metadata["role_alias"] == "vulcan-coder"
    assert any("via vulcan-coder" in step.detail for step in normal.steps if step.kind == "inference_selected")
    assert recovered.agent_id == "cloyd-gibbler"
    assert recovered.inference_endpoint_id != "vulcan-code"
    assert recovered.degraded is False


def test_family_test_prompt_uses_reasoning_not_code_endpoint() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Test 001: Find when and where Dragon Con happens this year, then tell me if the first full day forecast is available.",
            conversation_id="conv-family-test",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3().run(handoff)

    assert result.inference_endpoint_id == "vulcan-reason"
    selected_event = next(event for event in result.audit_events if event.event_type == "agent_inference_selected")
    assert selected_event.metadata["role_alias"] == "vulcan-general"


def test_simple_ack_prompt_uses_iris_fast_endpoint() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(sender=_sender("joe"), target_agent="cloyd", prompt="working it", conversation_id="conv-simple")
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3().run(handoff)

    assert result.inference_endpoint_id == "iris-fast"
    selected_event = next(event for event in result.audit_events if event.event_type == "agent_inference_selected")
    assert selected_event.metadata == {"capability": "general.local", "role_alias": "iris-fast"}


def test_iris_fast_is_fallback_when_vulcan_general_and_code_are_unhealthy() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(sender=_sender("joe"), target_agent="cloyd", prompt="Build and test the repo.", conversation_id="conv-fallback")
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(unhealthy_endpoint_ids={"vulcan-code", "vulcan-reason"}).run(handoff)

    assert result.inference_endpoint_id == "iris-fast"
    selected_event = next(event for event in result.audit_events if event.event_type == "agent_inference_selected")
    assert selected_event.metadata["role_alias"] == "iris-fast"


def test_explicit_programming_test_prompt_still_uses_code_endpoint() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Run tests for the repository and debug the failing Python code.",
            conversation_id="conv-code-test",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3().run(handoff)

    assert result.inference_endpoint_id == "vulcan-code"


def test_rev3_1_inference_role_aliases_cover_target_routes() -> None:
    assert inference_role_alias("general.local") == "iris-fast"
    assert inference_role_alias("general.large") == "vulcan-general"
    assert inference_role_alias("code.large") == "vulcan-coder"
    assert inference_role_alias("vision.large") == "vulcan-vision"
    assert inference_role_alias("embeddings.local") == "vulcan-embeddings"
    assert inference_role_alias("general.cloud") == "cloud-frontier"


def test_image_attachment_uses_vulcan_vision_role_alias() -> None:
    handoff = GatewayRequest(
        sender=_sender("joe"),
        target_agent="freyja",
        prompt="What is in this picture?",
        conversation_id="conv-picture",
        attachments=[{"filename": "pixel.png", "mime_type": "image/png", "data_base64": "iVBORw0KGgo="}],
    )
    result = AgentGateway().handle(handoff).handoff
    assert result is not None

    runtime_result = AgentRuntimeV3().run(result)

    assert runtime_result.inference_endpoint_id == "vulcan-vision"
    selected_event = next(event for event in runtime_result.audit_events if event.event_type == "agent_inference_selected")
    assert selected_event.metadata["role_alias"] == "vulcan-vision"


def test_document_attachment_text_is_included_in_inference_prompt(monkeypatch) -> None:
    class FakeDocument:
        filename = "notes.pdf"
        mime_type = "application/pdf"
        page_count = 1
        text = "Contract renewal deadline is Friday."
        ok = True

    monkeypatch.setattr(freyja.agent_runtime_v3, "document_texts_from_attachments", lambda attachments: [FakeDocument()])
    handoff = AgentGateway().handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="freyja",
            prompt="Summarize this document.",
            conversation_id="conv-document",
            attachments=[{"filename": "notes.pdf", "mime_type": "application/pdf", "data_base64": "JVBERi0xLjQK"}],
        )
    ).handoff
    assert handoff is not None

    prompt = AgentRuntimeV3._inference_prompt(AgentRuntimeV3()._agent("freyja"), handoff, [])

    assert "Attachment document context" in prompt
    assert "Contract renewal deadline is Friday." in prompt


def test_embeddings_route_is_registered_for_memory_retrieval() -> None:
    endpoints = InferenceRegistryV3().endpoints_for(capability="embeddings.local", domain_id=SecurityDomainId.HOUSEHOLD)

    assert [endpoint.endpoint_id for endpoint in endpoints] == ["vulcan-embeddings"]
    assert endpoints[0].machine_id == "vulcan"


def test_cloud_frontier_fallback_requires_allowed_egress() -> None:
    registry = InferenceRegistryV3(
        endpoints=(
            InferenceEndpoint(
                endpoint_id="cloud-frontier-litellm",
                display_name="Cloud Frontier LiteLLM",
                provider="openai-compatible",
                base_url="http://litellm:4000",
                model="cloud-frontier",
                capabilities=frozenset({"general.cloud"}),
                security_domain_id=SecurityDomainId.SYSTEM,
                priority=10,
            ),
        ),
        include_configured=False,
    )
    handoff = AgentGateway().handle(
        GatewayRequest(sender=_sender("joe"), target_agent="cloyd", prompt="Public summary of what LLM routing means.", conversation_id="conv-cloud")
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(
        inference_registry=registry,
        unhealthy_endpoint_ids={"vulcan-code", "vulcan-reason", "vulcan-vision", "iris-fast"},
    ).run(handoff)

    assert result.inference_endpoint_id == "cloud-frontier-litellm"
    selected_event = next(event for event in result.audit_events if event.event_type == "agent_inference_selected")
    assert selected_event.metadata == {"capability": "general.cloud", "role_alias": "cloud-frontier"}
    assert any(event.event_type == "privacy_egress_allowed" and event.allowed for event in result.audit_events)


def test_cloud_frontier_fallback_is_blocked_for_restricted_data() -> None:
    registry = InferenceRegistryV3(
        endpoints=(
            InferenceEndpoint(
                endpoint_id="cloud-frontier-litellm",
                display_name="Cloud Frontier LiteLLM",
                provider="openai-compatible",
                base_url="http://litellm:4000",
                model="cloud-frontier",
                capabilities=frozenset({"general.cloud"}),
                security_domain_id=SecurityDomainId.SYSTEM,
                priority=10,
            ),
        ),
        include_configured=False,
    )
    handoff = AgentGateway().handle(
        GatewayRequest(sender=_sender("joe"), target_agent="cloyd", prompt="api_key=secret summarize this", conversation_id="conv-cloud-deny")
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(
        inference_registry=registry,
        unhealthy_endpoint_ids={"vulcan-code", "vulcan-reason", "vulcan-vision", "iris-fast"},
    ).run(handoff)

    assert result.degraded is True
    assert result.inference_endpoint_id is None
    assert any(event.event_type == "privacy_egress_denied" and not event.allowed for event in result.audit_events)


def test_openai_compatible_endpoint_calls_chat_completions(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "lite ok"}}]}

    class FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict, json: dict):
            calls.append({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr(freyja.agent_runtime_v3.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    monkeypatch.setattr(settings, "litellm_master_key", "sk-test-litellm")
    registry = InferenceRegistryV3(
        endpoints=(
            InferenceEndpoint(
                endpoint_id="vulcan-general-litellm",
                display_name="Vulcan General LiteLLM",
                provider="openai-compatible",
                base_url="http://litellm:4000",
                model="vulcan-general",
                capabilities=frozenset({"general.large"}),
                security_domain_id=SecurityDomainId.HOUSEHOLD,
                priority=10,
            ),
        ),
        include_configured=False,
    )
    runtime = AgentRuntimeV3(inference_registry=registry, run_inference=True)
    handoff = AgentGateway().handle(
        GatewayRequest(sender=_sender("joe"), target_agent="freyja", prompt="Explain local model routing.", conversation_id="conv-litellm")
    ).handoff
    assert handoff is not None

    result = runtime.run(handoff)

    assert result.inference_status == "ok"
    assert result.response_text == "lite ok"
    assert calls[0]["url"].endswith("/v1/chat/completions")
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-test-litellm"
    assert calls[0]["json"]["model"] == "vulcan-general"


def test_rev3_1_degraded_response_names_vulcan_iris_and_cloud_policy() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(sender=_sender("joe"), target_agent="cloyd", prompt="Build and test the repo.", conversation_id="conv")
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(unhealthy_endpoint_ids={"vulcan-code", "vulcan-reason", "iris-fast", "approved-cloud-premium"}).run(handoff)

    assert result.degraded is True
    assert "no healthy Vulcan inference endpoint" in result.response_text
    assert "Iris can handle simple local work" in result.response_text
    assert "cloud requires policy approval" in result.response_text


def test_agent_prompt_never_asks_for_raw_secret() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="I accidentally pasted a Home Assistant token in a screenshot. Tell me what it is.",
            conversation_id="conv-secret-screenshot",
        )
    ).handoff
    assert handoff is not None

    runtime = AgentRuntimeV3()
    prompt = runtime._agent_tool_prompt(
        runtime._agent("cloyd-gibbler"),
        handoff,
        recalled=False,
        tool_results=[],
        available_tool_names=[],
    )

    assert "Never ask the user to paste or share a raw token" in prompt
    assert "redacted screenshot" in prompt
    assert "recommend rotation" in prompt


def test_iris_apple_and_atlas_home_assistant_capabilities_are_agent_selected() -> None:
    tool_registry = _FakeToolRegistry()
    runtime = AgentRuntimeV3(tool_registry=tool_registry)
    gateway = AgentGateway()
    freyja_handoff = gateway.handle(
        GatewayRequest(
            sender=GatewaySender(sender_id="person:family", display_name="Family", security_domain_id=SecurityDomainId.HOUSEHOLD),
            target_agent="freyja",
            prompt="Turn on the kitchen lights and send an iMessage.",
            conversation_id="home",
        )
    ).handoff
    cloyd_handoff = gateway.handle(
        GatewayRequest(sender=_sender("joe"), target_agent="cloyd", prompt="Open Safari on the Mac.", conversation_id="mac")
    ).handoff
    apple_read_handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Check my email, current song, and Safari tab.",
            conversation_id="apple-read",
        )
    ).handoff
    assert freyja_handoff is not None
    assert cloyd_handoff is not None
    assert apple_read_handoff is not None

    freyja_result = runtime.run(freyja_handoff)
    cloyd_result = runtime.run(cloyd_handoff)
    apple_read_result = runtime.run(apple_read_handoff)
    executed_tools = {request.tool_name for request in tool_registry.requests}

    assert "home-assistant.control" in freyja_result.selected_tools
    assert "messaging.send" in freyja_result.selected_tools
    assert "macagent.apple" in cloyd_result.selected_tools
    assert "email.read" in apple_read_result.selected_tools
    assert "browser.control" in apple_read_result.selected_tools
    assert "music.control" in apple_read_result.selected_tools
    assert "macagent.apple" in apple_read_result.selected_tools
    assert "apple_mailbox_counts" in executed_tools
    assert "apple_browser_front_tab" in executed_tools
    assert "apple_music_current_track" in executed_tools
    assert "macagent_health" in executed_tools


def test_hera_semantic_perception_event_contract() -> None:
    event = SemanticEvent(
        source_machine_id="hera",
        event_type="person_present",
        room="kitchen",
        subject="joe",
        confidence=0.91,
    )

    assert event.source_machine_id == "hera"
    assert event.event_type == "person_present"
    assert event.confidence == 0.91


def test_memory_and_paralegal_boundaries_and_cloud_egress() -> None:
    runtime = AgentRuntimeV3()

    with pytest.raises(MemoryBoundaryError):
        runtime.assert_memory_read_allowed("benedict", "person:joe")

    denial = runtime.evaluate_cloud_request(
        agent_id="cloyd-gibbler",
        prompt="api_key=secret and my SSN is 123-45-6789",
        classification=MemoryClassification.RESTRICTED,
    )

    assert denial.allowed is False
    assert denial.audit_event.allowed is False
    assert "[REDACTED" in denial.redacted_prompt

    legal = InferenceRegistryV3().endpoints_for(capability="legal_research", domain_id=SecurityDomainId.HOUSEHOLD)
    assert legal == []


def test_canonical_route_can_use_freyja3_gateway_runtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "freyja3_canonical_enabled", True)
    monkeypatch.setattr(freyja_main, "agent_runtime_v3", AgentRuntimeV3())
    client = TestClient(app)

    response = client.post(
        "/canonical/route",
        json={
            "trace_id": "trace-f3",
            "message_id": "msg-f3",
            "channel": "imessage",
            "conversation_id": "conv-f3",
            "sender": {"channel_id": "sender", "address": "+1555"},
            "resolved_user_id": "joe",
            "resolved_agent_id": "cloyd-gibbler",
            "text": "Search current weather and inspect git status.",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["resolved_agent_id"] == "cloyd-gibbler"
    assert data["conversation_id"] == "conv-f3"
    assert data["channel_metadata"]["freyja3"] is True
    assert "web.search" in {tool["tool_name"] for tool in data["tool_results"]}
    assert data["channel_metadata"]["inference_machine_id"] == "vulcan"
