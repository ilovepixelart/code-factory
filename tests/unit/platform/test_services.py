import pytest

from code_factory.platform.services import Services


class Greeter:
    pass


def test_a_registered_service_is_found_by_its_class() -> None:
    services = Services()
    greeter = Greeter()
    services.add(Greeter, greeter)
    assert services.get(Greeter) is greeter


def test_a_later_registration_replaces_the_earlier_one() -> None:
    services = Services()
    services.add(Greeter, Greeter())
    replacement = Greeter()
    services.add(Greeter, replacement)
    assert services.get(Greeter) is replacement


def test_an_unregistered_service_is_a_sentence_naming_the_class_and_the_repair() -> None:
    with pytest.raises(LookupError) as raised:
        Services().get(Greeter)
    assert (
        str(raised.value) == "no service is registered for Greeter; list its module in app.MODULES"
    )
