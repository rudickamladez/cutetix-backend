from datetime import datetime, timedelta, timezone
import base64
import hashlib
import secrets
from typing import Optional
import html
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric import rsa

from app.database import get_db
from app.models import OAuthAuthorizationCode, User
from app.schemas.settings import settings
from app.services import auth as auth_service
from app.services.user import get_by_username
from app.middleware import auth as auth_middleware


router = APIRouter(
    tags=["oauth"],
)


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _base64url(digest)


def _get_allowed_redirect_uris() -> list[str]:
    if settings.mcp_oauth_redirect_uris:
        return settings.mcp_oauth_redirect_uris
    return [
        "https://chatgpt.com/connector_platform_oauth_redirect",
        "https://platform.openai.com/apps-manage/oauth",
    ]


def _validate_client(client_id: str) -> None:
    if not settings.mcp_oauth_client_id or client_id != settings.mcp_oauth_client_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid client_id")


def _require_redirect_uri(redirect_uri: str) -> None:
    allowed = _get_allowed_redirect_uris()
    if redirect_uri not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid redirect_uri")


def _validate_scope(scope: str) -> list[str]:
    supported = settings.mcp_oauth_scopes_supported or list(auth_middleware.OAUTH_SCOPES.keys())
    requested = [s for s in scope.split() if s]
    for item in requested:
        if item not in supported:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scope")
    return requested


def _validate_pkce(code_challenge: str, code_challenge_method: str) -> None:
    if code_challenge_method != "S256":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code_challenge_method")
    if not code_challenge:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code_challenge")


def _validate_client_secret(request: Request, client_id: str, client_secret: Optional[str]) -> None:
    supported = settings.mcp_oauth_token_endpoint_auth_methods_supported or ["none"]
    if "none" in supported:
        return
    if not settings.mcp_oauth_client_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Client authentication required")

    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
            header_client_id, header_secret = decoded.split(":", 1)
            if header_client_id == client_id and header_secret == settings.mcp_oauth_client_secret:
                return
        except Exception:
            pass

    if client_secret and client_secret == settings.mcp_oauth_client_secret:
        return

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid client_secret")


def _render_login_form(
    *,
    error: Optional[str],
    params: dict,
) -> HTMLResponse:
    error_html = f"<p style='color:#b00020'>{error}</p>" if error else ""
    hidden_inputs = "\n".join(
        f"<input type='hidden' name='{html.escape(str(key))}' value='{html.escape(str(value or ''))}'>"
        for key, value in params.items()
        if key not in {"username", "password"}
    )
    page = f"""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>OAuth Login</title>
    <style>
      body {{ font-family: Arial, sans-serif; max-width: 420px; margin: 40px auto; padding: 0 12px; }}
      label {{ display: block; margin-top: 12px; }}
      input {{ width: 100%; padding: 8px; margin-top: 4px; }}
      button {{ margin-top: 16px; padding: 10px 14px; }}
    </style>
  </head>
  <body>
    <h2>Sign in</h2>
    {error_html}
    <form method="post" action="/oauth/authorize">
      {hidden_inputs}
      <label>Username
        <input type="text" name="username" required />
      </label>
      <label>Password
        <input type="password" name="password" required />
      </label>
      <button type="submit">Continue</button>
    </form>
  </body>
</html>
"""
    return HTMLResponse(content=page)


@router.get("/oauth/authorize", response_class=HTMLResponse, include_in_schema=False)
async def oauth_authorize_get(
    response_type: str = "code",
    client_id: str = "",
    redirect_uri: str = "",
    scope: str = "",
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "",
    resource: str = "",
):
    if response_type != "code":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported response_type")
    _validate_client(client_id)
    _require_redirect_uri(redirect_uri)
    _validate_pkce(code_challenge, code_challenge_method)
    _validate_scope(scope)

    params = {
        "response_type": response_type,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "resource": resource,
    }

    if settings.mcp_oauth_frontend_login_url:
        return RedirectResponse(
            url=f"{settings.mcp_oauth_frontend_login_url}?{urlencode(params)}"
        )

    return _render_login_form(error=None, params=params)


