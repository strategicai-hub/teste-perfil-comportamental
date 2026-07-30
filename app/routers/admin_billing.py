"""Painel do owner: fila de cadastros, planos, integração ASAAS e faturas por tenant.

Regra de fila importante: o owner aprova **consultorias** e as **empresas do link
geral** — ou seja, tenants com `parent_id IS NULL`. Empresa que veio do link de um
consultor é aprovada por ele, em `routers/consultor.py`.
"""

import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Form, Request

from .. import asaas, auth, billing, plans, settings_store
from ..config import settings
from ..db import Company, Plan, User, get_session
from ..web import deps

router = APIRouter()


# ---------------------------------------------------------------------------
# Fila de cadastros
# ---------------------------------------------------------------------------
def _pendentes_do_owner() -> list[dict]:
    with get_session() as s:
        rows = (
            s.query(Company)
            .filter(Company.status == Company.STATUS_PENDENTE, Company.parent_id.is_(None))
            .order_by(Company.created_at.asc())
            .all()
        )
        return [
            {
                "id": c.id,
                "nome": c.nome,
                "slug": c.slug,
                "kind": c.kind,
                "consultoria": c.kind == Company.KIND_CONSULTORIA,
                "cpf_cnpj": c.cpf_cnpj,
                "manager_email": c.manager_email,
                "plan_id": c.plan_id,
                "signup_ip": c.signup_ip,
                "criado_em": deps.fmt_data(c.created_at),
            }
            for c in rows
        ]


@router.get("/admin/cadastros")
def admin_cadastros(request: Request, ok: str | None = None, error: str | None = None):
    user, redir = deps.page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    return deps.templates.TemplateResponse(
        "admin_cadastros.html",
        {
            "request": request,
            "pendentes": _pendentes_do_owner(),
            "planos_empresa": plans.listar(tipo=Plan.TIPO_EMPRESA, apenas_ativos=True),
            "planos_consultoria": plans.listar(tipo=Plan.TIPO_CONSULTORIA, apenas_ativos=True),
            "vencimento_padrao": (
                deps.hoje_sp() + timedelta(days=billing.PRIMEIRA_FATURA_DIAS)
            ).isoformat(),
            "hoje": deps.hoje_sp().isoformat(),
            "ok": ok,
            "error": error,
            **deps.shell_ctx(user, "cadastros"),
        },
    )


@router.post("/admin/cadastros/{company_id}/aprovar")
def admin_aprovar(
    request: Request,
    company_id: str,
    bg: BackgroundTasks,
    plan_id: str = Form(""),
    primeira_fatura: str = Form(""),
    sem_cobranca: str = Form(""),
):
    """Libera o acesso e (se for para cobrar) cria a assinatura no ASAAS.

    `sem_cobranca` marca o tenant como isento: nada é criado no gateway e ele nunca
    é bloqueado. É o caminho dos primeiros clientes/cortesias, e é reversível em
    `/admin/empresas/{id}/cobranca`.
    """
    user, redir = deps.page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir

    isento = bool(sem_cobranca)
    vencimento: date | None = None
    if not isento and primeira_fatura:
        try:
            vencimento = date.fromisoformat(primeira_fatura)
        except ValueError:
            return deps.redirect("/admin/cadastros", error="Data da primeira fatura inválida.")

    with get_session() as s:
        company = s.get(Company, company_id)
        if company is None or company.parent_id is not None:
            return deps.redirect("/admin/cadastros", error="Cadastro não encontrado nesta fila.")
        # Recheca dentro da transação: duplo clique não pode gerar duas assinaturas.
        if company.status != Company.STATUS_PENDENTE:
            return deps.redirect("/admin/cadastros", error="Esse cadastro já foi analisado.")

        if not isento:
            escolhido = None
            if plan_id.isdigit():
                escolhido = s.get(Plan, int(plan_id))
            if escolhido is None or escolhido.tipo != (
                Plan.TIPO_CONSULTORIA if company.e_consultoria else Plan.TIPO_EMPRESA
            ):
                return deps.redirect("/admin/cadastros", error="Escolha um plano válido para este cadastro.")
            company.plan_id = escolhido.id
            company.billing_mode = Company.BILLING_PROPRIO
        else:
            company.billing_mode = Company.BILLING_ISENTO

        company.status = Company.STATUS_ATIVO
        company.approved_at = datetime.utcnow()
        company.approved_by = user.id
        nome = company.nome
        s.commit()

    if not isento:
        bg.add_task(billing.ensure_subscription, company_id, vencimento)
        msg = f"{nome} liberado. Assinatura sendo criada no ASAAS."
    else:
        msg = f"{nome} liberado sem cobrança."
    return deps.redirect("/admin/cadastros", ok=msg)


