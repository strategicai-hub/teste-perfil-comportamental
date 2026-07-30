"""Faturas do tenant e tela de bloqueio por inadimplência.

Estas páginas usam `allow_blocked=True` de propósito: é justamente aqui que o cliente
bloqueado resolve a pendência. Travar o acesso a elas deixaria o cliente sem saída.
"""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from .. import auth, billing
from ..config import settings
from ..db import Company, get_session
from ..web import deps

router = APIRouter()


def _tenant(request: Request, user):
    """Tenant efetivo de quem está vendo a fatura (respeita impersonation)."""
    tenant_id = auth.get_effective_tenant_id(request, user)
    if not tenant_id:
        return None, None
    with get_session() as s:
        company = s.get(Company, tenant_id)
        if company is None:
            return None, None
        return tenant_id, {"id": company.id, "nome": company.nome, "slug": company.slug}


@router.get("/faturas")
def faturas_page(request: Request, ok: str | None = None, error: str | None = None):
    user, redir = deps.page_user(
        request, auth.ADMIN, auth.CONSULTANT, auth.SUPER_ADMIN, allow_blocked=True
    )
    if redir:
        return redir
    tenant_id, company = _tenant(request, user)
    if not tenant_id:
        return RedirectResponse(url=deps.home_for_role(user.role), status_code=302)

    dados = billing.faturas_do_tenant(tenant_id)
    with get_session() as s:
        acesso = billing.acesso(s, s.get(Company, tenant_id), user.role)
    return deps.templates.TemplateResponse(
        "faturas.html",
        {
            "request": request,
            "company": company,
            "pagas": dados["pagas"],
            "abertas": dados["abertas"],
            "coberto_por": dados["coberto_por"],
            "isento": dados["isento"],
            "plano": dados["plano"],
            "acesso": acesso,
            "ok": ok,
            "error": error,
            **deps.shell_ctx(user, "faturas", role=user.role),
        },
    )


@router.post("/faturas/{charge_id}/link")
def faturas_link(charge_id: str, request: Request):
    """Abre a página de pagamento do ASAAS (boleto, PIX ou cartão na mesma tela)."""
    user, redir = deps.page_user(
        request, auth.ADMIN, auth.CONSULTANT, auth.SUPER_ADMIN, allow_blocked=True
    )
    if redir:
        return redir
    tenant_id, _company = _tenant(request, user)
    if not tenant_id:
        return RedirectResponse(url=deps.home_for_role(user.role), status_code=302)

    url = billing.payment_link(charge_id, tenant_id)
    if not url:
        return deps.redirect("/faturas", error="Não consegui gerar o link de pagamento agora. Tente de novo em alguns minutos.")
    return RedirectResponse(url=url, status_code=302)


@router.get("/pagamento")
def pagamento_bloqueado(request: Request):
    """Tela que substitui o painel quando o acesso está travado."""
    user, redir = deps.page_user(request, allow_blocked=True)
    if redir:
        return redir
    tenant_id = auth.get_effective_tenant_id(request, user)
    with get_session() as s:
        company = s.get(Company, tenant_id) if tenant_id else None
        acesso = billing.acesso(s, company, user.role)
        company_ctx = {"nome": company.nome} if company else None
    if not acesso.bloqueado:
        # Pagou (ou o webhook chegou) enquanto estava aqui — volta para o painel.
        return RedirectResponse(url=deps.home_for_role(user.role), status_code=302)

    dados = billing.faturas_do_tenant(tenant_id) if tenant_id else {}
    # Empresa coberta por consultoria não tem fatura própria para pagar: quem resolve
    # é o consultor. Mostrar botão de pagamento aqui só geraria confusão.
    coberto_por = dados.get("coberto_por")
    return deps.templates.TemplateResponse(
        "pagamento_bloqueado.html",
        {
            "request": request,
            "company": company_ctx,
            "acesso": acesso,
            "abertas": dados.get("abertas", []),
            "coberto_por": coberto_por,
            "pode_pagar": user.role in (auth.ADMIN, auth.CONSULTANT) and not coberto_por,
            "base_path": settings.base_path,
        },
    )
