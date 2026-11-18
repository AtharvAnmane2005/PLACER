"""
Verifies a Google "Sign in with Google" ID token (a JWT signed by Google,
handed to us by the frontend's Google Identity Services widget).

This is the client-secret-free flow: the frontend never talks to our
backend with a raw password, and we never hold a Google client secret —
we just verify Google's signature on a token Google already vetted.
Kept in its own module (rather than inline in auth_service.py) so tests
can monkeypatch `verify_google_token` without making a real network call
to Google's certs endpoint.
"""
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel, EmailStr

from app.core.config import get_settings

settings = get_settings()


class GoogleNotConfiguredError(RuntimeError):
    """GOOGLE_CLIENT_ID is blank — a server misconfiguration, not a bad login."""


class GoogleCredentialError(ValueError):
    """The credential Google handed us failed verification (bad/expired/wrong audience)."""


class GoogleVerificationUnavailableError(RuntimeError):
    """We could not reach Google's certificate endpoint to verify the token."""


class GoogleTokenPayload(BaseModel):
    sub: str
    email: EmailStr
    email_verified: bool
    name: str | None = None


def verify_google_token(credential: str) -> GoogleTokenPayload:
    if not settings.GOOGLE_CLIENT_ID:
        raise GoogleNotConfiguredError(
            "GOOGLE_CLIENT_ID is not configured. Set it in .env — see "
            "PROJECT_PROGRESS.md for how to obtain a free OAuth client ID."
        )
    try:
        idinfo = id_token.verify_oauth2_token(
            credential, google_requests.Request(), settings.GOOGLE_CLIENT_ID
        )
    except ValueError as exc:
        # google-auth raises ValueError for malformed tokens, bad signatures,
        # expired tokens, and audience mismatches. Surface it as a credential
        # problem (401) rather than pretending the server is misconfigured.
        raise GoogleCredentialError("Google credential could not be verified.") from exc
    except GoogleAuthError as exc:
        # Transport/cert-fetch failures are transient and not the user's fault.
        raise GoogleVerificationUnavailableError(
            "Could not reach Google to verify the credential."
        ) from exc

    return GoogleTokenPayload(
        sub=idinfo["sub"],
        email=idinfo["email"],
        email_verified=idinfo.get("email_verified", False),
        name=idinfo.get("name"),
    )
