import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import greet


def test_greet_default():
    assert greet("World") == "Hello, World!"


def test_greet_custom_name():
    assert greet("Ada") == "Hello, Ada!"
