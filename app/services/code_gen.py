import secrets

from sqlalchemy.orm import Session

from app.models.link import Link

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
CODE_LENGTH = 7


def _random_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LENGTH))


def generate_unique_code(db: Session) -> str:
    while True:
        code = _random_code()
        if db.get(Link, code) is None:
            return code
