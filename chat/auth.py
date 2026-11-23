"""Firebase ID-token check, using Google's public signing certificates (no admin credentials)."""
from __future__ import annotations

from typing import Callable

FIREBASE_PROJECT = "kodiwise-9adab"


class AuthError(Exception):
    pass


def verify_firebase_token(token: str, project: str = FIREBASE_PROJECT) -> dict:
    """Returns {"uid", "name"} for a valid, unexpired token issued for this Firebase project."""
    import google.auth.transport.requests
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_firebase_token(
            token, google.auth.transport.requests.Request(), audience=project)
    except Exception as exc:
        raise AuthError("invalid token") from exc
    if not claims or not claims.get("sub"):
        raise AuthError("invalid token")
    return {"uid": str(claims["sub"]), "name": str(claims.get("name") or "")}


TokenVerifier = Callable[[str], dict]
