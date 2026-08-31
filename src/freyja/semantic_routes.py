from __future__ import annotations

import re
from enum import StrEnum


class SemanticRoute(StrEnum):
    FAST = "fast"
    GENERAL = "general"
    DEEP = "deep"
    CODE = "code"
    VISION = "vision"
    EMBEDDING = "embedding"
    PRIVATE = "private"


ROUTE_TO_CAPABILITY: dict[SemanticRoute, str] = {
    SemanticRoute.FAST: "route.fast",
    SemanticRoute.GENERAL: "route.general",
    SemanticRoute.DEEP: "route.deep",
    SemanticRoute.CODE: "route.code",
    SemanticRoute.VISION: "route.vision",
    SemanticRoute.EMBEDDING: "route.embedding",
    SemanticRoute.PRIVATE: "route.private",
}

CAPABILITY_TO_ROUTE: dict[str, SemanticRoute] = {
    value: route for route, value in ROUTE_TO_CAPABILITY.items()
}


def semantic_route_for_objective(objective: str, *, has_attachments: bool = False, private: bool = False) -> SemanticRoute:
    lowered = objective.lower()
    if private:
        return SemanticRoute.PRIVATE
    if has_attachments or any(term in lowered for term in ("photo", "image", "picture", "pdf", "document")):
        return SemanticRoute.VISION
    if any(term in lowered for term in ("embed", "embedding", "semantic search", "vector")):
        return SemanticRoute.EMBEDDING
    if _is_code_route(lowered):
        return SemanticRoute.CODE
    if any(term in lowered for term in ("deep", "sleep on it", "thorough", "complex", "research plan")):
        return SemanticRoute.DEEP
    if _is_fast_route(lowered):
        return SemanticRoute.FAST
    return SemanticRoute.GENERAL


def capability_for_route(route: SemanticRoute | str) -> str:
    semantic_route = route if isinstance(route, SemanticRoute) else SemanticRoute(route)
    return ROUTE_TO_CAPABILITY[semantic_route]


def route_for_capability(capability: str) -> SemanticRoute | None:
    return CAPABILITY_TO_ROUTE.get(capability)


def _is_code_route(lowered: str) -> bool:
    code_patterns = (
        r"\bcode\b",
        r"\bcoding\b",
        r"\bprogramming\b",
        r"\bsoftware\b",
        r"\bscript\b",
        r"\bdebug\b",
        r"\bbug\b",
        r"\bbuild\b",
        r"\bwebsite\b",
        r"\bsite\b",
        r"\bapp\b",
        r"\brepo\b",
        r"\brepository\b",
        r"\bgit\b",
        r"\bpytest\b",
        r"\bunit tests?\b",
        r"\bintegration tests?\b",
        r"\btest suite\b",
        r"\brun tests?\b",
    )
    return any(re.search(pattern, lowered) for pattern in code_patterns)


def _is_fast_route(lowered: str) -> bool:
    stripped = lowered.strip()
    return len(stripped) <= 160 and (
        stripped in {"ok", "okay", "thanks", "thank you", "got it", "roger", "ack", "acknowledged", "working it", "ready"}
        or stripped.startswith(("are you there", "ping", "status", "hello", "hi", "hey"))
        or stripped.startswith(("say ", "reply with "))
    )
