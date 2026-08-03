from __future__ import annotations

from freyja.identity import Alias, Identity, IdentityService, Person, Relationship, default_identity_service


def test_identity_service_resolves_aliases_and_channel_identifiers() -> None:
    service = IdentityService(
        people=[
            Person(
                person_id="joe",
                display_name="Joseph Smith",
                preferred_name="Joe",
                aliases=(Alias("Dad"), Alias("Father")),
                identities=(
                    Identity(kind="phone", value="+1 (555) 123-4567"),
                    Identity(kind="email", value="JOE@example.com"),
                    Identity(kind="signal", value="+15551234567"),
                    Identity(kind="imessage", value="joe@example.com"),
                    Identity(kind="calendar", value="joe-cal"),
                ),
            )
        ]
    )

    assert service.resolve("Dad").person_id == "joe"
    assert service.resolve("Father").person_id == "joe"
    assert service.resolve("Joseph Smith").person_id == "joe"
    assert service.resolve("+15551234567").person_id == "joe"
    assert service.resolve("joe@example.com").person_id == "joe"
    assert service.resolve_signal_sender("+1 555 123 4567").person_id == "joe"
    assert service.resolve_imessage_sender("JOE@example.com").person_id == "joe"
    assert service.resolve_calendar_owner("joe-cal").person_id == "joe"


def test_relationships_are_queryable() -> None:
    joe = Person(person_id="joe", display_name="Joe")
    beth = Person(person_id="beth", display_name="Beth")
    daughter = Person(person_id="daughter", display_name="Daughter")
    service = IdentityService(
        people=[joe, beth, daughter],
        relationships=[
            Relationship("joe", "spouse", "beth"),
            Relationship("joe", "child", "daughter"),
        ],
    )

    assert [person.person_id for person in service.related_people("joe", "spouse")] == ["beth"]
    assert [person.person_id for person in service.related_people("joe", "child")] == ["daughter"]


def test_default_identity_service_models_family_aliases() -> None:
    service = default_identity_service()

    assert service.resolve("Dad").person_id == "joe"
    assert service.resolve("Joseph").person_id == "joe"
    assert service.resolve("Mom").person_id == "beth"
    assert service.related_people("joe", "spouse")[0].person_id == "beth"
