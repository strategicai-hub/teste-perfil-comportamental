"""Painel do consultor.

O consultor não roda avaliação própria: a consultoria é um tenant "guarda-chuva". O
que ele faz aqui é (a) acompanhar as empresas dele, (b) aprovar quem se cadastrou pelo
link dele e (c) entrar em cada empresa para operar por dentro.

Aprovar empresa vinda do link do consultor é responsabilidade **dele** — essas
empresas não entram na fila do owner (ver `routers/admin_billing.py`).
"""

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from .. import auth, queries
from ..config import settings
from ..db import Company, User, get_session
from ..web import deps

router = APIRouter()


def _consultoria(request: Request, user: User) -> Company | None:
    """Consultoria de quem está logado (ou a que o owner está visitando)."""
    tenant_id = auth.get_effective_tenant_id(request, user)
    if not tenant_id:
        return None
    with get_session() as s:
        company = s.get(Company, tenant_id)
        if company is None or company.kind != Company.KIND_CONSULTORIA:
            return None
        s.expunge(company)
        return company


@router.get("/consultor")
def consultor_dashboard(request: Request, ok: str | None = None, error: str | None = None):
    user, redir = deps.page_user(request, auth.CONSULTANT, auth.SUPER_ADMIN)
    if redir:
        return redir
    consultoria = _consultoria(request, user)
    if consultoria is None:
        # Owner sem consultoria selecionada → escolhe uma no painel dele.
        return RedirectResponse(url=f"{settings.base_path}/admin", status_code=302)

    empresas = queries.empresas_do_consultor(consultoria.id)
    return deps.templates.TemplateResponse(
        "consultor_dashboard.html",
        {
            "request": request,
            "consultoria": {"id": consultoria.id, "nome": consultoria.nome, "slug": consultoria.slug},
            "pendentes": [e for e in empresas if e["pendente"]],
            "ativas": [e for e in empresas if not e["pendente"]],
            "link_cadastro": f"{settings.public_base_url}{settings.base_path}/cadastro-empresa/{consultoria.slug}",
            "ok": ok,
            "error": error,
            **deps.shell_ctx(
                user, "empresas", role=auth.CONSULTANT, trilha=deps.trilha_ctx(request, user)
            ),
        },
    )


@router.post("/consultor/entrar/{company_id}")
def consultor_entrar(company_id: str, request: Request):
    """Entra numa empresa da carteira. A permissão é revalidada em `auth.pode_impersonar`."""
    user, redir = deps.page_user(request, auth.CONSULTANT, auth.SUPER_ADMIN)
    if redir:
        return redir
    consultoria = _consultoria(request, user)
    if consultoria is None:
        return RedirectResponse(url=f"{settings.base_path}/admin", status_code=302)

    with get_session() as s:
        empresa = s.get(Company, company_id)
        if empresa is None or empresa.parent_id != consultoria.id:
            return deps.redirect("/consultor", error="Empresa não encontrada na sua carteira.")
        if empresa.status == Company.STATUS_PENDENTE:
            return deps.redirect("/consultor", error="Aprove o cadastro antes de entrar na empresa.")
        trilha = deps.ancestral_de(s, empresa)

    response = RedirectResponse(url=f"{settings.base_path}/empresa", status_code=302)
    deps.set_impersonation(response, trilha)
    return response


@router.post("/impersonate/stop")
def impersonate_stop(request: Request):
    """Sobe UM nível na trilha (empresa → consultoria → painel de origem)."""
    user = auth.get_current_user_optional(request)
    if user is None:
        return RedirectResponse(url=f"{settings.base_path}/entrar", status_code=302)
    trilha = [c.id for c in auth.trilha_impersonation(request, user)]
    restante = trilha[:-1]
    destino = deps.home_for_role(user.role)
    if restante:
        with get_session() as s:
            ultimo = s.get(Company, restante[-1])
            destino = (
                f"{settings.base_path}/consultor"
                if ultimo is not None and ultimo.kind == Company.KIND_CONSULTORIA
                else f"{settings.base_path}/empresa"
            )
    response = RedirectResponse(url=destino, status_code=302)
    if restante:
        deps.set_impersonation(response, restante)
    else:
        deps.clear_impersonation(response)
    return response


# ---------------------------------------------------------------------------
# Aprovação dos cadastros vindos do link do consultor
# ---------------------------------------------------------------------------
def _empresa_da_carteira(request: Request, user: User, company_id: str):
    consultoria = _consultoria(request, user)
    if consultoria is None:
        return None, None
    with get_session() as s:
        empresa = s.get(Company, company_id)
        if empresa is None or empresa.parent_id != consultoria.id:
            return consultoria, None
        s.expunge(empresa)
        return consultoria, empresa


@router.post("/consultor/cadastros/{company_id}/aprovar")
def consultor_aprovar(company_id: str, request: Request):
    """Libera o acesso da empresa. Não cria assinatura: quem paga é a consultoria."""
    user, redir = deps.page_user(request, auth.CONSULTANT, auth.SUPER_ADMIN)
    if redir:
        return redir
    _consultoria_ctx, empresa = _empresa_da_carteira(request, user, company_id)
    if empresa is None:
        return deps.redirect("/consultor", error="Cadastro não encontrado na sua carteira.")
    if empresa.status != Company.STATUS_PENDENTE:
        return deps.redirect("/consultor", error="Esse cadastro já foi analisado.")

    with get_session() as s:
        alvo = s.get(Company, company_id)
        # Recheca o status dentro da transação: duplo clique não pode aprovar duas vezes.
        if alvo is None or alvo.status != Company.STATUS_PENDENTE:
            return deps.redirect("/consultor", error="Esse cadastro já foi analisado.")
        alvo.status = Company.STATUS_ATIVO
        alvo.billing_mode = Company.BILLING_CONSULTOR
        alvo.approved_at = datetime.utcnow()
        alvo.approved_by = user.id
        nome = alvo.nome
        s.commit()
    return deps.redirect("/consultor", ok=f"{nome} liberado para usar o sistema.")


@router.post("/consultor/cadastros/{company_id}/recusar")
def consultor_recusar(company_id: str, request: Request):
    user, redir = deps.page_user(request, auth.CONSULTANT, auth.SUPER_ADMIN)
    if redir:
        return redir
    _consultoria_ctx, empresa = _empresa_da_carteira(request, user, company_id)
    if empresa is None:
        return deps.redirect("/consultor", error="Cadastro não encontrado na sua carteira.")

    with get_session() as s:
        alvo = s.get(Company, company_id)
        if alvo is None or alvo.status != Company.STATUS_PENDENTE:
            return deps.redirect("/consultor", error="Esse cadastro já foi analisado.")
        alvo.status = Company.STATUS_RECUSADO
        nome = alvo.nome
        s.commit()
    # Não usamos User.blocked aqui: bloquear o login faria a pessoa ver "senha
    # inválida". Com o status em `recusado` ela entra e lê o motivo na tela.
    return deps.redirect("/consultor", ok=f"Cadastro de {nome} recusado.")
