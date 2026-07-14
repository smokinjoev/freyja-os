from fastapi import APIRouter, HTTPException, Path

from freyja.memory.models import (
    AppendMessageRequest,
    AppendMessageResponse,
    ConversationMessagesResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    ListConversationsResponse,
)
from freyja.memory.store import (
    append_message as _append_message,
    create_conversation as _create_conversation,
    delete_conversation as _delete_conversation,
    get_messages as _get_messages,
    list_conversations as _list_conversations,
    prune as _prune,
)

memory_router = APIRouter(prefix="/memory", tags=["memory"])


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
