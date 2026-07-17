def add(a: int, b: int) -> int:
    return a + b


def is_palindrome(s: str) -> bool:
    return s == s[::-1]


def factorial(n: int) -> int:
    return 1 if n <= 1 else n * factorial(n - 1)


if __name__ == "__main__":
    print(f"3 + 4 = {add(3, 4)}")
    print(f"'level' is palindrome: {is_palindrome('level')}")
    print(f"5! = {factorial(5)}")
