"""Agent Smith policy enforcement: repository boundaries, operation allowlists,
approval gates, retry limits, loop detection, and audit records.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from freyja.config import settings
from freyja.tools.models import ToolRiskLevel

from .models import AuditEvent, PolicyCheckResult, PolicyDecision

logger = logging.getLogger(__name__)

_SECRET_PATH_PATTERNS = [
    re.compile(r"(^|/|\.)env"),
    re.compile(r"(^|/)secrets?(/|$)"),
    re.compile(r"(^|/|\.)(key|pem|crt|p12|pfx|keystore)(/|$)"),
    re.compile(r"(^|/)\.ssh(/|$)"),
    re.compile(r"(^|/)\.aws(/|$)"),
    re.compile(r"(^|/)\.git-credentials(/|$)"),
]


class AgentPolicy:
    """Loads policy from YAML and enforces it for every Agent Smith operation."""

    def __init__(self, path: str | None = None) -> None:
        self._path = path or str(settings.agent_smith_policy_path)
        self._config: dict[str, Any] = self._load(self._path)
        self._allowed_root = Path(self._config.get("allowed_root", "/Users/freyja/freyja-os")).resolve()
        self._auto_allowed = set(self._config.get("auto_allowed_operations", []))
        self._approval_required = set(self._config.get("approval_required_operations", []))
        self._prohibited_operations = set(self._config.get("prohibited_operations", []))
        self._read_only_builtin_tools = set(self._config.get("read_only_builtin_tools", []))
        self._smith_read_only_tools = set(self._config.get("smith_read_only_tools", []))
        self._write_pilot_allowed_tools = set(self._config.get("write_pilot_allowed_tools", []))
        self._write_pilot_sandbox = Path(
            self._config.get("write_pilot_sandbox", "/Users/freyja/freyja-os/docs/smith-pilot")
        ).expanduser().resolve()
        self._max_retries = int(self._config.get("max_retries", settings.agent_smith_max_retries))
        self._secret_patterns = [
            re.compile(pattern) for pattern in self._config.get("secret_patterns", [r"\.env$", r"(^|/)secrets?(/|$)", r"\.pem$", r"\.key$", r"\.pfx$"])
        ]
        self._audit_enabled = bool(settings.agent_smith_audit_enabled)

    def _load(self, path: str) -> dict[str, Any]:
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = Path(__file__).resolve().parents[3] / resolved
        with resolved.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"Policy file '{path}' must contain a YAML mapping")
        return data

    @property
    def allowed_root(self) -> Path:
        return self._allowed_root

    @property
    def max_retries(self) -> int:
        return self._max_retries

    @property
    def audit_enabled(self) -> bool:
        return self._audit_enabled

    @property
    def read_only_builtin_tools(self) -> set[str]:
        return self._read_only_builtin_tools

    @property
    def smith_read_only_tools(self) -> set[str]:
        return self._smith_read_only_tools

    @property
    def write_pilot_allowed_tools(self) -> set[str]:
        return self._write_pilot_allowed_tools

    @property
    def write_pilot_sandbox(self) -> Path:
        return self._write_pilot_sandbox

    def check_tool_permitted(self, tool_name: str, risk_level: ToolRiskLevel) -> PolicyCheckResult:
        if tool_name in self._prohibited_operations:
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Tool '{tool_name}' is prohibited for Agent Smith.",
            )
        if risk_level == ToolRiskLevel.READ_ONLY and (
            tool_name in self._read_only_builtin_tools or tool_name in self._smith_read_only_tools
        ):
            return PolicyCheckResult(decision=PolicyDecision.ALLOW)
        if risk_level == ToolRiskLevel.CONTROLLED_WRITE and tool_name in self._approval_required:
            return PolicyCheckResult(
                decision=PolicyDecision.APPROVE,
                reason=f"Tool '{tool_name}' requires explicit approval before execution.",
                approval_required=True,
            )
        return PolicyCheckResult(
            decision=PolicyDecision.DENY,
            reason=f"Tool '{tool_name}' is not in the Agent Smith whitelist or is not read-only.",
        )

    def check_path(self, requested_path: str) -> PolicyCheckResult:
        target = Path(requested_path).expanduser().resolve()
        try:
            target.relative_to(self._allowed_root)
        except ValueError:
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Path '{requested_path}' is outside the allowed repository root '{self._allowed_root}'.",
            )
        if self._is_secret_path(target):
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Path '{requested_path}' matches a protected secret pattern.",
            )
        return PolicyCheckResult(decision=PolicyDecision.ALLOW)

    def check_operation(self, operation: str, target_path: str | None = None) -> PolicyCheckResult:
        if operation in self._prohibited_operations:
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Operation '{operation}' is prohibited by Agent Smith policy.",
            )
        if target_path is not None:
            path_result = self.check_path(target_path)
            if path_result.decision == PolicyDecision.DENY:
                return path_result
        if operation in self._auto_allowed:
            return PolicyCheckResult(decision=PolicyDecision.ALLOW)
        if operation in self._approval_required:
            return PolicyCheckResult(
                decision=PolicyDecision.APPROVE,
                reason=f"Operation '{operation}' requires explicit approval before execution.",
                approval_required=True,
            )
        return PolicyCheckResult(
            decision=PolicyDecision.DENY,
            reason=f"Operation '{operation}' is not in the Agent Smith allowlist.",
        )

    def check_approval(self, operation: str, approved: bool) -> PolicyCheckResult:
        if operation not in self._approval_required:
            return PolicyCheckResult(decision=PolicyDecision.ALLOW)
        if approved:
            return PolicyCheckResult(
                decision=PolicyDecision.ALLOW,
                reason=f"Operation '{operation}' was explicitly approved.",
            )
        return PolicyCheckResult(
            decision=PolicyDecision.DENY,
            reason=f"Operation '{operation}' requires explicit approval but was not approved.",
        )

    def detect_loop(self, fingerprints: list[str]) -> bool:
        if len(fingerprints) < 4:
            return False
        recent = fingerprints[-6:]
        if len(set(recent)) == 1:
            return True
        pairs: list[tuple[str, str]] = []
        for index in range(1, len(recent)):
            pairs.append((recent[index - 1], recent[index]))
        if len(pairs) >= 4:
            last_pair = pairs[-1]
            if pairs.count(last_pair) >= 2:
                return True
        counts: dict[str, int] = {}
        for fingerprint in recent:
            counts[fingerprint] = counts.get(fingerprint, 0) + 1
            if counts[fingerprint] >= 3:
                return True
        return False

    def record_audit(
        self,
        request_id: str,
        action: str,
        outcome: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        details = details or {}
        event = AuditEvent(
            request_id=request_id,
            actor="agent_smith",
            action=action,
            outcome=outcome,
            details=details,
        )
        record = event.to_dict()
        if self._audit_enabled:
            logger.info(record)
        return record

    def check_write_pilot_path(self, requested_path: str, *, repo_root: Path | None = None) -> PolicyCheckResult:
        """Validate a target path for the approved-write pilot.

        The path must be a repository-relative path under the configured
        write_pilot_sandbox, must not be absolute, must not contain parent
        traversal, must not be hidden, must be a Markdown file, must not be a
        symlink, and must not match protected secret patterns. Symlink
        resolution is deliberately avoided; containment is checked against
        the logical path components.
        """
        if not requested_path:
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason="Write-pilot target path is empty.",
            )
        if " " in requested_path:
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Path '{requested_path}' contains multiple path components.",
            )
        if requested_path.startswith("-"):
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Path '{requested_path}' looks like an option argument.",
            )
        if requested_path.startswith(("/", "\\")):
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Path '{requested_path}' is absolute; only repository-relative paths are allowed.",
            )
        path_obj = Path(requested_path)
        if ".." in path_obj.parts:
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Path '{requested_path}' contains parent directory traversal.",
            )
        if requested_path.endswith("/") or requested_path.endswith("\\"):
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Path '{requested_path}' is a directory, not a file.",
            )
        if path_obj.name.startswith(".") or any(part.startswith(".") for part in path_obj.parts):
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Path '{requested_path}' is hidden or contains hidden components.",
            )
        if path_obj.suffix.lower() != ".md":
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Path '{requested_path}' is not a Markdown (.md) file.",
            )

        root = (repo_root or self._allowed_root).resolve()
        try:
            # Use .absolute() rather than .resolve() so symlinks are not followed
            # and can be rejected before containment checks.
            target = (root / requested_path).absolute()
        except (OSError, ValueError):
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Path '{requested_path}' is not a valid filesystem path.",
            )

        # Reject any component that is a symlink before checking containment.
        for parent in target.parents:
            if parent == root:
                break
            if parent.is_symlink():
                return PolicyCheckResult(
                    decision=PolicyDecision.DENY,
                    reason=f"Path '{requested_path}' traverses a symlink.",
                )
        if target.is_symlink():
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Path '{requested_path}' is a symlink, which is not allowed.",
            )

        sandbox = self._write_pilot_sandbox.resolve()
        try:
            target.relative_to(sandbox)
        except ValueError:
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=(
                    f"Path '{requested_path}' is outside the write-pilot sandbox "
                    f"'{sandbox}'."
                ),
            )
        if self._is_secret_path(target):
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Path '{requested_path}' matches a protected secret pattern.",
            )
        return PolicyCheckResult(decision=PolicyDecision.ALLOW)

    def check_write_pilot_tool(self, tool_name: str) -> PolicyCheckResult:
        if tool_name in self._prohibited_operations:
            return PolicyCheckResult(
                decision=PolicyDecision.DENY,
                reason=f"Tool '{tool_name}' is prohibited for the write-pilot.",
            )
        if tool_name in self._write_pilot_allowed_tools:
            return PolicyCheckResult(decision=PolicyDecision.ALLOW)
        return PolicyCheckResult(
            decision=PolicyDecision.DENY,
            reason=(
                f"Tool '{tool_name}' is not in the write-pilot allowlist: "
                f"{sorted(self._write_pilot_allowed_tools)}."
            ),
        )

    def _is_secret_path(self, target: Path) -> bool:
        path_str = str(target)
        for pattern in self._secret_patterns:
            if pattern.search(path_str):
                return True
        return any(pattern.search(path_str) for pattern in _SECRET_PATH_PATTERNS)


def _is_within_allowed_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _default_policy_path() -> Path:
    candidate = Path(settings.agent_smith_policy_path)
    if candidate.is_absolute():
        return candidate
    project_root = Path(__file__).resolve().parents[3]
    return project_root / candidate
