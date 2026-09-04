from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Protocol

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = REPO_ROOT / "config" / "freyja-channels.yaml"
DEFAULT_STATE_DIR = REPO_ROOT / "data" / "freyja-channels"


@dataclasses.dataclass(frozen=True)
class ChannelMessage:
    channel: str
    sender: str
    text: str
    requested_agent: str | None = None
    chat_id: str | None = None
    attachments: tuple[dict[str, Any], ...] = ()


@dataclasses.dataclass(frozen=True)
class ChannelRoute:
    channel: str
    identity: str
    agent: str
    thread_key: str
    sender_hash: str
    attachment_count: int


class OpenWebUIClient(Protocol):
    def send(self, *, agent: str, thread_key: str, message: str, attachments: tuple[dict[str, Any], ...]) -> str:
        ...


class ChannelPolicyError(ValueError):
    pass


class RateLimitExceeded(ChannelPolicyError):
    pass


class FileChannelStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.audit_log = self.root / "audit.jsonl"
        self.threads = self.root / "threads.json"

    def remember_thread(self, route: ChannelRoute) -> None:
        data = self._read_threads()
        data[self.thread_map_key(route.channel, route.sender_hash, route.agent)] = route.thread_key
        self.threads.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def get_thread(self, *, channel: str, sender_hash: str, agent: str) -> str | None:
        return self._read_threads().get(self.thread_map_key(channel, sender_hash, agent))

    @staticmethod
    def thread_map_key(channel: str, sender_hash: str, agent: str) -> str:
        return f"{channel}:{sender_hash}:{agent}"

    def write_audit(self, event: dict[str, Any]) -> None:
        event = {**event, "timestamp_unix": int(time.time())}
        with self.audit_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def _read_threads(self) -> dict[str, str]:
        if not self.threads.exists():
            return {}
        data = json.loads(self.threads.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in data.items()}


class MemoryChannelStore(FileChannelStore):
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.thread_map: dict[str, str] = {}

    def remember_thread(self, route: ChannelRoute) -> None:
        self.thread_map[self.thread_map_key(route.channel, route.sender_hash, route.agent)] = route.thread_key

    def get_thread(self, *, channel: str, sender_hash: str, agent: str) -> str | None:
        return self.thread_map.get(self.thread_map_key(channel, sender_hash, agent))

    def write_audit(self, event: dict[str, Any]) -> None:
        self.events.append({**event, "timestamp_unix": int(time.time())})


