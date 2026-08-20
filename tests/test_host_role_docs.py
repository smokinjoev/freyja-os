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
