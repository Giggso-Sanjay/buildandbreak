"""
Hardcoded JWT Bearer auth for API testing (Postman, frontend).
Token has no practical expiration (exp: year 2099).

Postman: Authorization → Type: Bearer Token → paste the token below.
"""

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Hardcoded JWT for testing — use in Postman: Authorization → Bearer Token
# Payload: {"sub": "test-user", "iat": 1735689600, "exp": 4070908800} (expires 2099)
# Token (copy for Postman):
# eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXIiLCJpYXQiOjE3MzU2ODk2MDAsImV4cCI6NDA3MDkwODgwMH0.49JDWZ45SFFkBSQUV9aiy682SvKMcOpfhTRF1rhMNy4
BEARER_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXIiLCJpYXQiOjE3MzU2ODk2MDAsImV4cCI6NDA3MDkwODgwMH0.49JDWZ45SFFkBSQUV9aiy682SvKMcOpfhTRF1rhMNy4"
JWT_SECRET = "orca-test-secret-for-testing-only-32chars"

security = HTTPBearer(auto_error=True)


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    """Validate Bearer token; return decoded payload or raise 401."""
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
