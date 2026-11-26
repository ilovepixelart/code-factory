"""The growth measure tells linear work from quadratic work."""

from growth import LINEAR_BOUND, growth


def _linear(n: int) -> None:
    sum(range(n))


def _quadratic(n: int) -> None:
    sum(i * j for i in range(n) for j in range(n))


def test_linear_work_stays_under_the_bound_and_quadratic_work_does_not() -> None:
    assert growth(_linear, 200_000) < LINEAR_BOUND
    assert growth(_quadratic, 150) > LINEAR_BOUND
