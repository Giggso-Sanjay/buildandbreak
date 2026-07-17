"""Tests for sample_app/sample3.py."""

import pytest

from sample_app.sample3 import add, factorial, is_palindrome, is_prime


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (3, 4, 7),
        (0, 0, 0),
        (-2, 2, 0),
        (-3, -4, -7),
    ],
)
def test_add(a: int, b: int, expected: int) -> None:
    assert add(a, b) == expected


@pytest.mark.parametrize(
    "s,expected",
    [
        ("level", True),
        ("racecar", True),
        ("hello", False),
        ("", True),
        ("a", True),
    ],
)
def test_is_palindrome(s: str, expected: bool) -> None:
    assert is_palindrome(s) is expected


@pytest.mark.parametrize(
    "n,expected",
    [
        (0, 1),
        (1, 1),
        (5, 120),
    ],
)
def test_factorial(n: int, expected: int) -> None:
    assert factorial(n) == expected


def test_factorial_negative_raises() -> None:
    with pytest.raises(ValueError):
        factorial(-5)


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
