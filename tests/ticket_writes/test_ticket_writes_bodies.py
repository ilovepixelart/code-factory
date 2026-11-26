"""The route bodies name exactly the fields the ticket-writes service takes."""

from code_factory.ticket_writes.models import CREATE_FIELDS, EDITABLE
from code_factory.ticket_writes.routes import CreateBody, EditBody
from code_factory.ticket_writes.rules import known_repository
from code_factory.tickets.models import DEFAULT_REPOSITORY


def test_a_new_tickets_body_takes_the_create_fields_and_its_repository() -> None:
    assert set(CreateBody.model_fields) == {*CREATE_FIELDS, "repository"}


def test_an_edits_body_takes_the_editable_fields() -> None:
    assert set(EditBody.model_fields) == set(EDITABLE)


def test_a_repository_is_known_as_the_board_offers_it() -> None:
    assert known_repository("sample", tracked={"sample"}, filed=set())
    assert known_repository("old", tracked={"sample"}, filed={"old"})
    assert known_repository(DEFAULT_REPOSITORY, tracked=set(), filed=set())
    assert not known_repository(DEFAULT_REPOSITORY, tracked={"sample"}, filed=set())
    assert not known_repository("typo", tracked={"sample"}, filed={"old"})
