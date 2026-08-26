"""
MIA Authentication — Password + JWT session management.
"""

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Request, WebSocket, HTTPException, status

from server.config import config

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Rate limiting storage
_login_attempts: dict[str, list[float]] = {}
MAX_ATTEMPTS = 5
ATTEMPT_WINDOW = 60  # seconds


def verify_password(plain_password: str) -> bool:
    """Verify password against configured password."""
    return plain_password == config.MIA_PASSWORD


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(hours=config.SESSION_EXPIRY_HOURS)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, config.JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        return payload
    except JWTError:
        return None


def check_rate_limit(client_ip: str) -> bool:
    """Check if login attempts are within rate limit."""
    now = time.time()
    if client_ip not in _login_attempts:
        _login_attempts[client_ip] = []

    # Clean old attempts
    _login_attempts[client_ip] = [
        t for t in _login_attempts[client_ip] if now - t < ATTEMPT_WINDOW
    ]

    if len(_login_attempts[client_ip]) >= MAX_ATTEMPTS:
        return False

    _login_attempts[client_ip].append(now)
    return True


def get_token_from_request(request: Request) -> Optional[str]:
    """Extract token from Authorization header or cookie."""
    # Check Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    # Check cookie
    return request.cookies.get("mia_token")


def get_token_from_websocket(websocket: WebSocket) -> Optional[str]:
    """Extract token from WebSocket query params or cookie."""
    token = websocket.query_params.get("token")
    if token:
        return token
    return websocket.cookies.get("mia_token")


async def require_auth(request: Request):
    """FastAPI dependency — require valid authentication."""
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return payload


async def require_ws_auth(websocket: WebSocket) -> bool:
    """Validate WebSocket authentication."""
    token = get_token_from_websocket(websocket)
    if not token:
        return False
    payload = verify_token(token)
    return payload is not None
