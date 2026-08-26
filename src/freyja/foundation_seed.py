from __future__ import annotations

from freyja.foundation_models import (
    InferenceEndpoint,
    Machine,
    MemoryClassification,
    PersistentAgent,
    SecurityDomain,
    SecurityDomainId,
    ToolCapabilityGrant,
    normalize_agent_key,
)


FREYJA_HOUSEHOLD_DOMAIN = SecurityDomain(
    domain_id=SecurityDomainId.HOUSEHOLD,
    display_name="Freyja household domain",
    classification_floor=MemoryClassification.PRIVATE,
    allowed_domain_ids=frozenset(
        {
            SecurityDomainId.FREYJA_HOUSEHOLD,
            SecurityDomainId.PERSON_JOE,
            SecurityDomainId.PERSON_BETH,
            SecurityDomainId.PERSON_LIAM,
            SecurityDomainId.PERSON_JENNA,
            SecurityDomainId.SYSTEM,
        }
    ),
)

LEGACY_FREYJA_HOUSEHOLD_DOMAIN = SecurityDomain(
    domain_id=SecurityDomainId.FREYJA_HOUSEHOLD,
    display_name="Legacy Freyja household compatibility domain",
    classification_floor=MemoryClassification.PRIVATE,
    allowed_domain_ids=frozenset({SecurityDomainId.HOUSEHOLD}),
)

JOE_DOMAIN = SecurityDomain(
    domain_id=SecurityDomainId.PERSON_JOE,
    display_name="Joe private domain",
    parent_domain_id=SecurityDomainId.HOUSEHOLD,
    allowed_domain_ids=frozenset({SecurityDomainId.HOUSEHOLD, SecurityDomainId.SYSTEM}),
    classification_floor=MemoryClassification.PRIVATE,
)

BETH_DOMAIN = SecurityDomain(
    domain_id=SecurityDomainId.PERSON_BETH,
    display_name="Beth private domain",
    parent_domain_id=SecurityDomainId.HOUSEHOLD,
    allowed_domain_ids=frozenset({SecurityDomainId.HOUSEHOLD, SecurityDomainId.SYSTEM}),
    classification_floor=MemoryClassification.PRIVATE,
)

LIAM_DOMAIN = SecurityDomain(
    domain_id=SecurityDomainId.PERSON_LIAM,
    display_name="Liam private domain",
    parent_domain_id=SecurityDomainId.HOUSEHOLD,
    allowed_domain_ids=frozenset({SecurityDomainId.HOUSEHOLD, SecurityDomainId.SYSTEM}),
    classification_floor=MemoryClassification.PRIVATE,
)

JENNA_DOMAIN = SecurityDomain(
    domain_id=SecurityDomainId.PERSON_JENNA,
    display_name="Jenna private domain",
    parent_domain_id=SecurityDomainId.HOUSEHOLD,
    allowed_domain_ids=frozenset({SecurityDomainId.HOUSEHOLD, SecurityDomainId.SYSTEM}),
    classification_floor=MemoryClassification.PRIVATE,
)

SYSTEM_DOMAIN = SecurityDomain(
    domain_id=SecurityDomainId.SYSTEM,
    display_name="Infrastructure system domain",
    allowed_domain_ids=frozenset({SecurityDomainId.HOUSEHOLD}),
    classification_floor=MemoryClassification.ROUTINE,
)

PARALEGAL_ENCLAVE_DOMAIN = SecurityDomain(
    domain_id=SecurityDomainId.PARALEGAL,
    display_name="Paralegal enclave",
    classification_floor=MemoryClassification.RESTRICTED,
)

LEGACY_PARALEGAL_ENCLAVE_DOMAIN = SecurityDomain(
    domain_id=SecurityDomainId.PARALEGAL_ENCLAVE,
    display_name="Legacy paralegal enclave compatibility domain",
    classification_floor=MemoryClassification.RESTRICTED,
    allowed_domain_ids=frozenset({SecurityDomainId.PARALEGAL}),
)

