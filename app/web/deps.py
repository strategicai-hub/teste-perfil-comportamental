"""Helpers compartilhados por `main.py` e pelos routers.

Estes helpers moravam em `main.py`. Ficam aqui porque um `APIRouter` em
`app/routers/*.py` não pode importar de `main.py` (import circular: `main` é quem
registra os routers). Nenhum comportamento mudou na extração — `main.py` reexporta
os nomes antigos (`_page_user`, `_shell_ctx`, ...) para as rotas que já existiam.
"""

import logging
import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import auth
from ..config import settings
from ..copsoq import report as copsoq_report
from ..db import Company, User, get_session

log = logging.getLogger(__name__)

APP_DIR = Path(__file__).parent.parent.parent
STATIC_DIR = APP_DIR / "static"
ASSETS_DIR = APP_DIR / "assets"
TEMPLATES_DIR = APP_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["base_path"] = settings.base_path
# Usado nas telas que mostram um link para copiar (cadastro público, link do consultor).
templates.env.globals["public_base_url"] = settings.public_base_url.rstrip("/")
# Paleta e rótulos do semáforo em um lugar só — usados pelo painel e pelo relatório.
templates.env.globals["nivel_cor"] = copsoq_report.NIVEL_COR
templates.env.globals["nivel_txt"] = copsoq_report.NIVEL_LABEL
# Mesma estrutura de blocos alimenta o painel gráfico e o relatório.
templates.env.filters["panorama"] = copsoq_report.build_report

# Mínimo de respondentes para exibir um recorte (anonimato — NR-1 / dado sensível).
MIN_RESPONDENTES = 3


