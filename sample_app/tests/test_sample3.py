"""Tests for sample_app/sample3.py."""

import pytest

from sample_app.sample3 import is_prime


@pytest.mark.parametrize(
    "n,expected",
    [
        (0, False),
        (1, False),
        (2, True),
        (3, True),
        (4, False),
        (9, False),
        (17, True),
        (25, False),
        (-7, False),
    ],
)
def test_is_prime(n: int, expected: bool) -> None:
    assert is_prime(n) is expected
