import pytest

from sample import add, greet
from sample2 import is_even, is_not_even, multiply, reverse_string
from sample3 import factorial, is_palindrome, unique_items


def test_greet():
    assert greet("Raven") == "Hello, Raven!"


def test_add():
    assert add(2, 3) == 5


def test_multiply():
    assert multiply(4, 5) == 20


def test_is_even():
    assert is_even(4) is True
    assert is_even(7) is False


def test_is_not_even():
    assert is_not_even(9) is True
    assert is_not_even(4) is False


def test_reverse_string():
    assert reverse_string("buildandbreak") == "kaerbdnadliub"


def test_factorial():
    assert factorial(5) == 120
    assert factorial(0) == 1


def test_factorial_negative_raises():
    with pytest.raises(ValueError):
        factorial(-1)


def test_is_palindrome():
    assert is_palindrome("level") is True
    assert is_palindrome("hello") is False


def test_unique_items():
    assert unique_items([1, 2, 2, 3, 1, 4]) == [1, 2, 3, 4]
