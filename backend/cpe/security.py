import hashlib
import hmac
import secrets
import time
from fastapi import HTTPException, Request
from sqlalchemy import select
from .db import DB, User, Session, Case, Membership
from .config import settings


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return salt + ":" + digest


def verify_password(password, stored):
    try:
        salt, expected = stored.split(":")
        actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, expected)
    except ValueError:
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(request: Request):
    with DB() as db:
        bearer = request.headers.get("Authorization", "")
        if bearer.startswith("Bearer ") and settings.oidc_issuer:
            import jwt
            try:
                client = jwt.PyJWKClient(settings.oidc_jwks_url, cache_keys=True)
                key = client.get_signing_key_from_jwt(bearer[7:])
                claims = jwt.decode(bearer[7:], key.key, algorithms=["RS256"], audience=settings.oidc_audience,
                                    issuer=settings.oidc_issuer, options={"require": ["exp", "sub", "iss", "aud"]})
                # Explicit administrator provisioning; tokens cannot assign roles.
                user = db.scalar(select(User).where(User.email == claims.get("email"), User.enabled == True))
                if not user or claims.get("email_verified") is not True:
                    raise ValueError("Unprovisioned identity")
                return user
            except Exception:
                raise HTTPException(401, "Invalid or unprovisioned identity")
        token = request.cookies.get("cpe_session", "")
        session = db.scalar(select(Session).where(Session.token_hash == token_hash(token), Session.expires > time.time()))
        if not session:
            raise HTTPException(401, "Please sign in")
        user = db.get(User, session.user_id)
        if not user or not user.enabled:
            raise HTTPException(401, "Account unavailable")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), session.csrf):
                raise HTTPException(403, "Invalid CSRF token")
        request.state.csrf = session.csrf
        return user


def require_role(user, *roles):
    if user.role not in roles and user.role != "admin":
        raise HTTPException(403, "Role does not permit this action")


def authorized_case(db, user, case_id, write=False):
    case = db.get(Case, case_id)
    member = db.scalar(select(Membership.id).where(Membership.case_id == case_id, Membership.user_id == user.id))
    if not case or (user.role != "admin" and case.owner_id != user.id and not member):
        raise HTTPException(404, "Case not found")
    if write:
        require_role(user, "investigator", "reviewer")
    return case
