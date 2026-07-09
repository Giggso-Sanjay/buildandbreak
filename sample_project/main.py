import sys


def greet(name: str) -> str:
    return f"Hello, {name}!"


def main() -> None:
    args = sys.argv[1:]
    shout = "--shout" in args
    args = [arg for arg in args if arg != "--shout"]
    name = args[0] if args and args[0] else "World"
    greeting = greet(name)
    if shout:
        greeting = greeting.upper()
    print(greeting)


if __name__ == "__main__":
    main()
