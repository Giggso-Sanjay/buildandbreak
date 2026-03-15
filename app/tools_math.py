import math
from typing import Any, Dict
import sys

def math_add(a: float, b: float) -> float:
    return a + b


def math_multiply(a: float, b: float) -> float:
    return a * b


def math_eval(expression: str) -> float:
    """
    Safely evaluate a basic mathematical expression.
    This is intentionally limited; extend as needed.
    """
    allowed_names = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}

    code = compile(expression, "<math_eval>", "eval")
    for name in code.co_names:
        if name not in allowed_names:
            raise ValueError(f"Use of name '{name}' is not allowed in math_eval")

    return float(eval(code, {"__builtins__": {}}, allowed_names))


def sanjay_profit(n: int, m: int) -> int:
    """
    Example tool: compute n! + m!

    This is just for verifying that the agent is calling tools.
    """
    print(f"jay_profit called with n={n}, m={m} sanjay", file=sys.stderr)
    return math.factorial(int(n)) + math.factorial(int(m))
