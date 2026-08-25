from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text()


def test_current_host_roles_are_documented() -> None:
    docs = "\n".join(
        [
            _read("README.md"),
            _read("ARCHITECTURE.md"),
            _read("deploy/compose/director/README.md"),
            _read("deploy/compose/signal/README.md"),
            _read("docs/REV1_STATUS.md"),
        ]
    )

    assert "Atlas" in docs and "Director" in docs and "control plane" in docs
    assert "local_reasoning" in docs and "gpt-oss:20b" in docs
    assert "Iris" in docs and "fast local inference" in docs
    assert "Atlas" in docs and "Signal connector" in docs
    assert "Tailscale" in docs
    assert "OpenRouter fallback requires" in docs
    assert "provider failure" in docs


def test_signal_docs_do_not_route_to_mars_director() -> None:
    signal_docs = "\n".join(
        [
            _read("README.md"),
            _read("deploy/compose/signal/.env.example"),
            _read("deploy/compose/signal/README.md"),
        ]
    )

    assert "Mars Director" not in signal_docs
    assert "<mars-tailscale-host>" not in signal_docs


def test_readme_current_architecture_names_atlas_as_director() -> None:
    readme = _read("README.md")
    current_architecture = readme.split("## Current phase", 1)[0]

    assert "- Atlas: Freyja Director" in current_architecture
    assert "- Mars: Freyja Director" not in current_architecture
    assert "not the authoritative Director host" in current_architecture


def test_director_deployment_docs_include_rev2_advisory_and_provider_health() -> None:
    docs = "\n".join(
        [
            _read("deploy/compose/director/.env.example"),
            _read("deploy/compose/director/README.md"),
        ]
    )

    assert "IRIS_ROUTER_ADVISORY_ENABLED=false" in docs
    assert "IRIS_ROUTER_CONFIDENCE_THRESHOLD=0.80" in docs
    assert "FREYJA_INFERENCE_PROVIDER_PROFILES" in docs
    assert "/providers/health" in docs


def test_rev2_status_document_tracks_current_implementation_candidate() -> None:
    plan = _read("docs/REV2_IMPLEMENTATION_PLAN.md")
    status = _read("docs/REV2_STATUS.md")

    assert "implementation not yet started" not in plan
    assert "docs/REV2_STATUS.md" in plan
    assert "docs/REV2_COMPLETION_AUDIT.md" in status
    assert "implementation candidate" in status
    assert "completion audit still active" in status
    assert "Provider profiles and readiness" in status
    assert "Rev 2 certification suite covers the 15 required release cases" in status
    assert "verifier support contract" in status
    assert "freyja-certify rev2-readiness" in status
    assert "expected latency-winning target" in status
    assert "any final cutover artifact is" in status
    assert "Connector production-check reports" in status
    assert "memory provenance audit report" in status
    assert "Approval exercise" in status
    assert "Local one-command selected-connector readiness bundle: `passed`" in status
    assert "Live local Rev 2 entrypoint check" in status
    assert "20260824T164147.173324Z0000-rev2-readiness.json" in status
    assert "LaunchAgent readiness bundle" in status
    assert "passed" in status
    assert "127.0.0.1:8000" in status
    assert "native operation handlers" in status
    assert "requiring Director approval" in status
    assert "Current LaunchAgent status scripts" in status
    assert "protected `/providers/health`, `/iris-router/health`, and" in status
    assert "MacAgent LaunchAgent loaded/running" in status
    assert "Current iMessage production check" in status
    assert "configured sender not locally known" in status
    assert "iMessage live-smoke dry-run" in status
    assert "`0` messages" in status
    assert "imessage-live-smoke-dry-run.json" in status
    assert "20260824T165012.276395Z0000-rev2-readiness.json" in status
    assert "failed only `imessage-live-smoke-report`" in status
    assert "Approved iMessage live-smoke attempt" in status
    assert "resolves the configured `joe=` allowlist alias" in status
    assert "existing chat id" in status
    assert "Messages scripting" in status
    assert "20260825T040632.268989Z0000-rev2-readiness.json" in status
    assert "local Messages/`imsg`" in status
    assert "send transport must be corrected" in status
    assert "Package wheel build via `pip wheel . --no-deps`: `passed`" in status
    assert "Installed-wheel preflight console check" in status
    assert "`dry_run_command` and" in status
    assert "Repository hygiene, compileall, and `git diff --check`: `passed`" in status
    assert "964 passed, 1 skipped, 1 warning" in status
    assert "Final operator handoff" in status
    assert "stops before readiness" in status
    assert "Do not mark Freya 2.0 complete from this status file alone" in status