SECURITY_DOMAINS: tuple[SecurityDomain, ...] = (
    FREYJA_HOUSEHOLD_DOMAIN,
    LEGACY_FREYJA_HOUSEHOLD_DOMAIN,
    JOE_DOMAIN,
    BETH_DOMAIN,
    LIAM_DOMAIN,
    JENNA_DOMAIN,
    SYSTEM_DOMAIN,
    PARALEGAL_ENCLAVE_DOMAIN,
    LEGACY_PARALEGAL_ENCLAVE_DOMAIN,
)

MACHINES: tuple[Machine, ...] = (
    Machine(
        machine_id="iris",
        display_name="Iris",
        role="apple-runtime-hot-reflex",
        security_domain_id=SecurityDomainId.HOUSEHOLD,
        capabilities=frozenset({"agent.runtime", "apple.messages", "apple.calendar", "apple.mail", "apple.music", "macagent", "home-assistant.client", "vulcan.client", "general.local"}),
    ),
    Machine(
        machine_id="atlas",
        display_name="Atlas",
        role="persistent-infrastructure",
        security_domain_id=SecurityDomainId.HOUSEHOLD,
        capabilities=frozenset({"agent.gateway", "agent.hosting", "home-assistant", "memory", "events", "scheduler", "messaging", "audit", "observability"}),
    ),
    Machine(
        machine_id="vulcan",
        display_name="Vulcan",
        role="primary-inference-appliance",
        security_domain_id=SecurityDomainId.HOUSEHOLD,
        capabilities=frozenset({"ollama", "lm-studio", "openai-compatible", "general.large", "code.large", "vision.large", "embeddings.local"}),
    ),
    Machine(
        machine_id="hera",
        display_name="Hera",
        role="avatar-perception-edge",
        security_domain_id=SecurityDomainId.HOUSEHOLD,
        capabilities=frozenset({"avatar", "voice", "camera", "audio", "presence", "occupancy", "semantic.events", "vision.edge"}),
    ),
    Machine(
        machine_id="mars",
        display_name="Mars",
        role="worker-ingestion-monitoring",
        security_domain_id=SecurityDomainId.HOUSEHOLD,
        capabilities=frozenset({"monitoring", "testing", "fallback"}),
    ),
)

PERSISTENT_AGENTS: tuple[PersistentAgent, ...] = (
    PersistentAgent(
        agent_id="freyja",
        display_name="Freyja",
        owner="household",
        security_domain_id=SecurityDomainId.HOUSEHOLD,
        home_machine_id="atlas",
        aliases=frozenset({"family", "household", "home"}),
        tool_grants=frozenset({"web.search", "weather.current", "browser.control", "calendar.read", "email.read", "messaging.send", "home-assistant.read", "home-assistant.control", "macagent.apple", "vision.inspect", "music.control", "scheduling.create", "memory.shared", "system.health"}),
        private_memory_scope="agent:freyja",
        shared_memory_scopes=frozenset({"family", "system"}),
    ),
    PersistentAgent(
        agent_id="cloyd-gibbler",
        display_name="Cloyd Gibbler",
        owner="person:joe",
        security_domain_id=SecurityDomainId.PERSON_JOE,
        home_machine_id="atlas",
        aliases=frozenset({"cloyd", "joe"}),
        capabilities=frozenset({"code.inspect", "code.edit", "code.test"}),
        tool_grants=frozenset({"web.search", "weather.current", "calendar.read", "email.read", "messaging.send", "macagent.apple", "shell.run", "filesystem.read", "filesystem.write", "git.inspect", "git.write", "coding.execute", "documents.process", "vision.inspect", "memory.private", "memory.shared", "system.health"}),
        private_memory_scope="person:joe",
        shared_memory_scopes=frozenset({"family", "system"}),
    ),
    PersistentAgent(
        agent_id="benedict",
        display_name="Benedict",
        owner="person:beth",
        security_domain_id=SecurityDomainId.PERSON_BETH,
        home_machine_id="atlas",
        aliases=frozenset({"beth"}),
        tool_grants=frozenset({"web.search", "weather.current", "calendar.read", "email.read", "messaging.send", "documents.process", "vision.inspect", "memory.private", "memory.shared", "system.health"}),
        private_memory_scope="person:beth",
        shared_memory_scopes=frozenset({"family", "system"}),
    ),
    PersistentAgent(
        agent_id="agent-44",
        display_name="Agent 44",
        owner="person:liam",
        security_domain_id=SecurityDomainId.PERSON_LIAM,
        home_machine_id="atlas",
        aliases=frozenset({"agent 44", "agent_44", "liam"}),
        tool_grants=frozenset({"web.search", "weather.current", "calendar.read", "messaging.send", "vision.inspect", "memory.private", "memory.shared", "system.health"}),
        private_memory_scope="person:liam",
        shared_memory_scopes=frozenset({"family", "system"}),
    ),
    PersistentAgent(
        agent_id="jenna",
        display_name="Jenna",
        owner="person:jenna",
        security_domain_id=SecurityDomainId.PERSON_JENNA,
        home_machine_id="atlas",
        aliases=frozenset({"jenna-agent"}),
        tool_grants=frozenset({"web.search", "weather.current", "calendar.read", "messaging.send", "vision.inspect", "memory.private", "memory.shared", "system.health"}),
        private_memory_scope="person:jenna",
        shared_memory_scopes=frozenset({"family", "system"}),
    ),
)

