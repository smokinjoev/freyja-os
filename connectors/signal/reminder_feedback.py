"""Apply clear reminder feedback from owner messages without relying on model tool choice."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from connectors.gmail.reminders import ReminderStore

_COMPLETE_RE = re.compile(r"\b(?:done|handled|finished|completed|paid|picked up|taken care of|took care of|resolved|fixed)\b", re.I)
_DISMISS_RE = re.compile(r"\b(?:don['’]?t need|do not need|stop remind|no more remind|never.*remind|dismiss)\b", re.I)
_PERMANENT_RE = re.compile(r"\b(?:never|always|ever|from now on)\b", re.I)
_WORDS_RE = re.compile(r"[a-z0-9]+", re.I)
_CLAUSE_RE = re.compile(r"[.!?]+|\s+\band\b\s+", re.I)
_STOP_WORDS = {
    "a", "about", "again", "all", "an", "and", "are", "at", "be", "been", "by", "do", "ever",
    "for", "from", "i", "in", "is", "it", "me", "my", "need", "no", "not", "of", "on", "please",
    "reminder", "reminders", "the", "this", "to", "up", "was", "were", "with",
    "action", "needed", "issue", "taken", "care", "handled", "done", "completed", "picked", "paid",
}


@dataclass
class ReminderFeedbackResult:
    handled: bool = False
    updated: list[dict[str, str]] = field(default_factory=list)
    suppressions: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)

    def response_text(self) -> str:
        if not self.updated:
            return "I couldn't match that clearly to an active reminder. Which reminder did you mean?"
        completed = sum(item["status"] == "completed" for item in self.updated)
        dismissed = sum(item["status"] == "dismissed" for item in self.updated)
        parts = []
        if completed:
            parts.append(f"marked {completed} completed")
        if dismissed:
            parts.append(f"dismissed {dismissed}")
        text = "Got it — I " + " and ".join(parts) + "."
        if self.suppressions:
            text += " I’ll suppress future matches for: " + ", ".join(self.suppressions) + "."
        if self.unmatched:
            text += " I couldn't confidently match: " + "; ".join(self.unmatched) + "."
        return text


class ReminderFeedbackProcessor:
    def __init__(self, store: ReminderStore) -> None:
        self.store = store

    def apply(self, text: str) -> ReminderFeedbackResult:
        clauses = [part.strip() for part in _CLAUSE_RE.split(text) if part.strip()]
        result = ReminderFeedbackResult(handled=bool(_COMPLETE_RE.search(text) or _DISMISS_RE.search(text)))
        candidates = self.store.list_pending(limit=200)
        used: set[str] = set()
        for clause in clauses:
            status = "dismissed" if _DISMISS_RE.search(clause) else "completed" if _COMPLETE_RE.search(clause) else None
            if status is None:
                continue
            clause_tokens = _meaningful_tokens(clause)
            scored = []
            for candidate in candidates:
                candidate_id = str(candidate["candidate_id"])
                if candidate_id in used:
                    continue
                searchable = " ".join(
                    str(candidate.get(key) or "") for key in ("sender", "subject", "summary", "evidence")
                )
                overlap = clause_tokens & _meaningful_tokens(searchable)
                if overlap:
                    scored.append((len(overlap), candidate, overlap))
            if not scored:
                result.unmatched.append(clause)
                continue
            scored.sort(key=lambda item: item[0], reverse=True)
            if len(scored) > 1 and scored[0][0] == scored[1][0]:
                result.unmatched.append(clause)
                continue
            _, candidate, overlap = scored[0]
            candidate_id = str(candidate["candidate_id"])
            if not self.store.resolve(candidate_id, status=status, note=clause):
                result.unmatched.append(clause)
                continue
            used.add(candidate_id)
            result.updated.append({
                "candidate_id": candidate_id,
                "subject": str(candidate["subject"]),
                "status": status,
            })
            if status == "dismissed" and _PERMANENT_RE.search(clause):
                pattern_tokens = [word for word in _WORDS_RE.findall(clause.casefold()) if word in overlap]
                pattern = " ".join(dict.fromkeys(pattern_tokens))
                if len(pattern_tokens) >= 2 and self.store.add_suppression(pattern, reason=clause):
                    result.suppressions.append(pattern)
        return result


def _meaningful_tokens(text: str) -> set[str]:
    return {word for word in _WORDS_RE.findall(text.casefold()) if len(word) > 1 and word not in _STOP_WORDS}
