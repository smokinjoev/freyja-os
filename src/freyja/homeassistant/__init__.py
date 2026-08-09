"""Safe Home Assistant integration boundary."""

from .client import HomeAssistantClient
from .models import EntityAccess, HomeAssistantEntity, HomeAssistantSummary, PairingPlan, PairingProtocol
from .service import HomeAssistantService

__all__ = [
    "EntityAccess",
    "HomeAssistantClient",
    "HomeAssistantEntity",
    "HomeAssistantSummary",
    "HomeAssistantService",
    "PairingPlan",
    "PairingProtocol",
]
