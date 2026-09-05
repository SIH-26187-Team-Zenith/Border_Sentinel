"""
tests/test_auth.py
Authentication endpoint tests.

Note: /auth/login is NOT tested against Supabase here — we only have
placeholder credentials.  We test the JWT path (decode + /auth/me)
which is fully self-contained.
"""


# ── /auth/me — unauthenticated ─────────────────────────────────────────────────

def test_me_no_token_is_401(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_garbage_token_is_401(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
    assert r.status_code == 401
    assert "Invalid token" in r.json()["detail"]


def test_me_malformed_header_is_401(client):
    """Wrong scheme (Basic instead of Bearer) → 401 from HTTPBearer."""
    r = client.get("/auth/me", headers={"Authorization": "Basic abc123"})
    assert r.status_code == 401


# ── /auth/me — authenticated ──────────────────────────────────────────────────

def test_me_valid_token_returns_user(client, auth_headers):
    r = client.get("/auth/me", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "test-uuid-1234"
    assert data["email"] == "dev@test.local"
    assert data["role"] == "authenticated"


def test_me_valid_token_shape(client, auth_headers):
    """Response must include id, email, role — no extras that leak internals."""
    r = client.get("/auth/me", headers=auth_headers)
    assert set(r.json().keys()) == {"id", "email", "role"}