@router.post("/admin/cadastros/{company_id}/recusar")
def admin_recusar(company_id: str, request: Request):
    user, redir = deps.page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    with get_session() as s:
        company = s.get(Company, company_id)
        if company is None or company.parent_id is not None:
            return deps.redirect("/admin/cadastros", error="Cadastro não encontrado nesta fila.")
        if company.status != Company.STATUS_PENDENTE:
            return deps.redirect("/admin/cadastros", error="Esse cadastro já foi analisado.")
        company.status = Company.STATUS_RECUSADO
        nome = company.nome
        s.commit()
    return deps.redirect("/admin/cadastros", ok=f"Cadastro de {nome} recusado.")


# ---------------------------------------------------------------------------
# Cobrança de um tenant já aprovado
# ---------------------------------------------------------------------------
@router.post("/admin/empresas/{company_id}/cobranca")
def admin_trocar_cobranca(
    request: Request,
    company_id: str,
    bg: BackgroundTasks,
    modo: str = Form(...),
    plan_id: str = Form(""),
    primeira_fatura: str = Form(""),
):
    """Única porta para começar a cobrar quem está isento (e para isentar de volta)."""
    user, redir = deps.page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    destino = f"/admin/empresas/{company_id}"
    if modo not in (Company.BILLING_PROPRIO, Company.BILLING_ISENTO, Company.BILLING_CONSULTOR):
        return deps.redirect(destino, error="Forma de cobrança inválida.")

    vencimento: date | None = None
    if modo == Company.BILLING_PROPRIO and primeira_fatura:
        try:
            vencimento = date.fromisoformat(primeira_fatura)
        except ValueError:
            return deps.redirect(destino, error="Data da primeira fatura inválida.")

    cancelar = False
    with get_session() as s:
        company = s.get(Company, company_id)
        if company is None:
            return deps.redirect("/admin", error="Empresa não encontrada.")
        if modo == Company.BILLING_CONSULTOR and not company.parent_id:
            return deps.redirect(destino, error="Só empresa de consultoria pode ser cobrada pelo consultor.")
        if modo == Company.BILLING_PROPRIO:
            if plan_id.isdigit():
                escolhido = s.get(Plan, int(plan_id))
                if escolhido is not None:
                    company.plan_id = escolhido.id
            if not company.plan_id:
                return deps.redirect(destino, error="Escolha um plano antes de começar a cobrar.")
            if not company.cpf_cnpj:
                return deps.redirect(destino, error="Cadastre o CPF/CNPJ antes de gerar a assinatura.")
        else:
            # Deixar de cobrar exige derrubar a assinatura: sem isso o ASAAS segue
            # emitindo fatura de quem virou isento.
            cancelar = bool(company.asaas_subscription_id)
        company.billing_mode = modo
        company.asaas_erro = None
        s.commit()

    if cancelar:
        bg.add_task(billing.cancelar_assinatura, company_id)
    if modo == Company.BILLING_PROPRIO:
        bg.add_task(billing.ensure_subscription, company_id, vencimento)
        return deps.redirect(destino, ok="Cobrança ativada. Assinatura sendo criada no ASAAS.")
    return deps.redirect(destino, ok="Forma de cobrança atualizada.")


