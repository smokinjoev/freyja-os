from __future__ import annotations

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
    ) -> None:
        self._endpoints = endpoints
        self._domains = domains_by_id() if domains == SECURITY_DOMAINS else {d.domain_id: d for d in domains}

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