# =========================================================================
# TEXTO / SLUG
# =========================================================================
def slugify(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    norm = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    return norm or "empresa"


def slug_unico(s, base: str) -> str:
    """Slug livre na tabela de companies, desambiguado com sufixo -2, -3..."""
    slug = base = slugify(base)
    i = 2
    while s.query(Company).filter(Company.slug == slug).first() is not None:
        slug = f"{base}-{i}"
        i += 1
    return slug


# =========================================================================
# DATAS (a operação toda é pensada no fuso de São Paulo)
# =========================================================================
try:
    SP_TZ = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:  # ambiente sem base de fusos (ver tzdata no requirements)
    log.warning("Base de fusos indisponível — usando UTC-3 fixo para as datas da campanha")
    SP_TZ = timezone(timedelta(hours=-3))


def hoje_sp() -> date:
    return datetime.now(SP_TZ).date()


def fim_do_dia_utc(data: date) -> datetime:
    """23:59:59 do dia informado em São Paulo, convertido para UTC (naive)."""
    local = datetime.combine(data, time(23, 59, 59), tzinfo=SP_TZ)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def para_data_local(dt: datetime) -> datetime:
    """UTC naive → horário de São Paulo, para exibir a data ao gestor."""
    return dt.replace(tzinfo=timezone.utc).astimezone(SP_TZ)


def fmt_data(dt: datetime | None) -> str:
    return para_data_local(dt).strftime("%d/%m/%Y") if dt else ""


def fmt_brl(centavos: int | None) -> str:
    valor = (centavos or 0) / 100
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


templates.env.filters["brl"] = fmt_brl
templates.env.filters["data_br"] = fmt_data


# =========================================================================
# SHELL / NAVEGAÇÃO
# =========================================================================
ROLE_LABEL = {
    auth.SUPER_ADMIN: "Owner",
    auth.CONSULTANT: "Consultor",
    auth.ADMIN: "Gestor",
    auth.MEMBER: "Colaborador",
}


def home_for_role(role: str) -> str:
    if role == auth.SUPER_ADMIN:
        return f"{settings.base_path}/admin"
    if role == auth.CONSULTANT:
        return f"{settings.base_path}/consultor"
    if role == auth.ADMIN:
        return f"{settings.base_path}/empresa"
    return f"{settings.base_path}/testes"


def shell_user(user: User, role: str | None = None) -> dict:
    nome = f"{user.nome} {user.sobrenome}".strip() or user.email
    r = role or user.role
    return {"nome": nome, "email": user.email, "role": r, "role_label": ROLE_LABEL.get(r, r)}


def shell_ctx(
    user: User,
    active: str,
    impersonating: str | None = None,
    role: str | None = None,
    trilha: list[dict] | None = None,
) -> dict:
    """Contexto do sidebar/topbar para qualquer página que estenda _shell.html."""
    return {
        "shell_user": shell_user(user, role),
        "active": active,
        "impersonating": impersonating,
        "trilha": trilha or [],
        "real_role": user.role,
    }


def safe_next(nxt: str | None) -> str | None:
    """Só aceita caminho local (evita open redirect)."""
    if nxt and nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt:
        return nxt
    return None


def redirect(path: str, ok: str | None = None, error: str | None = None, status_code: int = 302):
    """Redirect para uma rota interna, carregando a mensagem de ok/erro na query."""
    url = f"{settings.base_path}{path}"
    if ok:
        url += ("&" if "?" in url else "?") + f"ok={quote(ok)}"
    elif error:
        url += ("&" if "?" in url else "?") + f"error={quote(error)}"
    return RedirectResponse(url=url, status_code=status_code)


# =========================================================================
# GUARDAS DE PÁGINA (redirecionam para o login/home, em vez de 401/403)
# =========================================================================
def page_user(request: Request, *roles: str, allow_blocked: bool = False):
    """Retorna (user, None) se logado, com papel permitido e sem bloqueio de acesso.

    `allow_blocked=True` libera a página para quem está com o acesso suspenso
    (cadastro em análise ou inadimplência) — só as telas de pagamento, faturas e
    configurações da conta usam isso; é por lá que o cliente resolve a pendência.
    """
    user = auth.get_current_user_optional(request)
    if user is None:
        nxt = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return None, RedirectResponse(url=f"{settings.base_path}/entrar?next={quote(nxt)}", status_code=302)
    if roles and user.role not in roles:
        return None, RedirectResponse(url=home_for_role(user.role), status_code=302)
    if not allow_blocked:
        destino = destino_de_bloqueio(request, user)
        if destino is not None:
            return None, RedirectResponse(url=destino, status_code=302)
    return user, None


def destino_de_bloqueio(request: Request, user: User) -> str | None:
    """Para onde mandar o usuário quando o tenant dele está sem acesso liberado.

    Importado tarde de propósito: `billing` lê o banco e depende de `deps` para
    datas, então importar no topo fecharia um ciclo.
    """
    from .. import billing

    tenant_id = auth.get_effective_tenant_id(request, user)
    if not tenant_id:
        return None
    with get_session() as s:
        company = s.get(Company, tenant_id)
        acesso = billing.acesso(s, company, user.role)
    if not acesso.bloqueado:
        return None
    if acesso.motivo in ("pendente_aprovacao", "recusado"):
        return f"{settings.base_path}/cadastro/analise"
    return f"{settings.base_path}/pagamento"


# =========================================================================
# IMPERSONATION (cookie com a trilha Owner → Consultoria → Empresa)
# =========================================================================
def set_impersonation(response, trilha: list[str]) -> None:
    response.set_cookie(
        key=auth.IMPERSONATE_COOKIE,
        value=auth.make_impersonation_token(trilha),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=8 * 3600,
        path="/",
    )


def clear_impersonation(response) -> None:
    response.delete_cookie(key=auth.IMPERSONATE_COOKIE, path="/")


def trilha_ctx(request: Request, user: User) -> list[dict]:
    """Trilha para o banner do topo: onde o usuário está e por onde passou."""
    return [
        {"id": c.id, "nome": c.nome, "consultoria": c.kind == Company.KIND_CONSULTORIA}
        for c in auth.trilha_impersonation(request, user)
    ]


def ancestral_de(s, company: Company) -> list[str]:
    """Trilha completa até um tenant (consultoria dona primeiro, empresa depois).

    Entrar direto numa empresa filha sem esse caminho deixaria o "Voltar" pulando
    para o painel do owner, em vez de voltar para a consultoria.
    """
    cadeia = [company.id]
    pai_id = company.parent_id
    vistos = {company.id}
    while pai_id and pai_id not in vistos:
        pai = s.get(Company, pai_id)
        if pai is None:
            break
        cadeia.insert(0, pai.id)
        vistos.add(pai.id)
        pai_id = pai.parent_id
    return cadeia


def manager_tenant(request: Request, user: User):
    """Tenant efetivo do gestor (o próprio, ou o impersonado se super admin/consultor).

    Retorna (tenant_id, company, impersonating_nome|None) ou (None, None, None)
    quando quem está logado não tem tenant efetivo (deve ir para o painel dele).
    """
    tenant_id = auth.get_effective_tenant_id(request, user)
    if not tenant_id:
        return None, None, None
    with get_session() as s:
        company = s.get(Company, tenant_id)
        if company is None:
            return None, None, None
        impersonating = company.nome if user.role in (auth.SUPER_ADMIN, auth.CONSULTANT) else None
        return tenant_id, {"id": company.id, "nome": company.nome, "slug": company.slug}, impersonating


def gestor_page(request: Request, allow_blocked: bool = False):
    """Preâmbulo comum das páginas `/empresa/*`.

    Retorna `(user, tenant_id, company, impersonating, redirect)`. Quando `redirect`
    não é None, a rota deve devolvê-lo direto. Consultor sem empresa selecionada vai
    para o painel dele — consultoria não roda avaliação própria.
    """
    user, redir = page_user(
        request, auth.ADMIN, auth.CONSULTANT, auth.SUPER_ADMIN, allow_blocked=allow_blocked
    )
    if redir:
        return None, None, None, None, redir
    tenant_id, company, impersonating = manager_tenant(request, user)
    if not tenant_id:
        return None, None, None, None, RedirectResponse(url=home_for_role(user.role), status_code=302)
    with get_session() as s:
        alvo = s.get(Company, tenant_id)
        if alvo is not None and alvo.kind == Company.KIND_CONSULTORIA:
            return None, None, None, None, RedirectResponse(
                url=home_for_role(user.role), status_code=302
            )
    return user, tenant_id, company, impersonating, None
