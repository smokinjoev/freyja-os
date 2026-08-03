from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query

from freyja.memory.models import (
    AppendMessageRequest,
    AppendMessageResponse,
    ConversationMessagesResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    ListConversationsResponse,
    MemoryKind,
    MemoryPrincipal,
    PutSharedMemoryRequest,
    SharedMemory,
    SharedMemoryListResponse,
)
from freyja.memory.principal import require_memory_principal
from freyja.memory.store import (
    MemoryAccessDeniedError,
    MemoryStorageError,
    append_message as _append_message,
    create_conversation as _create_conversation,
    delete_shared_memory as _delete_shared_memory,
    delete_conversation as _delete_conversation,
    get_shared_memory as _get_shared_memory,
    get_messages as _get_messages,
    list_shared_memories as _list_shared_memories,
    list_conversations as _list_conversations,
    put_shared_memory as _put_shared_memory,
    prune as _prune,
)

memory_router = APIRouter(prefix="/memory", tags=["memory"])


@memory_router.put("/items/{memory_id}", response_model=SharedMemory)
async def put_shared_memory(
    memory_id: str = Path(...),
    request: PutSharedMemoryRequest = Body(...),
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> SharedMemory:
    if request.memory_id is not None and request.memory_id != memory_id:
        raise HTTPException(status_code=400, detail="memory_id mismatch")
    try:
        return _put_shared_memory(
            principal,
            request.model_copy(update={"memory_id": memory_id}),
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid memory identifier") from None
    except MemoryAccessDeniedError:
        raise HTTPException(status_code=403, detail="Shared memory is unavailable") from None
    except MemoryStorageError:
        raise HTTPException(status_code=503, detail="Shared memory storage unavailable") from None


@memory_router.get("/items", response_model=SharedMemoryListResponse)
async def list_shared_memories(
    kind: list[MemoryKind] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> SharedMemoryListResponse:
    try:
        return _list_shared_memories(principal, kinds=kind, limit=limit)
    except MemoryStorageError:
        raise HTTPException(status_code=503, detail="Shared memory storage unavailable") from None


@memory_router.get("/items/{memory_id}", response_model=SharedMemory)
async def get_shared_memory(
    memory_id: str = Path(...),
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> SharedMemory:
    try:
        memory = _get_shared_memory(principal, memory_id)
    except ValueError:
        memory = None
    except MemoryStorageError:
        raise HTTPException(status_code=503, detail="Shared memory storage unavailable") from None
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    return memory


@memory_router.delete("/items/{memory_id}")
async def delete_shared_memory(
    memory_id: str = Path(...),
    principal: MemoryPrincipal = Depends(require_memory_principal),
) -> dict[str, bool]:
    try:
        deleted = _delete_shared_memory(principal, memory_id)
    except ValueError:
        deleted = False
    except MemoryStorageError:
        raise HTTPException(status_code=503, detail="Shared memory storage unavailable") from None
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory item not found")
    return {"deleted": True}


@memory_router.post("/conversations", response_model=CreateConversationResponse)
async def create_conversation(
    request: CreateConversationRequest | None = None,
) -> CreateConversationResponse:
    return _create_conversation(request)


@memory_router.get("/conversations", response_model=ListConversationsResponse)
async def list_conversations() -> ListConversationsResponse:
    return _list_conversations()


@memory_router.get("/conversations/{conversation_id}", response_model=ConversationMessagesResponse)
async def get_conversation(
    conversation_id: str = Path(...),
) -> ConversationMessagesResponse:
    response = _get_messages(conversation_id)
    if not response.messages and not _conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return response


@memory_router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str = Path(...),
) -> dict[str, bool]:
    deleted = _delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}


@memory_router.post("/conversations/{conversation_id}/messages", response_model=AppendMessageResponse)
async def append_message_to_conversation(
    conversation_id: str = Path(...),
    request: AppendMessageRequest | None = None,
) -> AppendMessageResponse:
    body = request or AppendMessageRequest(conversation_id=conversation_id, role="user", content="")
    if body.conversation_id != conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id mismatch")
    message = _append_message(body)
    return AppendMessageResponse(message_id=message.message_id)


def _conversation_exists(conversation_id: str) -> bool:
    for summary in _list_conversations().conversations:
        if summary.conversation_id == conversation_id:
            return True
    return False


__all__ = [
    "memory_router",
    "create_conversation",
    "list_conversations",
    "get_messages",
    "delete_conversation",
    "append_message",
    "prune",
]
