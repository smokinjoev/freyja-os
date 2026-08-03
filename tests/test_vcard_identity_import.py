from __future__ import annotations

import pytest

from freyja.cli.identity_import_vcard import import_vcards
from freyja.identity.vcard import parse_vcards


VCARD = """BEGIN:VCARD
VERSION:3.0
UID:synthetic-contact-one
FN:Person One
NICKNAME:One
TEL;TYPE=CELL:+1 555 010 0001
EMAIL;TYPE=HOME:one@example.invalid
NOTE:folded
 value
END:VCARD
"""


def test_vcard_parses_unfolded_input_and_stable_identity() -> None:
    first = parse_vcards(VCARD)[0]
    second = parse_vcards(VCARD)[0]

    assert first.person_id == second.person_id
    assert first.person_id.startswith("contact-")
    assert "synthetic-contact-one" not in first.person_id
    assert first.preferred_name == "One"
    assert [(item.kind, item.value, item.label) for item in first.identities] == [
        ("phone", "+1 555 010 0001", "cell"),
        ("email", "one@example.invalid", "home"),
    ]


def test_vcard_requires_uid_and_full_name() -> None:
    with pytest.raises(ValueError, match="UID and FN"):
        parse_vcards("BEGIN:VCARD\nFN:Missing UID\nEND:VCARD\n")
    with pytest.raises(ValueError, match="UID and FN"):
        parse_vcards("BEGIN:VCARD\nUID:missing-name\nEND:VCARD\n")


def test_vcard_preserves_escaped_nickname_commas_and_rejects_encoded_values() -> None:
    escaped = VCARD.replace("NICKNAME:One", r"NICKNAME:One\, Primary,Uno")
    person = parse_vcards(escaped)[0]
    assert [alias.value for alias in person.aliases] == ["One, Primary", "Uno"]

    encoded = VCARD.replace("FN:Person One", "FN;ENCODING=QUOTED-PRINTABLE:Person=20One")
    with pytest.raises(ValueError, match="encoded vCard values"):
        parse_vcards(encoded)


def test_vcard_rejects_duplicate_identity() -> None:
    duplicate = VCARD + VCARD.replace("synthetic-contact-one", "synthetic-contact-two").replace(
        "Person One", "Person Two"
    ).replace("NICKNAME:One", "NICKNAME:Two")
    with pytest.raises(ValueError, match="duplicate identity"):
        parse_vcards(duplicate)


def test_vcard_dry_run_does_not_create_database(tmp_path) -> None:
    source = tmp_path / "contacts.vcf"
    source.write_text(VCARD)
    database = tmp_path / "identity.sqlite3"

    assert import_vcards(source, database, dry_run=True) == {
        "people": 1,
        "relationships": 0,
        "dry_run": True,
    }
    assert not database.exists()


def test_vcard_write_requires_explicit_replace(tmp_path) -> None:
    source = tmp_path / "contacts.vcf"
    source.write_text(VCARD)
    database = tmp_path / "identity.sqlite3"

    with pytest.raises(ValueError, match="--replace"):
        import_vcards(source, database)
    assert not database.exists()

    assert import_vcards(source, database, replace=True)["people"] == 1
    assert database.is_file()
