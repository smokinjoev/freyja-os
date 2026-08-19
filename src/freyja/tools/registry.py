import asyncio
import logging
import time
import uuid
from typing import Any

from freyja.config import settings
from freyja.tools.errors import ToolDisabledError, ToolNotFoundError, ToolTimeoutError, ToolValidationError
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolExecutionResult, ToolImplementation

logger = logging.getLogger(__name__)

_SANITIZED_TERMS = {"api key", "authorization", "bearer", "sk-", "token", "password", "secret"}


def _sanitize_for_audit(value: Any) -> Any:
    """Recursively redact likely secrets from audit records."""
    if isinstance(value, dict):
        return {k: _sanitize_for_audit(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_audit(item) for item in value]
    if isinstance(value, str):
        lowered = value.lower()
        if any(term in lowered for term in _SANITIZED_TERMS):
            return "<redacted>"
        return value
    return value


def _safe_public_error(code: str, message: str | None) -> str:
    if code == "tool_not_found":
        return "Tool not found."
    if code == "tool_disabled":
        return "Tool is currently disabled."
    if code == "validation_error":
        return message or "Invalid tool arguments."
    if code == "tool_timeout":
        return "Tool execution timed out."
    if code == "authorization_denied":
        return "Tool authorization denied."
    return "Tool execution failed."


class ToolAuthorizationDecision:
    def __init__(self, *, allowed: bool, reason: str, required_permission: str | None = None) -> None:
        self.allowed = allowed
        self.reason = reason
        self.required_permission = required_permission

    def model_dump(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "required_permission": self.required_permission,
        }


class ToolRegistry:
    def __init__(self, default_timeout_seconds: int | None = None, audit_enabled: bool | None = None) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._implementations: dict[str, ToolImplementation] = {}
        self._enabled: bool = bool(getattr(settings, "tools_enabled", True))
        self._default_timeout_seconds = (
            default_timeout_seconds
            if default_timeout_seconds is not None
            else int(getattr(settings, "tools_default_timeout_seconds", 30))
        )
        self._audit_enabled = (
            audit_enabled if audit_enabled is not None else bool(getattr(settings, "tools_audit_log_enabled", True))
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def register(self, definition: ToolDefinition, implementation: ToolImplementation) -> None:
        name = definition.name
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = definition
        self._implementations[name] = implementation

    def unregister(self, name: str) -> bool:
        if name not in self._tools:
            return False
        del self._tools[name]
        del self._implementations[name]
        return True

    def list_tools(self, *, include_disabled: bool = False) -> list[ToolDefinition]:
        definitions = list(self._tools.values())
        if not include_disabled:
            definitions = [d for d in definitions if d.enabled]
        return definitions

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def validate_arguments(self, tool_name: str, arguments: dict[str, Any]) -> list[str]:
        definition = self._tools.get(tool_name)
        if definition is None:
            return [f"Tool '{tool_name}' not found"]
        if not definition.enabled:
            return [f"Tool '{tool_name}' is disabled"]
        schema = definition.input_schema or {}
        if not schema:
            return []
        return _validate_against_schema(arguments, schema)

    def normalize_arguments(self, tool_name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """Return conservative schema-aware argument normalizations.

        Only unambiguous enum aliases are normalized. Invalid or ambiguous
        values are returned as validation errors instead of being guessed.
        """
        definition = self._tools.get(tool_name)
        if definition is None:
            return dict(arguments), [f"Tool '{tool_name}' not found"]
        if not definition.enabled:
            return dict(arguments), [f"Tool '{tool_name}' is disabled"]
        schema = definition.input_schema or {}
        if not schema:
            return dict(arguments), []
        return _normalize_against_schema(arguments, schema)

    def authorize(self, definition: ToolDefinition, request: ToolExecutionRequest) -> ToolAuthorizationDecision:
        permission = definition.required_permission
        if not permission:
            return ToolAuthorizationDecision(allowed=True, reason="no explicit permission required")

        metadata = request.metadata or {}
        person = metadata.get("person") if isinstance(metadata.get("person"), dict) else {}
        principal = metadata.get("memory_principal") if isinstance(metadata.get("memory_principal"), dict) else {}
        person_id = str(person.get("person_id") or "").strip().lower()
        has_principal = bool(principal.get("client_type") and principal.get("client_subject"))

        if permission in {"household:home.read", "household:calendar.read"}:
            if person_id in {"joe", "beth", "family"}:
                resource = "household state" if permission == "household:home.read" else "household calendar"
                return ToolAuthorizationDecision(
                    allowed=True,
                    reason=f"principal {person_id} may read {resource}",
                    required_permission=permission,
                )
            if person_id:
                return ToolAuthorizationDecision(
                    allowed=False,
                    reason="canonical household principal required",
                    required_permission=permission,
                )
            if has_principal and metadata.get("director_authorized") is True:
                resource = "household state" if permission == "household:home.read" else "household calendar"
                return ToolAuthorizationDecision(
                    allowed=True,
                    reason=f"Director-authorized connector principal may read {resource}",
                    required_permission=permission,
                )
            return ToolAuthorizationDecision(
                allowed=False,
                reason="canonical household principal required",
                required_permission=permission,
            )

        if permission == "household:home.control":
            if person_id not in {"joe", "beth", "family"}:
                return ToolAuthorizationDecision(
                    allowed=False,
                    reason="canonical household principal required",
                    required_permission=permission,
                )
            if metadata.get("director_authorized") is not True:
                return ToolAuthorizationDecision(
                    allowed=False,
                    reason="Director authorization required",
                    required_permission=permission,
                )
            if metadata.get("approval_granted") is not True:
                return ToolAuthorizationDecision(
                    allowed=False,
                    reason="explicit approval required for household control",
                    required_permission=permission,
                )
            return ToolAuthorizationDecision(
                allowed=True,
                reason=f"principal {person_id} may control household state with approval",
                required_permission=permission,
            )

        if permission == "household:calendar.write":
            if person_id not in {"joe", "beth", "family"}:
                return ToolAuthorizationDecision(
                    allowed=False,
                    reason="canonical household principal required",
                    required_permission=permission,
                )
            if metadata.get("director_authorized") is not True:
                return ToolAuthorizationDecision(
                    allowed=False,
                    reason="Director authorization required",
                    required_permission=permission,
                )
            if metadata.get("approval_granted") is not True:
                return ToolAuthorizationDecision(
                    allowed=False,
                    reason="explicit approval required for calendar write",
                    required_permission=permission,
                )
            return ToolAuthorizationDecision(
                allowed=True,
                reason=f"principal {person_id} may write household calendar with approval",
                required_permission=permission,
            )

        if permission == "personal:memory.read":
            if person_id and person_id not in {"joe", "beth", "family"}:
                return ToolAuthorizationDecision(
                    allowed=False,
                    reason="canonical memory principal required",
                    required_permission=permission,
                )
            if has_principal and metadata.get("director_authorized") is True:
                return ToolAuthorizationDecision(
                    allowed=True,
                    reason="Director-authorized principal may read scoped memory",
                    required_permission=permission,
                )
            return ToolAuthorizationDecision(
                allowed=False,
                reason="trusted memory principal required",
                required_permission=permission,
            )

        if metadata.get("director_authorized") is True:
            return ToolAuthorizationDecision(
                allowed=True,
                reason="Director authorization present",
                required_permission=permission,
            )
        return ToolAuthorizationDecision(
            allowed=False,
            reason="Director authorization required",
            required_permission=permission,
        )

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        start = time.monotonic()
        name = request.tool_name
        try:
            if not self._enabled:
                return self._error_result(
                    request,
                    "tool_disabled",
                    "Tool execution is globally disabled.",
                    duration_ms=_elapsed_ms(start),
                )

            definition = self._tools.get(name)
            if definition is None:
                return self._error_result(
                    request,
                    "tool_not_found",
                    f"Tool '{name}' is not registered.",
                    duration_ms=_elapsed_ms(start),
                )

            if not definition.enabled:
                return self._error_result(
                    request,
                    "tool_disabled",
                    f"Tool '{name}' is disabled.",
                    duration_ms=_elapsed_ms(start),
                )

            normalized_arguments, normalization_errors = self.normalize_arguments(name, request.arguments)
            validation_errors = normalization_errors or self.validate_arguments(name, normalized_arguments)
            if validation_errors:
                return self._error_result(
                    request,
                    "validation_error",
                    "; ".join(validation_errors),
                    duration_ms=_elapsed_ms(start),
                )

            authorization = self.authorize(definition, request)
            if not authorization.allowed:
                result = self._error_result(
                    request,
                    "authorization_denied",
                    authorization.reason,
                    duration_ms=_elapsed_ms(start),
                )
                self._audit(request, result, internal_error=None)
                return result

            implementation = self._implementations.get(name)
            if implementation is None:
                return self._error_result(
                    request,
                    "tool_not_found",
                    f"Tool '{name}' has no implementation.",
                    duration_ms=_elapsed_ms(start),
                )

            timeout = definition.timeout_seconds or self._default_timeout_seconds
            normalized_request = request.model_copy(update={"arguments": normalized_arguments})
            output = await asyncio.wait_for(implementation(normalized_request), timeout=timeout)
            duration_ms = _elapsed_ms(start)
            result = ToolExecutionResult(
                success=True,
                tool_name=name,
                output=output if output is not None else {},
                request_id=request.request_id,
                duration_ms=duration_ms,
            )
            self._audit(request, result, internal_error=None)
            return result
        except asyncio.TimeoutError:
            duration_ms = _elapsed_ms(start)
            result = self._error_result(
                request,
                "tool_timeout",
                f"Tool '{name}' exceeded {timeout} second timeout.",
                duration_ms=duration_ms,
            )
            self._audit(request, result, internal_error=None)
            return result
        except Exception as exc:  # noqa: BLE001
            duration_ms = _elapsed_ms(start)
            result = self._error_result(
                request,
                "tool_error",
                str(exc),
                duration_ms=duration_ms,
            )
            self._audit(request, result, internal_error=str(exc))
            return result

    def set_enabled(self, name: str, enabled: bool) -> bool:
        definition = self._tools.get(name)
        if definition is None:
            return False
        definition.enabled = enabled
        return True

    def _error_result(
        self,
        request: ToolExecutionRequest,
        error_code: str,
        internal_message: str,
        duration_ms: int,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            success=False,
            tool_name=request.tool_name,
            output={},
            error_code=error_code,
            public_error_message=_safe_public_error(error_code, internal_message),
            duration_ms=duration_ms,
            request_id=request.request_id,
        )

    def _audit(
        self,
        request: ToolExecutionRequest,
        result: ToolExecutionResult,
        internal_error: str | None,
    ) -> None:
        if not self._audit_enabled:
            return
        record = {
            "event": "tool_execution",
            "request_id": request.request_id,
            "tool_name": request.tool_name,
            "actor": request.actor,
            "conversation_id": request.conversation_id,
            "success": result.success,
            "error_code": result.error_code,
            "duration_ms": result.duration_ms,
            "arguments": _sanitize_for_audit(request.arguments),
            "output": _sanitize_for_audit(result.output),
        }
        if internal_error:
            record["internal_error"] = _sanitize_for_audit(internal_error)
        logger.info(record)


class DisabledToolRegistry(ToolRegistry):
    """No-op registry returned when tools are globally disabled."""

    def __init__(self) -> None:
        super().__init__(audit_enabled=False)
        self._enabled = False

    def register(self, definition: ToolDefinition, implementation: ToolImplementation) -> None:
        return None

    def unregister(self, name: str) -> bool:
        return False

    def list_tools(self, *, include_disabled: bool = False) -> list[ToolDefinition]:
        return []

    def get_tool(self, name: str) -> ToolDefinition | None:
        return None

    def validate_arguments(self, tool_name: str, arguments: dict[str, Any]) -> list[str]:
        return ["Tool execution is globally disabled"]

    def normalize_arguments(self, tool_name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        return dict(arguments), ["Tool execution is globally disabled"]

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        return ToolExecutionResult(
            success=False,
            tool_name=request.tool_name,
            error_code="tool_disabled",
            public_error_message="Tool execution is globally disabled.",
            duration_ms=0,
            request_id=request.request_id,
        )

    def set_enabled(self, name: str, enabled: bool) -> bool:
        return False


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _validate_against_schema(arguments: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = set(schema.get("required", []))
    properties = schema.get("properties", {}) or {}

    for key in required:
        if key not in arguments:
            errors.append(f"Missing required argument: {key}")

    for key, value in arguments.items():
        prop = properties.get(key)
        if prop is None:
            errors.append(f"Unknown argument: {key}")
            continue
        expected = prop.get("type")
        if expected is None:
            pass
        elif not _type_matches(value, expected):
            errors.append(f"Argument '{key}' must be of type {expected}")
            continue
        enum = prop.get("enum")
        if enum is not None and value not in enum:
            errors.append(f"Argument '{key}' must be one of: {', '.join(map(str, enum))}")

    return errors


def _normalize_against_schema(arguments: dict[str, Any], schema: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    normalized = dict(arguments)
    errors: list[str] = []
    properties = schema.get("properties", {}) or {}

    for key, value in arguments.items():
        prop = properties.get(key)
        if prop is None:
            continue
        enum = prop.get("enum")
        if enum is None or value in enum:
            continue
        if not isinstance(value, str):
            continue
        replacement, error = _normalize_enum_alias(key, value, enum)
        if error is not None:
            errors.append(error)
        elif replacement is not None:
            normalized[key] = replacement

    if errors:
        return normalized, errors
    return normalized, _validate_against_schema(normalized, schema)


def _normalize_enum_alias(key: str, value: str, enum: list[Any]) -> tuple[Any | None, str | None]:
    lower_enum = {str(item).lower(): item for item in enum}
    lowered = value.strip().lower()
    if lowered in lower_enum:
        return lower_enum[lowered], None

    alias_targets = {
        "f": "fahrenheit",
        "degf": "fahrenheit",
        "°f": "fahrenheit",
        "c": "celsius",
        "degc": "celsius",
        "°c": "celsius",
    }
    if len(lowered) == 1:
        prefix_matches = [item for item in enum if str(item).lower().startswith(lowered)]
        if len(prefix_matches) > 1:
            return None, f"Argument '{key}' is ambiguous for enum values: {', '.join(map(str, prefix_matches))}"
    target = alias_targets.get(lowered)
    if target is not None and target in lower_enum:
        return lower_enum[target], None
    if target is not None:
        return None, f"Argument '{key}' has unsupported enum alias: {value}"
    return None, f"Argument '{key}' must be one of: {', '.join(map(str, enum))}"


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        if bool(getattr(settings, "tools_enabled", True)):
            _registry = ToolRegistry()
        else:
            _registry = DisabledToolRegistry()
    return _registry


def set_registry(registry: ToolRegistry | None) -> None:
    global _registry
    _registry = registry
