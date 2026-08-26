"""
MIA Auth Routes — Login, logout, session validation.
"""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from server.auth import (
    verify_password,
    create_access_token,
    verify_token,
    check_rate_limit,
    get_token_from_request,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: str = ""
    message: str = ""


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, body: LoginRequest, response: Response):
    """Authenticate and return JWT token."""
    client_ip = request.client.host if request.client else "unknown"

    # Rate limit check
    if not check_rate_limit(client_ip):
        return LoginResponse(
            success=False,
            message="Too many login attempts. Try again in 60 seconds.",
        )

    # Verify password
    if not verify_password(body.password):
        return LoginResponse(success=False, message="Invalid password.")

    # Create token
    token = create_access_token({"sub": "mia_user", "ip": client_ip})

    # Set cookie
    response.set_cookie(
        key="mia_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=86400,  # 24 hours
    )

    return LoginResponse(success=True, token=token, message="Welcome to MIA!")


@router.post("/logout")
async def logout(response: Response):
    """Clear session cookie."""
    response.delete_cookie("mia_token")
    return {"success": True, "message": "Logged out."}


@router.get("/session")
async def check_session(request: Request):
    """Check if current session is valid."""
    token = get_token_from_request(request)
    if not token:
        return {"authenticated": False}

    payload = verify_token(token)
    if not payload:
        return {"authenticated": False}

    return {"authenticated": True, "user": payload.get("sub")}