@router.get("/admin/empresas/{company_id}/faturas")
def admin_faturas_do_tenant(company_id: str, request: Request):
    user, redir = deps.page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    with get_session() as s:
        company = s.get(Company, company_id)
        if company is None:
            return deps.redirect("/admin", error="Empresa não encontrada.")
        company_ctx = {"id": company.id, "nome": company.nome, "slug": company.slug}
    dados = billing.faturas_do_tenant(company_id)
    return deps.templates.TemplateResponse(
        "faturas.html",
        {
            "request": request,
            "company": company_ctx,
            "pagas": dados["pagas"],
            "abertas": dados["abertas"],
            "coberto_por": dados["coberto_por"],
            "isento": dados["isento"],
            "plano": dados["plano"],
            "acesso": None,
            "somente_leitura": True,
            **deps.shell_ctx(user, "empresas"),
        },
    )


# ---------------------------------------------------------------------------
# Consultorias criadas à mão pelo owner
# ---------------------------------------------------------------------------
@router.post("/admin/consultores")
def admin_criar_consultoria(
    request: Request,
    nome: str = Form(...),
    manager_email: str = Form(...),
    manager_password: str = Form(...),
):
    user, redir = deps.page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    nome = nome.strip()
    email = manager_email.lower().strip()
    if len(manager_password) < 8:
        return deps.redirect("/admin", error="A senha precisa ter ao menos 8 caracteres.")
    if settings.super_admin_email and email == settings.super_admin_email.lower().strip():
        return deps.redirect("/admin", error="Esse e-mail é reservado.")

    with get_session() as s:
        if s.query(User).filter(User.email == email).first() is not None:
            return deps.redirect("/admin", error="Esse e-mail já está em uso.")
        consultoria = Company(
            id=uuid.uuid4().hex,
            nome=nome,
            slug=deps.slug_unico(s, nome),
            manager_email="",  # o gestor já nasce como User; ver db.migrate_company_managers
            kind=Company.KIND_CONSULTORIA,
            status=Company.STATUS_ATIVO,
            billing_mode=Company.BILLING_ISENTO,
            approved_at=datetime.utcnow(),
            approved_by=user.id,
        )
        s.add(consultoria)
        s.flush()
        s.add(User(
            id=auth.new_user_id(),
            email=email,
            password_hash=auth.hash_password(manager_password),
            nome=nome,
            sobrenome="",
            whatsapp="",
            role=auth.CONSULTANT,
            tenant_id=consultoria.id,
        ))
        s.commit()
    return deps.redirect("/admin", ok=f"Consultoria {nome} criada. Defina a cobrança quando quiser.")


# ---------------------------------------------------------------------------
# Planos
# ---------------------------------------------------------------------------
@router.get("/admin/planos")
def admin_planos(request: Request, ok: str | None = None, error: str | None = None):
    user, redir = deps.page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    return deps.templates.TemplateResponse(
        "admin_planos.html",
        {
            "request": request,
            "planos": plans.listar(),
            "ciclos": plans.CICLOS,
            "ok": ok,
            "error": error,
            **deps.shell_ctx(user, "planos"),
        },
    )


@router.post("/admin/planos")
def admin_criar_plano(
    request: Request,
    nome: str = Form(...),
    valor: str = Form(...),
    ciclo: str = Form("MONTHLY"),
    tipo: str = Form("empresa"),
    ordem: int = Form(0),
):
    user, redir = deps.page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    centavos = plans.parse_valor(valor)
    if not nome.strip() or centavos <= 0:
        return deps.redirect("/admin/planos", error="Informe nome e valor do plano.")
    plans.criar(nome, centavos, ciclo, tipo, ordem)
    return deps.redirect("/admin/planos", ok="Plano criado.")


