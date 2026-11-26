"""The owner's writes: a notice, rows changed in one transaction, and the images that undo them."""

from code_factory.memory_extras.models import MemoryChanged


def test_a_change_answers_its_images_for_the_route_to_keep() -> None:
    assert list(MemoryChanged.model_fields) == ["notice", "restore"]
