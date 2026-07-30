"""Native macOS iMessage connector primitives."""

from connectors.imessage.config import IMessageSettings
from connectors.imessage.models import IMessage, IMessageReply
from connectors.imessage.transport import (
    IMessageTransport,
    IMessageTransportError,
    UnsupportedIMessageEvent,
)

__all__ = [
    "IMessage",
    "IMessageReply",
    "IMessageSettings",
    "IMessageTransport",
    "IMessageTransportError",
    "UnsupportedIMessageEvent",
]
