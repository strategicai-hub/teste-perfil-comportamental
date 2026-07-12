import secrets
import uuid
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException, Request

from .config import settings
from .db import Company, User, get_session

JWT_ALG = "HS256"
JWT_COOKIE = "tpc_session"
# Cookie separado (JWT curto e assinado) usado só quando o super admin "entra"
# num tenant. Nunca reescrevemos o tpc_session — impersonation é uma camada acima.
IMPERSONATE_COOKIE = "tpc_impersonate"

SUPER_ADMIN = "super_admin"
ADMIN = "admin"
MEMBER = "member"


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
    # Só `sub`. Papel e tenant NUNCA saem do JWT para autorização — são relidos do
    # banco a cada request (ver get_current_user). Assim JWTs antigos continuam
    # válidos e um rebaixamento de papel tem efeito imediato.
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


# ---------------------------------------------------------------------------
# Papéis / autorização (fonte de verdade é o User carregado do banco)
# ---------------------------------------------------------------------------
def is_super_admin(user: User | None) -> bool:
    return bool(user and user.role == SUPER_ADMIN)


def is_admin(user: User | None) -> bool:
    return bool(user and user.role in (ADMIN, SUPER_ADMIN))


def require_super_admin(request: Request) -> User:
    user = get_current_user(request)
    if user.role != SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Acesso restrito")
    return user


def require_admin_or_super(request: Request) -> User:
    user = get_current_user(request)
    if user.role not in (ADMIN, SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Acesso restrito")
    return user


# ---------------------------------------------------------------------------
# Impersonation — super admin "entra" num tenant
# ---------------------------------------------------------------------------
def make_impersonation_token(tenant_id: str) -> str:
    return jwt.encode(
        {"imp": tenant_id, "exp": datetime.utcnow() + timedelta(hours=8)},
        settings.jwt_secret,
        algorithm=JWT_ALG,
    )


def decode_impersonation_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALG])
        return payload.get("imp")
    except jwt.PyJWTError:
        return None


def get_effective_tenant_id(request: Request, user: User) -> str | None:
    """Tenant que o usuário está enxergando.

    Só o super admin pode impersonar; qualquer outro papel ignora o cookie de
    impersonation (defesa contra cookie forjado/rebaixamento). O tenant do cookie
    é validado contra o banco a cada request.
    """
    if user.role != SUPER_ADMIN:
        return user.tenant_id
    token = request.cookies.get(IMPERSONATE_COOKIE)
    if token:
        tid = decode_impersonation_token(token)
        if tid:
            with get_session() as s:
                if s.get(Company, tid) is not None:
                    return tid
    return user.tenant_id


def generate_reset_token() -> str:
    return secrets.token_hex(32)