class FreyjaChannels:
    def __init__(
        self,
        *,
        policy_path: Path = DEFAULT_POLICY,
        allowlists: dict[str, set[str]] | None = None,
        identity_maps: dict[str, dict[str, str]] | None = None,
        store: FileChannelStore | MemoryChannelStore | None = None,
        client: OpenWebUIClient | None = None,
        now: Any | None = None,
    ) -> None:
        self.policy = self._load_policy(policy_path)
        self.allowlists = allowlists or {}
        self.identity_maps = identity_maps or {}
        self.store = store or FileChannelStore(DEFAULT_STATE_DIR)
        self.client = client
        self._now = now or time.time
        self._rate_windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def route(self, message: ChannelMessage) -> ChannelRoute:
        sender_hash = self._hash(message.sender)
        try:
            channel_policy = self._channel_policy(message.channel)
            if str(channel_policy.get("status")) == "disabled":
                raise ChannelPolicyError(f"{message.channel} is disabled")
            allowed = self.allowlists.get(message.channel, set())
            if not allowed:
                raise ChannelPolicyError("allowlist is empty")
            if message.sender not in allowed:
                raise ChannelPolicyError("sender is not allowlisted")
            identity = self.identity_maps.get(message.channel, {}).get(message.sender)
            if not identity:
                raise ChannelPolicyError("sender identity is not mapped")
            agent = self._select_agent(identity, message.requested_agent)
            self._check_rate(message.channel, message.sender, channel_policy)
        except ChannelPolicyError as exc:
            self._write_denial_audit(message, sender_hash=sender_hash, reason=str(exc))
            raise
        thread_key = self.store.get_thread(channel=message.channel, sender_hash=sender_hash, agent=agent) or self._thread_key(
            channel_policy,
            agent=agent,
            sender_hash=sender_hash,
            chat_id=message.chat_id,
        )
        route = ChannelRoute(
            channel=message.channel,
            identity=identity,
            agent=agent,
            thread_key=thread_key,
            sender_hash=sender_hash,
            attachment_count=len(message.attachments),
        )
        self.store.remember_thread(route)
        self.store.write_audit(
            {
                "event": "freyja_channels_route",
                "channel": route.channel,
                "identity": route.identity,
                "agent": route.agent,
                "sender_hash": route.sender_hash,
                "attachment_count": route.attachment_count,
                "message_body_logged": False,
                "raw_sender_logged": False,
            }
        )
        return route

    def _write_denial_audit(self, message: ChannelMessage, *, sender_hash: str, reason: str) -> None:
        self.store.write_audit(
            {
                "event": "freyja_channels_denied",
                "channel": message.channel,
                "sender_hash": sender_hash,
                "reason": reason,
                "attachment_count": len(message.attachments),
                "message_body_logged": False,
                "raw_sender_logged": False,
            }
        )

    def handle(self, message: ChannelMessage) -> str:
        if self.client is None:
            raise ChannelPolicyError("Open WebUI client is not configured")
        route = self.route(message)
        response = self.client.send(agent=route.agent, thread_key=route.thread_key, message=message.text, attachments=message.attachments)
        self.store.write_audit(
            {
                "event": "freyja_channels_response",
                "channel": route.channel,
                "identity": route.identity,
                "agent": route.agent,
                "sender_hash": route.sender_hash,
                "message_body_logged": False,
                "raw_sender_logged": False,
            }
        )
        return response

    def _load_policy(self, path: Path) -> dict[str, Any]:
        policy = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(policy, dict):
            raise ChannelPolicyError("channel policy must be a mapping")
        if policy.get("secrets_included") is not False:
            raise ChannelPolicyError("channel policy must not contain secrets")
        if policy.get("principle") != "deterministic_gateway_only":
            raise ChannelPolicyError("channel policy must be deterministic")
        prohibitions = policy.get("prohibitions") or {}
        if prohibitions.get("model_routing") is not True or prohibitions.get("independent_agent_intelligence") is not True:
            raise ChannelPolicyError("channel policy must prohibit model routing and independent intelligence")
        return policy

    def _channel_policy(self, channel: str) -> dict[str, Any]:
        channels = self.policy.get("channels") or {}
        item = channels.get(channel)
        if not isinstance(item, dict):
            raise ChannelPolicyError(f"unsupported channel: {channel}")
        if item.get("empty_allowlist") != "deny_all":
            raise ChannelPolicyError(f"{channel} must deny an empty allowlist")
        return item

    def _select_agent(self, identity: str, requested_agent: str | None) -> str:
        identities = self.policy.get("identities") or {}
        item = identities.get(identity)
        if not isinstance(item, dict):
            raise ChannelPolicyError("identity is not configured")
        permitted = set(item.get("permitted_agents") or [])
        selected = requested_agent or str(item.get("default_agent"))
        if selected not in permitted:
            raise ChannelPolicyError("requested agent is not permitted for identity")
        return selected

    def _check_rate(self, channel: str, sender: str, channel_policy: dict[str, Any]) -> None:
        limit = int((channel_policy.get("rate_limit") or {}).get("per_sender_per_minute") or 0)
        if limit <= 0:
            return
        now = float(self._now())
        window = self._rate_windows[(channel, sender)]
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= limit:
            raise RateLimitExceeded("rate limit exceeded")
        window.append(now)

    def _thread_key(self, channel_policy: dict[str, Any], *, agent: str, sender_hash: str, chat_id: str | None) -> str:
        template = str((channel_policy.get("thread_persistence") or {}).get("key") or "{agent}:{hashed_chat_id}")
        hashed_chat = self._hash(chat_id or sender_hash)
        return template.format(agent=agent, hashed_chat_id=hashed_chat, hashed_sender_or_alias=sender_hash)

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
