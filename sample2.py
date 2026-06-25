def multiply(a: int, b: int) -> int:
    return a * b


def is_even(n: int) -> bool:
    return n % 2 == 0

def is_not_even(n: int) -> bool:
    return n % 2 != 0


def reverse_string(s: str) -> str:
    return s[::-1]


if __name__ == "__main__":
    print(f"4 * 5 = {multiply(4, 5)}")
    print(f"7 is even: {is_even(7)}")
    print(f"9 is odd : {is_not_even(9)}")
    print(f"Reversed 'buildandbreak': {reverse_string('buildandbreak')}")
