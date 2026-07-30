"""Rotas públicas: cadastro self-service (2 links) e webhook do ASAAS.

O link é **aberto** — não há pré-cadastro. A defesa é em camadas (`app/antibot.py`) e
o acesso só é liberado depois de aprovação humana: a conta nasce com
`Company.status='pending'` e o gate em `deps.page_user` manda o usuário para a tela
"cadastro em análise" até alguém aprovar.

Quem aprova depende de onde veio o cadastro:
- `/cadastro-empresa` e `/cadastro-consultor` → fila do owner;
- `/cadastro-empresa/{slug_do_consultor}` → fila daquele consultor.
"""

import hmac
import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Form, Request, Response
from fastapi.responses import RedirectResponse

from .. import antibot, auth, billing, plans, settings_store
from ..config import settings
from ..db import Company, Plan, User, get_session
from ..web import deps

log = logging.getLogger(__name__)
router = APIRouter()

LIMITE_POR_IP = 5
JANELA_S = 3600


# =========================================================================
# CADASTRO PÚBLICO
# =========================================================================
def _consultoria_por_slug(slug: str) -> dict | None:
    with get_session() as s:
        c = (
            s.query(Company)
            .filter(
                Company.slug == (slug or "").lower().strip(),
                Company.kind == Company.KIND_CONSULTORIA,
                Company.status == Company.STATUS_ATIVO,
            )
            .first()
        )
        return {"id": c.id, "nome": c.nome, "slug": c.slug} if c else None


def _form_cadastro(
    request: Request,
    kind: str,
    consultoria: dict | None,
    form: dict | None = None,
    error: str | None = None,
    status_code: int = 200,
):
    pergunta, desafio = antibot.novo_desafio()
    template = (
        "cadastro_consultor.html" if kind == Company.KIND_CONSULTORIA else "cadastro_empresa.html"
    )
    # Empresa de consultor não escolhe plano: quem paga é a consultoria.
    mostrar_planos = consultoria is None
    return deps.templates.TemplateResponse(
        template,
        {
            "request": request,
            "consultoria": consultoria,
            "planos": plans.para_cadastro(kind) if mostrar_planos else [],
            "mostrar_planos": mostrar_planos,
            "form": form or {},
            "error": error,
            "desafio_pergunta": pergunta,
            "desafio_token": desafio,
            "action": request.url.path,
        },
        status_code=status_code,
    )


@router.get("/cadastro-empresa")
def cadastro_empresa_page(request: Request):
    return _form_cadastro(request, Company.KIND_EMPRESA, None)


@router.get("/cadastro-empresa/{consultor_slug}")
def cadastro_empresa_consultor_page(consultor_slug: str, request: Request):
    consultoria = _consultoria_por_slug(consultor_slug)
    if consultoria is None:
        return deps.templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Link de cadastro inválido ou desativado."},
            status_code=404,
        )
    return _form_cadastro(request, Company.KIND_EMPRESA, consultoria)


@router.get("/cadastro-consultor")
def cadastro_consultor_page(request: Request):
    return _form_cadastro(request, Company.KIND_CONSULTORIA, None)


