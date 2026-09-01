from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "freyja5-readiness-bundle.py"


def load_bundle_module():
    spec = importlib.util.spec_from_file_location("freyja5_readiness_bundle", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freyja5_readiness_bundle_builds_expected_commands(tmp_path: Path) -> None:
    bundle = load_bundle_module()
    args = bundle.build_parser().parse_args(
        [
            "--base-url",
            "http://atlas.test:8500",
            "--token",
            "secret-token",
            "--output-dir",
            str(tmp_path),
            "--python",
            "python",
            "--timeout",
            "2.5",
            "--run-certification",
            "--run-smoke",
            "--skip-media",
        ]
    )

    assert bundle.build_certification_command(args) == [
        "python",
        "-m",
        "certification.cli",
        "routing/freyja5_architecture",
        "--provider",
        "freyja5",
        "--output-dir",
        str(tmp_path),
    ]
    assert bundle.build_smoke_command(args) == [
        "python",
        "scripts/freyja5-smoke.py",
        "--base-url",
        "http://atlas.test:8500",
        "--timeout",
        "2.5",
        "--output",
        str(tmp_path / "freyja5-smoke.json"),
        "--token",
        "secret-token",
        "--skip-media",
    ]


def test_freyja5_readiness_bundle_reports_source_ready_but_live_blocked(tmp_path: Path) -> None:
    bundle = load_bundle_module()
    certification = tmp_path / "cert.json"
    certification.write_text(
        """
{
  "metadata": {"suite_name": "freyja5-architecture", "overall_score": 1.0},
  "passed": true,
  "cases": [
    {
      "runtime_context": {
        "rev2_evidence": {
          "freyja5_certification": {
            "targets": [
              {"target": "A", "case": "a-gateway-to-freyja-to-vulcan", "name": "gateway-to-freyja-to-vulcan", "proves": ["joe_test_channel_gateway_handoff"]},
              {"target": "B", "case": "b-freyja-to-cloyd-delegation", "name": "freyja-to-cloyd-delegation", "proves": ["freyja_delegates_to_cloyd"]},
              {"target": "C", "case": "c-iris-calendar-tool", "name": "iris-calendar-tool", "proves": ["iris_apple_mcp_boundary"]},
              {"target": "D", "case": "d-media-vision-pathway", "name": "media-vision-pathway", "proves": ["webgui_inline_media_normalization"]},
              {"target": "E", "case": "e-multi-channel-household-identity", "name": "multi-channel-household-identity", "proves": ["same_user_cross_channel_resolution"]},
              {"target": "F", "case": "f-benedict-enclave-local-only", "name": "benedict-enclave-local-only", "proves": ["benedict_paralegal_private_agent_boundary"]},
              {"target": "G", "case": "g-optional-service-disabled", "name": "optional-service-disabled", "proves": ["optional_service_failure_isolated"]}
            ]
          },
          "freyja5_trace_summary": {
            "trace_id": "trace-1",
            "channel": "open-webui",
            "resolved_user": "person:joe",
            "authenticated_subject": "person:joe",
            "actor_principal": "person:joe",
            "memory_scopes": ["agent:freyja", "family", "system"],
            "agent": "freyja",
            "requested_route": "general",
            "actual_endpoint": "vulcan-nexus-strong",
            "actual_provider": "nexus",
            "actual_model": "@preset/freyja-strong-local",
            "actual_runtime": "nexus",
            "selected_tools": [],
            "tool_calls": [],
            "delegation": [],
            "machine": "vulcan",
            "latency_ms": 1.0,
            "failures": [],
            "fallbacks": [],
            "inference_status": "not_run",
            "egress_state": "local-only"
          }
        }
      }
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    smoke = tmp_path / "smoke.json"
    smoke.write_text(
        """
{
  "report_type": "freyja5-smoke",
  "passed": true,
  "token_configured": true,
  "checks": [
    {"name": "health"},
    {
      "name": "readiness",
      "readiness_ok": true,
      "openai_model": "freyja-5",
      "webgui_default_model": "agent-smith",
      "webgui_freyja5_opt_in": true,
      "mcp_hosts": ["atlas", "iris"],
      "mcp_server_ids": ["iris-apple-mcp", "atlas-household-mcp", "atlas-media-mcp"],
      "mcp_agent_ids": ["freyja", "cloyd-gibbler", "benedict", "benedict-paralegal", "agent-47", "jennacide"],
      "mcp_agent_grant_counts": {
        "freyja": 11,
        "cloyd-gibbler": 9,
        "benedict": 8,
        "benedict-paralegal": 3,
        "agent-47": 7,
        "jennacide": 7
      },
      "certification_targets": ["A", "B", "C", "D", "E", "F", "G"]
    },
    {"name": "chat_text"}
  ]
}
""".strip(),
        encoding="utf-8",
    )

    report = bundle.build_report(certification_report=certification, smoke_report=smoke)

    assert report["passed"] is False
    assert report["source_ready"] is True
    assert report["live_blocked"] is True
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["freyja5-certification-report"]["ok"] is True
    assert checks["freyja5-certification-report"]["target_matrix_evidence"] is True
    assert checks["freyja5-certification-report"]["trace_evidence"] is True
    assert checks["freyja5-smoke-report"]["ok"] is True
    assert checks["freyja5-smoke-report"]["readiness_architecture_evidence"] is True
    assert checks["freyja5-live-blockers"]["status"] == "blocked"
    assert checks["freyja5-live-blockers"]["remaining"] == [
        "msty_go_always_on_linux_validation",
        "vulcan_nexus_presets",
        "iris_apple_session",
        "hera_voice_avatar_hardware",
        "live_tool_sessions",
        "vulcan_nexus_private_preset",
    ]
    assert checks["freyja5-live-blockers"]["blockers"][0] == {
        "id": "msty_go_always_on_linux_validation",
        "component": "atlas",
        "requires": [
            "install_path",
            "service_definition",
            "restart_behavior",
            "local_config_export_story",
            "health_endpoint_or_equivalent",
            "source_controlled_agent_definition_compatibility",
        ],
        "next_actions": [
            "On Atlas, install or locate Msty Go and record the non-secret install path.",
            "Create or inspect the always-on Linux service definition, then validate start, stop, restart, and reboot recovery.",
            "Run scripts/freyja5-export-agent-definitions.py --output certification/reports/freyja5-agent-definitions.json and compare any Msty Go import/export against that non-secret source-controlled artifact.",
            "Capture the Msty Go health endpoint or equivalent operational proof.",
        ],
    }


def test_freyja5_readiness_bundle_rejects_stale_certification_without_target_matrix(tmp_path: Path) -> None:
    bundle = load_bundle_module()
    certification = tmp_path / "cert.json"
    certification.write_text(
        """
{
  "metadata": {"suite_name": "freyja5-architecture", "overall_score": 1.0},
  "passed": true,
  "cases": []
}
""".strip(),
        encoding="utf-8",
    )

    report = bundle.build_report(certification_report=certification, smoke_report=None)
    checks = {check["name"]: check for check in report["checks"]}

    assert report["source_ready"] is False
    assert checks["freyja5-certification-report"]["ok"] is False
    assert checks["freyja5-certification-report"]["target_matrix_evidence"] is False
    assert checks["freyja5-certification-report"]["trace_evidence"] is False


def test_freyja5_readiness_bundle_rejects_certification_without_trace_evidence(tmp_path: Path) -> None:
    bundle = load_bundle_module()
    certification = tmp_path / "cert.json"
    certification.write_text(
        """
{
  "metadata": {"suite_name": "freyja5-architecture", "overall_score": 1.0},
  "passed": true,
  "cases": [
    {
      "runtime_context": {
        "rev2_evidence": {
          "freyja5_certification": {
            "targets": [
              {"target": "A", "case": "a-gateway-to-freyja-to-vulcan", "name": "gateway-to-freyja-to-vulcan", "proves": ["joe_test_channel_gateway_handoff"]},
              {"target": "B", "case": "b-freyja-to-cloyd-delegation", "name": "freyja-to-cloyd-delegation", "proves": ["freyja_delegates_to_cloyd"]},
              {"target": "C", "case": "c-iris-calendar-tool", "name": "iris-calendar-tool", "proves": ["iris_apple_mcp_boundary"]},
              {"target": "D", "case": "d-media-vision-pathway", "name": "media-vision-pathway", "proves": ["webgui_inline_media_normalization"]},
              {"target": "E", "case": "e-multi-channel-household-identity", "name": "multi-channel-household-identity", "proves": ["same_user_cross_channel_resolution"]},
              {"target": "F", "case": "f-benedict-enclave-local-only", "name": "benedict-enclave-local-only", "proves": ["benedict_paralegal_private_agent_boundary"]},
              {"target": "G", "case": "g-optional-service-disabled", "name": "optional-service-disabled", "proves": ["optional_service_failure_isolated"]}
            ]
          }
        }
      }
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    report = bundle.build_report(certification_report=certification, smoke_report=None)
    checks = {check["name"]: check for check in report["checks"]}

    assert report["source_ready"] is False
    assert checks["freyja5-certification-report"]["target_matrix_evidence"] is True
    assert checks["freyja5-certification-report"]["trace_evidence"] is False


def test_freyja5_readiness_bundle_rejects_stale_smoke_without_readiness_architecture(
    tmp_path: Path,
) -> None:
    bundle = load_bundle_module()
    smoke = tmp_path / "smoke.json"
    smoke.write_text(
        """
{
  "report_type": "freyja5-smoke",
  "passed": true,
  "token_configured": true,
  "checks": [{"name": "health"}, {"name": "readiness"}, {"name": "chat_text"}]
}
""".strip(),
        encoding="utf-8",
    )

    report = bundle.build_report(certification_report=None, smoke_report=smoke)
    checks = {check["name"]: check for check in report["checks"]}

    assert report["source_ready"] is False
    assert checks["freyja5-smoke-report"]["ok"] is False
    assert checks["freyja5-smoke-report"]["readiness_architecture_evidence"] is False


def test_freyja5_readiness_bundle_rejects_smoke_without_agent_mcp_grants(tmp_path: Path) -> None:
    bundle = load_bundle_module()
    smoke = tmp_path / "smoke.json"
    smoke.write_text(
        """
{
  "report_type": "freyja5-smoke",
  "passed": true,
  "token_configured": true,
  "checks": [
    {"name": "health"},
    {
      "name": "readiness",
      "readiness_ok": true,
      "openai_model": "freyja-5",
      "webgui_default_model": "agent-smith",
      "webgui_freyja5_opt_in": true,
      "mcp_hosts": ["atlas", "iris"],
      "mcp_server_ids": ["iris-apple-mcp", "atlas-household-mcp", "atlas-media-mcp"],
      "certification_targets": ["A", "B", "C", "D", "E", "F", "G"]
    },
    {"name": "chat_text"}
  ]
}
""".strip(),
        encoding="utf-8",
    )

    report = bundle.build_report(certification_report=None, smoke_report=smoke)
    checks = {check["name"]: check for check in report["checks"]}

    assert report["source_ready"] is False
    assert checks["freyja5-smoke-report"]["ok"] is False
    assert checks["freyja5-smoke-report"]["readiness_architecture_evidence"] is False


def test_freyja5_readiness_bundle_fails_missing_artifacts() -> None:
    bundle = load_bundle_module()

    report = bundle.build_report(certification_report=None, smoke_report=None)

    assert report["passed"] is False
    assert report["source_ready"] is False
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["freyja5-certification-report"]["status"] == "not supplied"
    assert checks["freyja5-smoke-report"]["status"] == "not supplied"