TOOL_CAPABILITIES: tuple[ToolCapabilityGrant, ...] = (
    ToolCapabilityGrant(tool_id="web.search", category="web", display_name="Web search", required_permission="tool:web.search"),
    ToolCapabilityGrant(tool_id="weather.current", category="weather", display_name="Weather", required_permission="tool:weather.read"),
    ToolCapabilityGrant(tool_id="browser.control", category="browser", display_name="Browser", required_permission="tool:browser.control", machine_affinity="iris"),
    ToolCapabilityGrant(tool_id="calendar.read", category="calendar", display_name="Calendar read", required_permission="tool:calendar.read", machine_affinity="iris"),
    ToolCapabilityGrant(tool_id="email.read", category="email", display_name="Email read", required_permission="tool:email.read", machine_affinity="iris"),
    ToolCapabilityGrant(tool_id="messaging.send", category="messaging", display_name="Messaging", required_permission="tool:messaging.send", mutation=True, machine_affinity="iris"),
    ToolCapabilityGrant(tool_id="home-assistant.read", category="home_assistant", display_name="Home Assistant read", required_permission="tool:home_assistant.read", machine_affinity="atlas"),
    ToolCapabilityGrant(tool_id="home-assistant.control", category="home_assistant", display_name="Home Assistant control", required_permission="tool:home_assistant.control", mutation=True, machine_affinity="atlas"),
    ToolCapabilityGrant(tool_id="macagent.apple", category="macagent", display_name="Mac Agent", required_permission="tool:macagent.apple", machine_affinity="iris"),
    ToolCapabilityGrant(tool_id="shell.run", category="shell", display_name="Shell", required_permission="tool:shell.run", mutation=True),
    ToolCapabilityGrant(tool_id="filesystem.read", category="filesystem", display_name="Filesystem read", required_permission="tool:filesystem.read"),
    ToolCapabilityGrant(tool_id="filesystem.write", category="filesystem", display_name="Filesystem write", required_permission="tool:filesystem.write", mutation=True),
    ToolCapabilityGrant(tool_id="git.inspect", category="git", display_name="Git inspect", required_permission="tool:git.inspect"),
    ToolCapabilityGrant(tool_id="git.write", category="git", display_name="Git write", required_permission="tool:git.write", mutation=True),
    ToolCapabilityGrant(tool_id="coding.execute", category="coding", display_name="Coding", required_permission="tool:coding.execute"),
    ToolCapabilityGrant(tool_id="documents.process", category="documents", display_name="Documents/PDF", required_permission="tool:documents.process"),
    ToolCapabilityGrant(tool_id="vision.inspect", category="vision", display_name="Vision", required_permission="tool:vision.inspect"),
    ToolCapabilityGrant(tool_id="music.control", category="music", display_name="Music", required_permission="tool:music.control", mutation=True, machine_affinity="iris"),
    ToolCapabilityGrant(tool_id="scheduling.create", category="scheduling", display_name="Scheduling", required_permission="tool:scheduling.create", mutation=True, machine_affinity="atlas"),
    ToolCapabilityGrant(tool_id="memory.private", category="memory", display_name="Private memory", required_permission="tool:memory.private"),
    ToolCapabilityGrant(tool_id="memory.shared", category="memory", display_name="Shared memory", required_permission="tool:memory.shared"),
    ToolCapabilityGrant(tool_id="system.health", category="system", display_name="System health", required_permission="tool:system.health"),
)

