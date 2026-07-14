class ToolError(Exception):
    """Base class for tool registry errors."""

    code: str = "tool_error"


class ToolNotFoundError(ToolError):
    code: str = "tool_not_found"


class ToolDisabledError(ToolError):
    code: str = "tool_disabled"


class ToolValidationError(ToolError):
    code: str = "validation_error"


class ToolTimeoutError(ToolError):
    code: str = "tool_timeout"
