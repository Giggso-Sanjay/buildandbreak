def factorial(n: int) -> int:
    if n < 0:
        raise ValueError("factorial is not defined for negative numbers")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def is_palindrome(s: str) -> bool:
    normalized = s.lower()
    return normalized == normalized[::-1]


def unique_items(items: list) -> list:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


if __name__ == "__main__":
    print(f"5! = {factorial(5)}")
    print(f"'level' is palindrome: {is_palindrome('level')}")
    print(f"Unique items: {unique_items([1, 2, 2, 3, 1, 4])}")
