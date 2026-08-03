from __future__ import annotations

import json
from subprocess import CompletedProcess
from subprocess import TimeoutExpired

import pytest

from freyja.cli import identity_import_apple
from freyja.identity.apple_contacts import load_apple_contacts, people_from_apple_payload


def payload(*, identifier: str = "native-id-one", email: str = "one@example.invalid") -> dict:
    return {
        "contacts": [
            {
                "identifier": identifier,
                "display_name": "Person One",
                "nickname": "One",
                "phones": [{"label": "mobile", "value": "+1 555 010 0001"}],
                "emails": [{"label": "home", "value": email}],
            }
        ]
    }


def test_apple_payload_creates_stable_private_identity() -> None:
    first = people_from_apple_payload(payload())[0]
    second = people_from_apple_payload(payload())[0]

    assert first.person_id == second.person_id
    assert first.person_id.startswith("apple-")
    assert "native-id-one" not in first.person_id
    assert "native-id-one" not in json.dumps(first.metadata)
    assert first.display_name == "Person One"
    assert first.preferred_name == "One"
    assert [alias.value for alias in first.aliases] == ["One"]
    assert [(item.kind, item.value, item.label) for item in first.identities] == [
        ("phone", "+1 555 010 0001", "mobile"),
        ("email", "one@example.invalid", "home"),
    ]


def test_apple_payload_rejects_malformed_and_duplicate_records() -> None:
    with pytest.raises(ValueError, match="contacts array"):
        people_from_apple_payload([])
    with pytest.raises(ValueError, match="identifier and display_name"):
        people_from_apple_payload({"contacts": [{"identifier": "id", "display_name": ""}]})
    with pytest.raises(ValueError, match="string identifier"):
        people_from_apple_payload({"contacts": [{"identifier": 123, "display_name": "Person"}]})

    duplicate = payload()
    duplicate["contacts"].append(
        {
            "identifier": "native-id-two",
            "display_name": "Person Two",
            "nickname": "",
            "phones": [],
            "emails": [{"label": "", "value": "ONE@example.invalid"}],
        }
    )
    with pytest.raises(ValueError, match="duplicate identity"):
        people_from_apple_payload(duplicate)


def test_helper_output_is_parsed_without_exposing_stderr(monkeypatch, tmp_path) -> None:
    helper = tmp_path / "helper.swift"
    helper.write_text("// synthetic helper")
    monkeypatch.setattr(
        "freyja.identity.apple_contacts.subprocess.run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, json.dumps(payload()), "private helper detail"),
    )
    assert len(load_apple_contacts(helper_path=helper)) == 1

    monkeypatch.setattr(
        "freyja.identity.apple_contacts.subprocess.run",
        lambda *args, **kwargs: CompletedProcess(args[0], 2, "", "private helper detail"),
    )
    with pytest.raises(RuntimeError, match="Contacts permission") as error:
        load_apple_contacts(helper_path=helper)
    assert "private helper detail" not in str(error.value)

    def time_out(*args, **kwargs):
        raise TimeoutExpired(args[0], 1)

    monkeypatch.setattr("freyja.identity.apple_contacts.subprocess.run", time_out)
    with pytest.raises(RuntimeError, match="could not be run"):
        load_apple_contacts(helper_path=helper)


def test_permission_request_is_only_forwarded_when_explicit(monkeypatch, tmp_path) -> None:
    helper = tmp_path / "helper.swift"
    helper.write_text("// synthetic helper")
    commands = []

    def successful_run(command, **kwargs):
        commands.append(command)
        return CompletedProcess(command, 0, json.dumps(payload()), "")

    monkeypatch.setattr("freyja.identity.apple_contacts.subprocess.run", successful_run)
    load_apple_contacts(helper_path=helper)
    load_apple_contacts(helper_path=helper, request_access=True)

    assert commands[0] == ["/usr/bin/swift", str(helper)]
    assert commands[1] == ["/usr/bin/swift", str(helper), "--request-access"]


def test_apple_cli_dry_run_does_not_create_database(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        identity_import_apple,
        "load_apple_contacts",
        lambda **kwargs: people_from_apple_payload(payload()),
    )
    database = tmp_path / "identity.sqlite3"

    assert identity_import_apple.main(["--database", str(database), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out) == {"dry_run": True, "people": 1, "relationships": 0}
    assert not database.exists()


def test_apple_cli_requires_replace_before_writing(monkeypatch, tmp_path) -> None:
    called = False

    def unexpected_load(**kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(identity_import_apple, "load_apple_contacts", unexpected_load)
    with pytest.raises(SystemExit):
        identity_import_apple.main(["--database", str(tmp_path / "identity.sqlite3")])
    assert not called
