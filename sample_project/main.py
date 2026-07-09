import sys


def greet(name: str) -> str:
    return f"Hello, {name}!"


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else "World"
    print(greet(name))


if __name__ == "__main__":
    main()