def test_rev2_completion_audit_tracks_every_workstream() -> None:
    audit = _read("docs/REV2_COMPLETION_AUDIT.md")

    for workstream in (
        "A - Host and Deployment Alignment",
        "B - Provider Registry",
        "C - Iris 7B Route Classifier",
        "D - Tiered Routing",
        "E - Runtime Evidence and Latency",
        "F - MacAgent Boundary",
        "G - Capability Broker",
        "H - Trust-Aware External Workers",
        "I - Memory Provenance",
        "J - Certification",
    ):
        assert workstream in audit
    assert "Remaining proof before completion" in audit
    assert "Live local Rev 2 entrypoint" in audit
    assert "LaunchAgent readiness report" in audit
    assert "Current status scripts confirm the Director and MacAgent LaunchAgents" in audit
    assert "protected Rev 2 health" in audit
    assert "Current read-only iMessage production-check evidence" in audit
    assert "Installed-wheel preflight console command" in audit
    assert "iMessage read" in audit
    assert "unapproved-send denial" in audit
    assert "live-smoke dry-run" in audit
    assert "approved live-smoke attempt" in audit
    assert "resolves the configured" in audit
    assert "underlying `imsg send`" in audit
    assert "Messages AppleScript" in audit
    assert "20260825T040632.268989Z0000-rev2-readiness.json" in audit
    assert "failed only `imessage-live-smoke-report`" in audit
    assert "Do not mark the Freya 2.0 goal complete" in audit


def test_operations_todo_is_not_the_rev2_completion_gate() -> None:
    docs = _read("docs/FREYJA_OPERATIONS_TODO.md")

    assert "This file is an operator backlog, not the Freyja 2.0 completion gate" in docs
    assert "docs/REV2_STATUS.md" in docs
    assert "docs/REV2_COMPLETION_AUDIT.md" in docs
    assert "--require-smoke-report" in docs
    assert "operator actions" in docs


def test_certification_docs_describe_rev2_fixture_contract() -> None:
    docs = _read("certification/README.md")

    assert "SUPPORTED_EXPECTATION_KEYS" in docs
    assert "Rev 2 Certification Fixtures" in docs
    assert "certification_iris_recommendation" in docs
    assert "certification_provider_health" in docs
    assert "certification_capability_checks" in docs
    assert "worker_observation" in docs
    assert "They are not accepted production route fields" in docs
    assert "freyja-certify rev2-readiness" in docs
    assert "rev2-latency-probe" in docs
    assert "--benchmark-probe" in docs
    assert "scripts/rev2-readiness-bundle.py" in docs
    assert "--benchmark-report" in docs
    assert "--connector-report" in docs
    assert "--imessage-live-smoke" in docs
    assert "stops before readiness" in docs
    assert "add `--yes`" in docs
    assert "messaging-production-check.py" in docs
    assert "--output certification/reports/messaging-production-check.json" in docs
    assert "--memory-report" in docs
    assert "--approval-report" in docs
    assert "--latency-winner-target" in docs
    assert "--required-provider-profile heavy_local" in docs
    assert "same Atlas Director URL" in docs
    assert "rev2-approval-exercise" in docs
    assert "rev2-memory-audit" in docs
    assert "consequential action denied without approval" in docs
    assert "command fails" in docs
    assert "cutover artifact" in docs
    assert "scripts/rev2-preflight-status.py" in docs
    assert "freyja-rev2-preflight-status" in docs
    assert "preferred operator command" in _read("docs/REV2_STATUS.md")
    assert "the approval-only `--yes` command" in _read("docs/REV2_STATUS.md")
    assert "`dry_run_command`" in _read("docs/REV2_STATUS.md")
    assert "`final_command`" in _read("docs/REV2_STATUS.md")
    assert "`dry_run_command`" in docs
    assert "`final_command`" in docs
    assert "equivalent repository wrapper" in docs
    assert "--json" in docs
    assert "Exit code `0`" in docs
    assert "Exit code `0` means" in docs
    assert "/providers/health" in docs
    assert "/macagent/health" in docs


def test_macagent_boundary_is_documented_as_authenticated_and_non_authoritative() -> None:
    docs = "\n".join(
        [
            _read(".env.example"),
            _read("deploy/compose/director/.env.example"),
            _read("deploy/compose/director/README.md"),
        ]
    )

    assert "MACAGENT_TOKEN" in docs
    assert "scripts/run-macagent.py" in docs
    assert "scripts/install-macagent.sh" in docs
    assert "scripts/status-macagent.sh" in docs
    assert "authenticated health" in docs
    assert "without printing the token" in docs
    assert "/macagent/health" in docs
    assert "Private-network source address is not authorization" in docs
    assert "Atlas Director still decides identity" in docs
    assert "native operation handlers" in docs
    assert "approved iMessage replies" in docs
    assert "approved Shortcuts runs" in docs
    assert "iMessage live smoke" in docs
    assert "live-smoke" in docs
    assert "one-command path" in docs
    assert "--imessage-live-smoke" in docs
    assert "--yes" in docs
    assert "--output certification/reports/imessage-live-smoke-sent.json" in docs
    assert "--smoke-report" in docs
    assert "refuses recipients outside `IMESSAGE_ALLOWED_SENDERS`" in docs


def test_external_worker_boundary_is_documented_as_observations_not_actions() -> None:
    docs = _read("deploy/compose/director/README.md")

    assert "External-content workers" in docs
    assert "structured observations to Atlas" in docs
    assert "cannot invoke authoritative memory writes" in docs
    assert "normal Capability Broker before any action" in docs


def test_deployment_docs_do_not_commit_private_tailnet_addresses() -> None:
    checked_paths = [
        "deploy/compose/director/.env.example",
        "deploy/compose/director/README.md",
        "deploy/compose/signal/.env.example",
        "deploy/compose/signal/README.md",
    ]
    forbidden_fragments = ("100.", "10.", "192.168.")

    for path in checked_paths:
        content = _read(path)
        assert not any(fragment in content for fragment in forbidden_fragments), path
