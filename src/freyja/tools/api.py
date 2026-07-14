from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolExecutionResult
from freyja.tools.registry import ToolRegistry, get_registry

tools_router = APIRouter(prefix="/tools", tags=["tools"])


class ToolListResponse(BaseModel):
    tools: list[ToolDefinition]


class ToolExecuteRequest(BaseModel):
    arguments: dict | None = None
    actor: str | None = None
    conversation_id: str | None = None
    metadata: dict | None = None


@tools_router.get("", response_model=ToolListResponse)
async def list_tools() -> ToolListResponse:
    registry = get_registry()
    return ToolListResponse(tools=registry.list_tools())


@tools_router.get("/{tool_name}", response_model=ToolDefinition)
async def get_tool(tool_name: str = Path(...)) -> ToolDefinition:
    registry = get_registry()
    tool = registry.get_tool(tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@tools_router.post("/{tool_name}/execute", response_model=ToolExecutionResult)
async def execute_tool(
    tool_name: str = Path(...),
    body: ToolExecuteRequest | None = None,
) -> ToolExecutionResult:
    registry = get_registry()
    body = body or ToolExecuteRequest()
    request = ToolExecutionRequest(
        tool_name=tool_name,
        arguments=body.arguments or {},
        actor=body.actor,
        conversation_id=body.conversation_id,
        metadata=body.metadata or {},
    )
    result = await registry.execute(request)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.public_error_message or "Tool execution failed")
    return result
