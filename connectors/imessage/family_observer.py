from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from freyja.memory.models import MemoryPrincipal, PutSharedMemoryRequest
from freyja.memory.principal import build_memory_principal, stable_identity
from freyja.memory.store import MemoryStore, get_store


_TIME_PATTERN = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b", re.IGNORECASE)
_DATE_HINT_PATTERN = re.compile(
    r"\b(today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
    re.IGNORECASE,
)
_LOCATION_PATTERN = re.compile(r"\b(?:at|in|to|from)\s+([A-Z][A-Za-z0-9&'. -]{1,60})")
_CANCEL_PATTERN = re.compile(
    r"\b(never mind|nevermind|cancel(?:led|ed|ing)?|aren't going|are not going|not going|called off)\b",
    re.IGNORECASE,
)
_UPDATE_PATTERN = re.compile(r"\b(delayed|now|instead|changed|moved|rescheduled|updated)\b", re.IGNORECASE)


@dataclass(frozen=True)
class FamilyMemoryCandidate:
    memory_id: str
    content: str
    confidence: float
    status: str
    fact_type: str
    people: list[str]
    date_time: str | None = None
    location: str | None = None
    related_memory_id: str | None = None


class LocalFamilyContextExtractor:
    """Small local extractor for passive family logistics.

    This intentionally stores structured candidate summaries, not raw group-chat
    text. It is conservative until a dedicated local model is wired in.
    """

    _EVENT_WORDS = {
        "arrive": "travel_arrival",
        "arrives": "travel_arrival",
        "arriving": "travel_arrival",
        "land": "travel_arrival",
        "lands": "travel_arrival",
        "appointment": "appointment",
        "birthday": "celebration",
        "celebration": "celebration",
        "dinner": "event",
        "flight": "travel",
        "leaving": "travel",
        "meeting": "appointment",
        "party": "celebration",
        "pickup": "logistics",
        "pick up": "logistics",
        "reservation": "event",
        "travel": "travel",
        "trip": "travel",
    }

    def extract(
        self,
        *,
        text: str,
        sender_label: str,
        chat_identifier: str,
        message_id: str,
        timestamp: datetime,
    ) -> list[FamilyMemoryCandidate]:
        normalized = " ".join(text.split())
        if not normalized:
            return []

        lowered = normalized.lower()
        fact_type = self._fact_type(lowered)
        is_cancellation = _CANCEL_PATTERN.search(normalized) is not None
        if fact_type is None:
            if not is_cancellation:
                return []
            fact_type = "event"

        date_time = self._date_time(normalized)
        location = self._location(normalized)
        if (
            not date_time
            and not location
            and fact_type not in {"celebration", "travel_arrival"}
            and not is_cancellation
        ):
            return []

        status = "cancelled" if is_cancellation else "confirmed"
        confidence = 0.82
        if status == "cancelled":
            confidence = 0.76
        elif _UPDATE_PATTERN.search(normalized):
            confidence = 0.72
        elif not date_time:
            confidence = 0.64

        people = [sender_label]
        memory_id = self._memory_id(fact_type, chat_identifier, normalized)
        related = memory_id if status == "cancelled" or _UPDATE_PATTERN.search(normalized) else None
        content = self._content(
            fact_type=fact_type,
            status=status,
            people=people,
            date_time=date_time,
            location=location,
        )
        return [
            FamilyMemoryCandidate(
                memory_id=memory_id,
                content=content,
                confidence=confidence,
                status=status,
                fact_type=fact_type,
                people=people,
                date_time=date_time,
                location=location,
                related_memory_id=related,
            )
        ]

    def _fact_type(self, lowered: str) -> str | None:
        for phrase, fact_type in self._EVENT_WORDS.items():
            if phrase in lowered:
                return fact_type
        if "gift" in lowered and ("wants" in lowered or "likes" in lowered or "idea" in lowered):
            return "gift_preference"
        return None

    def _date_time(self, text: str) -> str | None:
        parts: list[str] = []
        date_match = _DATE_HINT_PATTERN.search(text)
        time_match = _TIME_PATTERN.search(text)
        if date_match:
            parts.append(date_match.group(0))
        if time_match and self._looks_like_time(time_match.group(0)):
            parts.append(time_match.group(0))
        return " ".join(parts) or None

    @staticmethod
    def _looks_like_time(value: str) -> bool:
        lowered = value.lower()
        return ":" in value or "am" in lowered or "pm" in lowered

    @staticmethod
    def _location(text: str) -> str | None:
        match = _LOCATION_PATTERN.search(text)
        if not match:
            return None
        return match.group(1).strip(" .")

    @staticmethod
    def _memory_id(fact_type: str, chat_identifier: str, text: str) -> str:
        if fact_type in {"appointment", "event", "logistics", "travel", "travel_arrival"}:
            digest_source = f"{chat_identifier}:{fact_type}"
        else:
            digest_source = f"{chat_identifier}:{fact_type}:{text.lower()[:80]}"
        digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]
        return f"family-{fact_type}-{digest}"

    @staticmethod
    def _content(
        *,
        fact_type: str,
        status: str,
        people: list[str],
        date_time: str | None,
        location: str | None,
    ) -> str:
        details = [f"{fact_type.replace('_', ' ')} is {status}"]
        if people:
            details.append(f"people: {', '.join(people)}")
        if date_time:
            details.append(f"date/time: {date_time}")
        if location:
            details.append(f"location: {location}")
        return "; ".join(details)


class FamilyIMessageObserver:
    def __init__(
        self,
        *,
        store: MemoryStore | None = None,
        extractor: LocalFamilyContextExtractor | None = None,
    ) -> None:
        self._store = store
        self._extractor = extractor or LocalFamilyContextExtractor()

    def observe(
        self,
        *,
        text: str,
        sender_label: str,
        chat_identifier: str,
        message_id: str,
        timestamp: datetime,
    ) -> list[FamilyMemoryCandidate]:
        principal = self._principal(chat_identifier)
        candidates = self._extractor.extract(
            text=text,
            sender_label=sender_label,
            chat_identifier=chat_identifier,
            message_id=message_id,
            timestamp=timestamp,
        )
        if not candidates:
            return []
        store = self._store or get_store()
        for candidate in candidates:
            store.put_shared_memory(
                principal,
                PutSharedMemoryRequest(
                    memory_id=candidate.memory_id,
                    kind="fact",
                    content=candidate.content,
                    confidence=candidate.confidence,
                    sensitivity="private",
                    expires_at=timestamp.astimezone(timezone.utc) + timedelta(days=180),
                    metadata={
                        "source": "family_imessage_observer",
                        "source_thread": chat_identifier,
                        "source_message_id": message_id,
                        "fact_type": candidate.fact_type,
                        "people": candidate.people,
                        "date_time": candidate.date_time,
                        "location": candidate.location,
                        "status": candidate.status,
                        "tentative": candidate.confidence < 0.8,
                        "related_memory_id": candidate.related_memory_id,
                        "raw_text_persisted": False,
                    },
                ),
            )
        return candidates

    @staticmethod
    def _principal(chat_identifier: str) -> MemoryPrincipal:
        return build_memory_principal(
            client_type="imessage",
            client_subject=stable_identity("family-imessage-group", chat_identifier),
            account_owner="person:family",
            conversation_id=stable_identity("imessage-family-conv", chat_identifier),
        )
