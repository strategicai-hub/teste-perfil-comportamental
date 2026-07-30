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

SUPER_ADMIN = "super_admin"   # o owner — vê consultorias e empresas
CONSULTANT = "consultant"     # consultor — vê só as empresas trazidas por ele
ADMIN = "admin"               # gestor da empresa
MEMBER = "member"             # colaborador


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
# Impersonation — o owner "entra" numa consultoria e dela numa empresa;
# o consultor entra nas empresas dele. O cookie guarda a TRILHA, não um id só:
# sem isso, entrar na empresa a partir da consultoria apagaria o caminho de volta.
# ---------------------------------------------------------------------------
def make_impersonation_token(trilha: list[str]) -> str:
    return jwt.encode(
        {"imp": list(trilha), "exp": datetime.utcnow() + timedelta(hours=8)},
        settings.jwt_secret,
        algorithm=JWT_ALG,
    )


def decode_impersonation_token(token: str) -> list[str]:
    """Aceita o formato novo (lista) e o legado (string) — cookies já emitidos valem."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return []
    imp = payload.get("imp")
    if isinstance(imp, str):
        return [imp] if imp else []
    if isinstance(imp, list):
        return [t for t in imp if isinstance(t, str) and t]
    return []


def pode_impersonar(user: User, company: Company) -> bool:
    """Regra de quem pode entrar em qual tenant.

    - owner: qualquer tenant;
    - consultor: só empresas cujo `parent_id` é a consultoria dele;
    - resto: ninguém (defesa contra cookie forjado).
    """
    if company is None:
        return False
    if user.role == SUPER_ADMIN:
        return True
    if user.role == CONSULTANT:
        return (
            bool(user.tenant_id)
            and company.parent_id == user.tenant_id
            and company.kind == Company.KIND_EMPRESA
        )
    return False


def trilha_impersonation(request: Request, user: User) -> list[Company]:
    """Trilha válida do cookie, revalidada no banco a cada request.

    Cada elo tem de ser filho do anterior — uma trilha forjada com dois tenants sem
    parentesco é truncada no primeiro elo inválido.
    """
    if user.role not in (SUPER_ADMIN, CONSULTANT):
        return []
    token = request.cookies.get(IMPERSONATE_COOKIE)
    if not token:
        return []
    ids = decode_impersonation_token(token)
    if not ids:
        return []
    validos: list[Company] = []
    with get_session() as s:
        for tid in ids:
            company = s.get(Company, tid)
            if company is None:
                break
            if not validos:
                if not pode_impersonar(user, company):
                    break
            elif company.parent_id != validos[-1].id:
                break
            s.expunge(company)
            validos.append(company)
    return validos


def get_effective_tenant_id(request: Request, user: User) -> str | None:
    """Tenant que o usuário está enxergando: o último elo válido da trilha, ou o dele."""
    trilha = trilha_impersonation(request, user)
    if trilha:
        return trilha[-1].id
    return user.tenant_id


def generate_reset_token() -> str:
    return secrets.token_hex(32)