def _processar_cadastro(
    request: Request,
    kind: str,
    consultoria: dict | None,
    dados: dict,
) -> Response:
    """Valida e cria o tenant pendente. Devolve a página de erro ou o redirect final."""
    form = {k: v for k, v in dados.items() if k not in ("password", "password2", "desafio")}

    def erro(msg: str):
        return _form_cadastro(request, kind, consultoria, form, msg, status_code=400)

    # 1. Rate limit por IP — antes de qualquer trabalho de banco.
    ip = antibot.client_ip(request)
    if not antibot.rate_limit(f"signup:{ip}", LIMITE_POR_IP, JANELA_S):
        return erro("Muitas tentativas de cadastro deste computador. Tente novamente em uma hora.")

    # 2. Honeypot: campo invisível. Se veio preenchido é bot — responde como se tivesse
    # dado certo (não entrega a detecção) e não grava nada.
    if (dados.get("website") or "").strip():
        log.info("Cadastro descartado por honeypot (ip=%s)", ip)
        return RedirectResponse(url=f"{settings.base_path}/cadastro/analise?novo=1", status_code=302)

    # 3. Desafio assinado (inclui tempo mínimo de preenchimento).
    if not antibot.valida_desafio(dados.get("desafio_token", ""), dados.get("desafio", "")):
        return erro("A resposta da pergunta de verificação está errada. Tente de novo.")

    nome_responsavel = (dados.get("nome") or "").strip()
    email = (dados.get("email") or "").lower().strip()
    senha = dados.get("password") or ""
    senha2 = dados.get("password2") or ""
    nome_tenant = (dados.get("nome_empresa") or "").strip()
    documento = (dados.get("cpf_cnpj") or "").strip()

    if not nome_responsavel or not nome_tenant:
        return erro("Preencha seu nome e o nome da empresa.")
    if not _email_ok(email):
        return erro("E-mail inválido.")
    if senha != senha2:
        return erro("As senhas não coincidem.")
    if len(senha) < 8:
        return erro("A senha precisa ter pelo menos 8 caracteres.")
    if not antibot.documento_valido(documento):
        return erro("CPF/CNPJ inválido. Confira os números.")
    if settings.super_admin_email and email == settings.super_admin_email.lower().strip():
        return erro("Esse e-mail já está cadastrado.")

    plan_id: int | None = None
    if consultoria is None:
        bruto = dados.get("plan_id") or ""
        plan_id = int(bruto) if bruto.isdigit() else None
        if not plans.existe_para(plan_id, kind):
            return erro("Escolha um plano para continuar.")

    partes = nome_responsavel.split()
    uid = auth.new_user_id()
    with get_session() as s:
        if s.query(User).filter(User.email == email).first() is not None:
            # Mensagem genérica: não confirma para um bot quais e-mails existem.
            return erro("Esse e-mail já está cadastrado. Faça login ou use outro e-mail.")

        company = Company(
            id=uuid.uuid4().hex,
            nome=nome_tenant,
            slug=deps.slug_unico(s, nome_tenant),
            manager_email="",  # gestor já nasce como User (ver db.migrate_company_managers)
            kind=kind,
            parent_id=consultoria["id"] if consultoria else None,
            status=Company.STATUS_PENDENTE,
            cpf_cnpj=antibot.digitos(documento),
            plan_id=plan_id,
            billing_mode=(
                Company.BILLING_CONSULTOR if consultoria else Company.BILLING_PROPRIO
            ),
            signup_ip=ip,
        )
        s.add(company)
        s.flush()
        s.add(User(
            id=uid,
            email=email,
            password_hash=auth.hash_password(senha),
            nome=partes[0],
            sobrenome=" ".join(partes[1:]),
            whatsapp=(dados.get("whatsapp") or "").strip()[:40],
            role=auth.CONSULTANT if kind == Company.KIND_CONSULTORIA else auth.ADMIN,
            tenant_id=company.id,
        ))
        try:
            s.commit()
        except Exception:
            s.rollback()
            log.exception("Falha ao gravar cadastro público")
            return erro("Não consegui concluir o cadastro agora. Tente novamente em alguns minutos.")

    log.info("Novo cadastro pendente: %s (%s, ip=%s)", nome_tenant, kind, ip)
    # Já entra logado: assim ele vê o andamento sem precisar guardar senha antes da
    # aprovação. O gate de acesso segura tudo o mais até alguém aprovar.
    response = RedirectResponse(url=f"{settings.base_path}/cadastro/analise?novo=1", status_code=302)
    response.set_cookie(
        key=auth.JWT_COOKIE,
        value=auth.create_jwt(uid),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_expire_hours * 3600,
        path="/",
    )
    return response


def _email_ok(email: str) -> bool:
    from ..invites import _EMAIL_RE

    return bool(email and _EMAIL_RE.match(email))


def _dados(
    nome: str,
    email: str,
    whatsapp: str,
    password: str,
    password2: str,
    nome_empresa: str,
    cpf_cnpj: str,
    plan_id: str,
    desafio: str,
    desafio_token: str,
    website: str,
) -> dict:
    return {
        "nome": nome,
        "email": email,
        "whatsapp": whatsapp,
        "password": password,
        "password2": password2,
        "nome_empresa": nome_empresa,
        "cpf_cnpj": cpf_cnpj,
        "plan_id": plan_id,
        "desafio": desafio,
        "desafio_token": desafio_token,
        "website": website,
    }


@router.post("/cadastro-empresa")
def cadastro_empresa_submit(
    request: Request,
    nome: str = Form(""),
    email: str = Form(""),
    whatsapp: str = Form(""),
    password: str = Form(""),
    password2: str = Form(""),
    nome_empresa: str = Form(""),
    cpf_cnpj: str = Form(""),
    plan_id: str = Form(""),
    desafio: str = Form(""),
    desafio_token: str = Form(""),
    website: str = Form(""),
):
    dados = _dados(
        nome, email, whatsapp, password, password2, nome_empresa, cpf_cnpj,
        plan_id, desafio, desafio_token, website,
    )
    return _processar_cadastro(request, Company.KIND_EMPRESA, None, dados)


