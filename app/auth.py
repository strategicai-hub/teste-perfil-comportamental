import secrets
import uuid
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException, Request

from .config import settings
from .db import User, get_session

JWT_ALG = "HS256"
JWT_COOKIE = "tpc_session"
ADMIN_COOKIE = "tpc_admin"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(10)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def new_user_id() -> str:
    return uuid.uuid4().hex


def create_jwt(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALG)


def decode_jwt(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALG])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def get_current_user(request: Request) -> User:
    token = request.cookies.get(JWT_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado")
    user_id = decode_jwt(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sessão inválida")
    with get_session() as s:
        user = s.get(User, user_id)
        if user is None or user.blocked:
            raise HTTPException(status_code=401, detail="Usuário inválido")
        s.expunge(user)
        return user


def get_current_user_optional(request: Request) -> User | None:
    try:
        return get_current_user(request)
    except HTTPException:
        return None


def make_admin_cookie() -> str:
    return jwt.encode(
        {"admin": settings.admin_user, "exp": datetime.utcnow() + timedelta(hours=12)},
        settings.jwt_secret,
        algorithm=JWT_ALG,
    )


def is_admin_cookie_valid(cookie_value: str | None) -> bool:
    if not cookie_value:
        return False
    try:
        payload = jwt.decode(cookie_value, settings.jwt_secret, algorithms=[JWT_ALG])
        return payload.get("admin") == settings.admin_user and bool(settings.admin_user)
    except jwt.PyJWTError:
        return False


def require_admin(request: Request) -> bool:
    cookie_value = request.cookies.get(ADMIN_COOKIE)
    if not is_admin_cookie_valid(cookie_value):
        raise HTTPException(status_code=401, detail="Admin não autenticado")
    return True


def generate_reset_token() -> str:
    return secrets.token_hex(32)