INFERENCE_ENDPOINTS: tuple[InferenceEndpoint, ...] = (
    InferenceEndpoint(
        endpoint_id="iris-fast",
        display_name="Iris fast local endpoint",
        provider="ollama",
        machine_id="iris",
        capabilities=frozenset({"general.local", "chat", "summarization"}),
        security_domain_id=SecurityDomainId.HOUSEHOLD,
        priority=10,
    ),
    InferenceEndpoint(
        endpoint_id="vulcan-reason",
        display_name="Vulcan heavy reasoning endpoint",
        provider="ollama",
        machine_id="vulcan",
        base_url="http://100.94.80.21:11434",
        model="qwen3-coder-next:q4_K_M",
        capabilities=frozenset({"general.large", "chat", "reasoning", "long_context"}),
        security_domain_id=SecurityDomainId.HOUSEHOLD,
        priority=10,
    ),
    InferenceEndpoint(
        endpoint_id="vulcan-code",
        display_name="Vulcan code endpoint",
        provider="ollama",
        machine_id="vulcan",
        base_url="http://100.94.80.21:11434",
        model="qwen3-coder-next:q4_K_M",
        capabilities=frozenset({"code.large", "coding"}),
        security_domain_id=SecurityDomainId.HOUSEHOLD,
        priority=10,
    ),
    InferenceEndpoint(
        endpoint_id="vulcan-vision",
        display_name="Vulcan vision endpoint",
        provider="ollama",
        machine_id="vulcan",
        base_url="http://100.94.80.21:11434",
        model="minicpm-v",
        capabilities=frozenset({"vision.large"}),
        security_domain_id=SecurityDomainId.HOUSEHOLD,
        priority=10,
    ),
    InferenceEndpoint(
        endpoint_id="vulcan-embeddings",
        display_name="Vulcan embeddings endpoint",
        provider="ollama",
        machine_id="vulcan",
        base_url="http://100.94.80.21:11434",
        model="nomic-embed-text",
        capabilities=frozenset({"embeddings.local"}),
        security_domain_id=SecurityDomainId.HOUSEHOLD,
        priority=10,
    ),
    InferenceEndpoint(
        endpoint_id="approved-cloud-premium",
        display_name="Approved cloud provider behind Privacy/Egress Gate",
        provider="openrouter",
        model="openai/gpt-4o-mini",
        capabilities=frozenset({"premium", "vision.cloud", "general.cloud"}),
        security_domain_id=SecurityDomainId.SYSTEM,
        priority=50,
    ),
    InferenceEndpoint(
        endpoint_id="paralegal-local",
        display_name="Paralegal enclave endpoint",
        provider="ollama",
        machine_id="vulcan",
        base_url="http://100.94.80.21:11434",
        capabilities=frozenset({"chat", "document_review", "legal_research", "embeddings.local"}),
        security_domain_id=SecurityDomainId.PARALEGAL,
        priority=10,
    ),
)


def domains_by_id() -> dict[SecurityDomainId, SecurityDomain]:
    return {domain.domain_id: domain for domain in SECURITY_DOMAINS}


def agents_by_key() -> dict[str, PersistentAgent]:
    agents: dict[str, PersistentAgent] = {}
    for agent in PERSISTENT_AGENTS:
        agents[normalize_agent_key(agent.agent_id)] = agent
        agents[normalize_agent_key(agent.display_name)] = agent
        for alias in agent.aliases:
            agents[normalize_agent_key(alias)] = agent
    return agents


def tools_by_id() -> dict[str, ToolCapabilityGrant]:
    return {tool.tool_id: tool for tool in TOOL_CAPABILITIES}