@router.post("/oauth/authorize", response_class=HTMLResponse, include_in_schema=False)
async def oauth_authorize_post(
    response_type: str = Form("code"),
    client_id: str = Form(""),
    redirect_uri: str = Form(""),
    scope: str = Form(""),
    state: str = Form(""),
    code_challenge: str = Form(""),
    code_challenge_method: str = Form(""),
    resource: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    if response_type != "code":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported response_type")

    _validate_client(client_id)
    _require_redirect_uri(redirect_uri)
    _validate_pkce(code_challenge, code_challenge_method)
    requested_scopes = _validate_scope(scope)

    user = get_by_username(username, db=db)
    if not user or not auth_service.verify_password(password, user.hashed_password):
        params = {
            "response_type": response_type,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "resource": resource,
        }
        return _render_login_form(error="Invalid credentials", params=params)

    if user.disabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")

    effective_scopes = [s for s in requested_scopes if s in (user.scopes or [])]
    code = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    oauth_code = OAuthAuthorizationCode(
        code=code,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=effective_scopes,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        resource=resource or "",
        expires_at=expires_at,
        user_uuid=user.uuid,
    )
    db.add(oauth_code)
    db.commit()

    redirect = f"{redirect_uri}?code={code}"
    if state:
        redirect += f"&state={state}"
    return RedirectResponse(url=redirect, status_code=status.HTTP_302_FOUND)


@router.post("/oauth/token", include_in_schema=False)
async def oauth_token(
    request: Request,
    grant_type: str = Form(""),
    code: str = Form(""),
    redirect_uri: str = Form(""),
    client_id: str = Form(""),
    client_secret: Optional[str] = Form(None),
    code_verifier: str = Form(""),
    db: Session = Depends(get_db),
):
    if grant_type != "authorization_code":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported grant_type")

    _validate_client(client_id)
    _require_redirect_uri(redirect_uri)
    _validate_client_secret(request, client_id, client_secret)

    oauth_code = db.query(OAuthAuthorizationCode).filter(
        OAuthAuthorizationCode.code == code
    ).first()
    if not oauth_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")
    if oauth_code.redirect_uri != redirect_uri or oauth_code.client_id != client_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")
    expires_at = oauth_code.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        db.delete(oauth_code)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code expired")

    if not code_verifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code_verifier")
    expected_challenge = _pkce_challenge(code_verifier)
    if oauth_code.code_challenge != expected_challenge:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code_verifier")

    user = db.query(User).filter(User.uuid == oauth_code.user_uuid).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

    token_scopes = oauth_code.scope or []
    refresh_token, refresh_family = auth_service.create_refresh_token(
        user=user,
        db=db,
        token_scopes=token_scopes,
    )
    access_payload = {
        "sub": user.username,
        "rtfid": refresh_family,
        "scope": token_scopes,
    }
    if oauth_code.resource:
        access_payload["aud"] = oauth_code.resource
    access_token = auth_service.sign_token(
        payload=access_payload,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )

    db.delete(oauth_code)
    db.commit()

    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "refresh_token": refresh_token,
            "scope": " ".join(token_scopes),
        }
    )


@router.get("/.well-known/jwks.json", include_in_schema=False)
async def jwks():
    public_key = load_pem_public_key(settings.jwt_public.encode("utf-8"))
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid public key")
    numbers = public_key.public_numbers()
    n = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    e = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
    jwk = {
        "kty": "RSA",
        "use": "sig",
        "kid": _base64url(hashlib.sha256(n).digest())[:16],
        "alg": settings.jwt_algorithm,
        "n": _base64url(n),
        "e": _base64url(e),
    }
    return JSONResponse({"keys": [jwk]})
