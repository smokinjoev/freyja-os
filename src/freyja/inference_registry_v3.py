from __future__ import annotations

import json

from freyja.config import settings
from freyja.foundation_models import InferenceEndpoint, SecurityDomain, SecurityDomainId
from freyja.foundation_seed import INFERENCE_ENDPOINTS, SECURITY_DOMAINS, domains_by_id


class InferenceRegistryV3:
    """Capability/domain endpoint lookup only.

    This registry deliberately does not classify user intent, choose agents,
    select tools, or decide task strategy.
    """

    def __init__(
        self,
        *,
        endpoints: tuple[InferenceEndpoint, ...] = INFERENCE_ENDPOINTS,
        domains: tuple[SecurityDomain, ...] = SECURITY_DOMAINS,
        include_configured: bool = True,
    ) -> None:
        self._endpoints = endpoints + _configured_endpoints() if include_configured and endpoints == INFERENCE_ENDPOINTS else endpoints
        self._domains = domains_by_id() if domains == SECURITY_DOMAINS else {d.domain_id: d for d in domains}

    def all_endpoints(self, *, domain_id: SecurityDomainId | None = None) -> list[InferenceEndpoint]:
        if domain_id is None:
            return sorted([endpoint for endpoint in self._endpoints if endpoint.enabled], key=lambda endpoint: (endpoint.priority, endpoint.endpoint_id))
        source = self._domains[domain_id]
        return sorted(
            [endpoint for endpoint in self._endpoints if endpoint.enabled and source.allows_domain(endpoint.security_domain_id)],
            key=lambda endpoint: (endpoint.priority, endpoint.endpoint_id),
        )

    def endpoints_for(
        self,
        *,
        capability: str,
        domain_id: SecurityDomainId,
    ) -> list[InferenceEndpoint]:
        source = self._domains[domain_id]
        return sorted(
            [
                endpoint
                for endpoint in self._endpoints
                if endpoint.enabled
                and capability in endpoint.capabilities
                and source.allows_domain(endpoint.security_domain_id)
            ],
            key=lambda endpoint: (endpoint.priority, endpoint.endpoint_id),
        )


def _configured_endpoints() -> tuple[InferenceEndpoint, ...]:
    raw = settings.freyja3_inference_endpoints_json.strip()
    if not raw:
        return ()
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(decoded, list):
        return ()
    endpoints: list[InferenceEndpoint] = []
    for entry in decoded:
        if not isinstance(entry, dict):
            continue
        try:
            endpoints.append(InferenceEndpoint.model_validate(entry))
        except Exception:
            continue
    return tuple(endpoints)
