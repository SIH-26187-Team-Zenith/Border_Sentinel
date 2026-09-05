"""
app/schemas/user.py
Pydantic schemas for user identity and JWT payloads.
"""
from typing import Optional

from pydantic import BaseModel


class TokenPayload(BaseModel):
    """Claims extracted from a Supabase-issued JWT."""

    sub: str                        # Supabase user UUID
    email: Optional[str] = None
    role: Optional[str] = None      # "authenticated" | "anon" | custom DB role
    aud: Optional[str] = None
    exp: Optional[int] = None
    iat: Optional[int] = None


class UserOut(BaseModel):
    """Safe user representation returned to callers."""

    id: str
    email: str
    role: str = "authenticated"