@router.post("/admin/planos/{plan_id}/editar")
def admin_editar_plano(
    plan_id: int,
    request: Request,
    nome: str = Form(...),
    valor: str = Form(...),
    ciclo: str = Form("MONTHLY"),
    ordem: int = Form(0),
):
    user, redir = deps.page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    centavos = plans.parse_valor(valor)
    if centavos <= 0:
        return deps.redirect("/admin/planos", error="Valor inválido.")
    plans.editar(plan_id, nome, centavos, ciclo, ordem)
    # Assinaturas já criadas no ASAAS mantêm o valor antigo — o novo vale para os
    # próximos cadastros.
    return deps.redirect("/admin/planos", ok="Plano atualizado. Assinaturas já ativas seguem no valor antigo.")


@router.post("/admin/planos/{plan_id}/desativar")
def admin_desativar_plano(plan_id: int, request: Request):
    user, redir = deps.page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    plans.alternar_ativo(plan_id)
    return deps.redirect("/admin/planos", ok="Plano atualizado.")


# ---------------------------------------------------------------------------
# Integração ASAAS
# ---------------------------------------------------------------------------
@router.get("/admin/integracoes")
def admin_integracoes(request: Request, ok: str | None = None, error: str | None = None):
    user, redir = deps.page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    cfg = settings_store.get_many([
        settings_store.ASAAS_TOKEN, settings_store.ASAAS_ENV, settings_store.ASAAS_WEBHOOK_TOKEN
    ])
    token_salvo = cfg.get(settings_store.ASAAS_TOKEN, "")
    return deps.templates.TemplateResponse(
        "admin_integracoes.html",
        {
            "request": request,
            "token_mascarado": settings_store.mask(token_salvo),
            "tem_token_no_env": bool((settings.asaas_api_key or "").strip()),
            "env_atual": cfg.get(settings_store.ASAAS_ENV) or settings.asaas_env,
            "webhook_token": cfg.get(settings_store.ASAAS_WEBHOOK_TOKEN, ""),
            "webhook_url": f"{settings.public_base_url}{settings.base_path}/webhooks/asaas",
            "eventos": [
                "PAYMENT_CREATED", "PAYMENT_UPDATED", "PAYMENT_CONFIRMED", "PAYMENT_RECEIVED",
                "PAYMENT_OVERDUE", "PAYMENT_REFUNDED", "PAYMENT_DELETED",
            ],
            "ok": ok,
            "error": error,
            **deps.shell_ctx(user, "integracoes"),
        },
    )


@router.post("/admin/integracoes")
def admin_salvar_integracoes(
    request: Request,
    token: str = Form(""),
    ambiente: str = Form("sandbox"),
    gerar_webhook_token: str = Form(""),
):
    user, redir = deps.page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    # Campo em branco = manter o token atual (a tela mostra só a máscara).
    if token.strip():
        settings_store.set(settings_store.ASAAS_TOKEN, token.strip())
    settings_store.set(
        settings_store.ASAAS_ENV, "production" if ambiente == "production" else "sandbox"
    )
    if gerar_webhook_token or not settings_store.get(settings_store.ASAAS_WEBHOOK_TOKEN):
        import secrets

        settings_store.set(settings_store.ASAAS_WEBHOOK_TOKEN, secrets.token_hex(32))
    return deps.redirect("/admin/integracoes", ok="Integração salva.")


@router.post("/admin/integracoes/testar")
def admin_testar_integracao(request: Request):
    user, redir = deps.page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    try:
        asaas.ping()
    except asaas.AsaasNaoConfigurado as exc:
        return deps.redirect("/admin/integracoes", error=str(exc))
    except asaas.AsaasErro as exc:
        return deps.redirect("/admin/integracoes", error=f"Falha na conexão — {exc.descricao}")
    return deps.redirect("/admin/integracoes", ok=f"Conexão OK ({asaas.ambiente()}).")
