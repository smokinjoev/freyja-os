from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_homepod_shortcut_runbook_documents_siri_phrase_and_transport() -> None:
    content = (REPO_ROOT / "docs" / "HOMEPOD_SHORTCUTS.md").read_text()

    assert "Tell Freyja" in content
    assert "Hey Siri, Tell Freyja" in content
    assert "iMessage connector" in content
    assert "Home Assistant safety policy is unchanged" in content


def test_homepod_shortcut_verifier_exists_and_checks_runtime_keys() -> None:
    script = REPO_ROOT / "scripts" / "verify-homepod-shortcut-path.sh"
    content = script.read_text()

    assert "IMESSAGE_ENABLED" in content
    assert "IMESSAGE_ALLOWED_SENDERS" in content
    assert "FREYJA_DIRECTOR_URL" in content
    assert "FREYJA_CONNECTOR_TOKEN" in content
