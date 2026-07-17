def add(a: int, b: int) -> int:
    return a + b


def is_palindrome(s: str) -> bool:
    return s == s[::-1]


def factorial(n: int) -> int:
    if n < 0:
        raise ValueError("factorial is undefined for negative numbers")
    return 1 if n <= 1 else n * factorial(n - 1)


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    for divisor in range(2, int(n**0.5) + 1):
        if n % divisor == 0:
            return False
    return True


if __name__ == "__main__":
    print(f"3 + 4 = {add(3, 4)}")
    print(f"'level' is palindrome: {is_palindrome('level')}")
    print(f"5! = {factorial(5)}")
    print(f"17 is prime: {is_prime(17)}")
