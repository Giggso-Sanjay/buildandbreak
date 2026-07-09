import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import greet, main


def test_greet_default():
    assert greet("World") == "Hello, World!"


def test_greet_custom_name():
    assert greet("Ada") == "Hello, Ada!"


def test_main_default_argv(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py"])
    main()
    assert capsys.readouterr().out == "Hello, World!\n"


def test_main_empty_name_falls_back_to_default(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", ""])
    main()
    assert capsys.readouterr().out == "Hello, World!\n"


def test_main_shout_uppercases_greeting(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "Claude", "--shout"])
    main()
    assert capsys.readouterr().out == "HELLO, CLAUDE!\n"


def test_main_shout_before_name(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "--shout", "Claude"])
    main()
    assert capsys.readouterr().out == "HELLO, CLAUDE!\n"


def test_main_shout_without_name_falls_back_to_default(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "--shout"])
    main()
    assert capsys.readouterr().out == "HELLO, WORLD!\n"
