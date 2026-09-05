"""
app/api/routes/auth.py
Authentication routes:
  POST /auth/login  — exchange email+password for a Supabase JWT
  GET  /auth/me     — return identity of the currently authenticated user
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import get_current_user
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request / response schemas (local, not shared) ────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(body: LoginRequest) -> LoginResponse:
    """
    Authenticate with Supabase using email + password.
    Returns the Supabase-issued JWT on success.
    """
    from supabase import create_client  # lazy import — avoid top-level side-effects

    settings = get_settings()
    try:
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        response = client.auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
        return LoginResponse(access_token=response.session.access_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {exc}",
        )


@router.get("/me", response_model=UserOut)
async def me(
    current_user: Annotated[UserOut, Depends(get_current_user)],
) -> UserOut:
    """Return the identity of the currently authenticated user."""
    return current_user