@router.post("/cadastro-empresa/{consultor_slug}")
def cadastro_empresa_consultor_submit(
    consultor_slug: str,
    request: Request,
    nome: str = Form(""),
    email: str = Form(""),
    whatsapp: str = Form(""),
    password: str = Form(""),
    password2: str = Form(""),
    nome_empresa: str = Form(""),
    cpf_cnpj: str = Form(""),
    desafio: str = Form(""),
    desafio_token: str = Form(""),
    website: str = Form(""),
):
    consultoria = _consultoria_por_slug(consultor_slug)
    if consultoria is None:
        return deps.templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Link de cadastro inválido ou desativado."},
            status_code=404,
        )
    dados = _dados(
        nome, email, whatsapp, password, password2, nome_empresa, cpf_cnpj,
        "", desafio, desafio_token, website,
    )
    return _processar_cadastro(request, Company.KIND_EMPRESA, consultoria, dados)


@router.post("/cadastro-consultor")
def cadastro_consultor_submit(
    request: Request,
    nome: str = Form(""),
    email: str = Form(""),
    whatsapp: str = Form(""),
    password: str = Form(""),
    password2: str = Form(""),
    nome_empresa: str = Form(""),
    cpf_cnpj: str = Form(""),
    plan_id: str = Form(""),
    desafio: str = Form(""),
    desafio_token: str = Form(""),
    website: str = Form(""),
):
    dados = _dados(
        nome, email, whatsapp, password, password2, nome_empresa, cpf_cnpj,
        plan_id, desafio, desafio_token, website,
    )
    return _processar_cadastro(request, Company.KIND_CONSULTORIA, None, dados)


@router.get("/cadastro/analise")
def cadastro_analise(request: Request, novo: str | None = None):
    """Tela de espera. `allow_blocked=True` porque é exatamente o estado bloqueado."""
    user, redir = deps.page_user(request, allow_blocked=True)
    if redir:
        return redir
    with get_session() as s:
        company = s.get(Company, user.tenant_id) if user.tenant_id else None
        if company is None:
            return RedirectResponse(url=deps.home_for_role(user.role), status_code=302)
        status = company.status
        nome = company.nome
        consultoria_nome = None
        if company.parent_id:
            pai = s.get(Company, company.parent_id)
            consultoria_nome = pai.nome if pai else None
    if status == Company.STATUS_ATIVO:
        return RedirectResponse(url=deps.home_for_role(user.role), status_code=302)
    return deps.templates.TemplateResponse(
        "cadastro_analise.html",
        {
            "request": request,
            "nome": nome,
            "status": status,
            "recusado": status == Company.STATUS_RECUSADO,
            "consultoria": consultoria_nome,
            "acabou_de_enviar": bool(novo),
            "email": user.email,
        },
    )


# =========================================================================
# WEBHOOK ASAAS
# =========================================================================
@router.post("/webhooks/asaas")
async def webhook_asaas(request: Request, bg: BackgroundTasks):
    """Recebe eventos de cobrança.

    Responde **200 sempre**, inclusive em erro: status de erro faz o ASAAS entrar em
    loop de retry, e o que garante consistência aqui é a reconciliação periódica
    (`billing.reconciliar`), não o retry dele.
    """
    esperado = settings_store.get(settings_store.ASAAS_WEBHOOK_TOKEN) or (
        settings.asaas_webhook_token or ""
    ).strip()
    if not esperado:
        log.warning("[asaas] webhook recebido sem token configurado — ignorando")
        return Response("webhook token not configured", status_code=200)

    recebido = (
        request.headers.get("asaas-access-token")
        or request.headers.get("asaas_access_token")
        or ""
    )
    if not hmac.compare_digest(recebido, esperado):
        log.warning("[asaas] webhook com token inválido")
        return Response("forbidden", status_code=200)

    try:
        corpo = await request.body()
        evento = json.loads(corpo or b"{}")
        pagamento = evento.get("payment") or {}
        payment_id = pagamento.get("id")
        tipo = str(evento.get("event") or "UNKNOWN")
        if not payment_id:
            return Response("ok", status_code=200)

        if not billing.registrar_evento(payment_id, tipo, corpo.decode("utf-8", "replace")):
            # Reentrega do mesmo evento: a unique (provider, id, tipo) barrou.
            return Response("ok", status_code=200)

        billing.upsert_charge(pagamento)
        billing.marcar_evento_processado(payment_id, tipo)
    except Exception:
        log.exception("[asaas] falha ao processar webhook")
    return Response("ok", status_code=200)
