import asyncio
import json
import logging
import uuid
from datetime import date, datetime, timedelta
from urllib.parse import quote

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func

from . import (
    auth,
    billing,
    gemini as gemini_client,
    invites,
    mailer,
    notifier,
    pdf,
    plans,
    queries,
    sheets,
)
from .config import settings
from .copsoq import report as copsoq_report, scoring as copsoq_scoring
from .db import (
    Answer,
    Campaign,
    CampaignInvite,
    ChatMessage,
    Company,
    CompanyArea,
    Lead,
    PasswordResetToken,
    Plan,
    User,
    get_session,
    init_db,
)
from .routers import admin_billing, consultor, faturas, publico
from .tests_engine import COPSOQ_TEST_ID, TESTS, get_engine, get_test, is_empresa_test
from .web import deps

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

APP_DIR = deps.APP_DIR
STATIC_DIR = deps.STATIC_DIR
ASSETS_DIR = deps.ASSETS_DIR
INDEX_FILE = STATIC_DIR / "index.html"
FAVICON_FILE = ASSETS_DIR / "favicon-sai.png"

# Helpers e templates vivem em app/web/deps.py e app/queries.py (os routers não podem
# importar de main). Os aliases abaixo mantêm os nomes que as rotas deste módulo já usam.
templates = deps.templates
MIN_RESPONDENTES = deps.MIN_RESPONDENTES
SP_TZ = deps.SP_TZ
_slugify = deps.slugify
_home_for_role = deps.home_for_role
_shell_user = deps.shell_user
_shell_ctx = deps.shell_ctx
_safe_next = deps.safe_next
_page_user = deps.page_user
_manager_tenant = deps.manager_tenant
_fim_do_dia_utc = deps.fim_do_dia_utc
_para_data_local = deps.para_data_local
_fmt_data = deps.fmt_data
_lead_result = queries.lead_result
_gestor_ids = queries.gestor_ids
_copsoq_leads = queries.copsoq_leads
_copsoq_agg_for = queries.copsoq_agg_for
_company_areas_com_contagem = queries.company_areas_com_contagem
_campanha_atual = queries.campanha_atual
_campanha_ctx = queries.campanha_ctx
_relatorio_secoes = queries.secoes_relatorio

app = FastAPI(title="Strategic AI — Testes Comportamentais")


@app.on_event("startup")
def _startup():
    init_db()


@app.on_event("startup")
async def _startup_reconciliacao():
    """Rede de segurança para webhook do ASAAS perdido (ver billing.reconciliar)."""
    asyncio.create_task(_loop_reconciliacao())


async def _loop_reconciliacao():
    await asyncio.sleep(60)  # deixa o boot e as migrações terminarem
    while True:
        try:
            await run_in_threadpool(billing.reconciliar)
        except Exception:
            log.exception("Reconciliação ASAAS falhou")
        await asyncio.sleep(30 * 60)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

# Routers registrados ANTES do catch-all /perfil-comportamental/{rest:path} — cada um
# declara o path completo, sem prefixo, então nenhuma URL existente muda.
app.include_router(publico.router)
app.include_router(consultor.router)
app.include_router(faturas.router)
app.include_router(admin_billing.router)


# =========================================================================
# HELPERS
# =========================================================================
def _lead_to_dict(lead: Lead) -> dict:
    return {
        "token": lead.token,
        "user_id": lead.user_id,
        "test_id": lead.test_id,
        "nome": lead.nome,
        "sobrenome": lead.sobrenome,
        "whatsapp": lead.whatsapp,
        "email": lead.email,
        "profissao": lead.profissao,
        "origem": lead.origem,
        "area": lead.area,
        "company_id": lead.company_id,
    }


def _history_resumo(lead: Lead) -> dict:
    result = _lead_result(lead) or {}
    if result.get("type") == "copsoq":
        vermelhos = sum(1 for d in result.get("domains", []) if d.get("nivel") == "vermelho")
        top = result.get("top_riscos") or []
        return {"tipo": "copsoq", "vermelhos": vermelhos, "top_risco": top[0]["nome"] if top else None}
    perc = result.get("perc", {})
    return {"tipo": "archetype", "perc": perc}


# =========================================================================
# STATIC / ROOT
# =========================================================================
@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/favicon.ico")
def favicon():
    return FileResponse(FAVICON_FILE, media_type="image/png")


@app.get("/")
def root(request: Request):
    user = auth.get_current_user_optional(request)
    if user is None:
        return RedirectResponse(url=f"{settings.base_path}/entrar", status_code=302)
    return RedirectResponse(url=_home_for_role(user.role), status_code=302)


@app.get("/r/{token}")
def retorno_legado(token: str):
    # Link dos e-mails/WhatsApp: abre direto a página do resultado (requer login).
    return RedirectResponse(url=f"{settings.base_path}/resultado/{quote(token)}", status_code=302)


@app.api_route("/perfil-comportamental", methods=["GET", "POST"])
@app.api_route("/perfil-comportamental/{rest:path}", methods=["GET", "POST"])
def legacy_prefix_redirect(request: Request, rest: str = ""):
    # Links antigos (e-mails/WhatsApp já enviados) usavam o prefixo /perfil-comportamental.
    # O app agora vive na raiz do domínio — redireciona preservando path e query.
    # lstrip evita open redirect: sem ele, "/perfil-comportamental//evil.com" viraria
    # Location "//evil.com" (URL protocol-relative → navegador vai para https://evil.com).
    # (fora da f-string: Python 3.11 não aceita backslash em expressão de f-string)
    safe_rest = rest.lstrip("/\\")
    target = f"{settings.base_path}/{safe_rest}"
    if request.url.query:
        target += f"?{request.url.query}"
    # 308 preserva o método (POST de forms antigos continua POST) e é permanente.
    return RedirectResponse(url=target, status_code=308)


# =========================================================================
# AUTH (páginas server-rendered com URL próprio)
# =========================================================================
@app.get("/entrar")
def entrar_page(request: Request, next: str | None = None):
    user = auth.get_current_user_optional(request)
    if user is not None:
        return RedirectResponse(url=_home_for_role(user.role), status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "next": _safe_next(next)})


@app.post("/entrar")
def entrar_submit(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("")):
    email_norm = email.lower().strip()
    with get_session() as s:
        user = s.query(User).filter(User.email == email_norm).first()
        if user is None or user.blocked or not auth.verify_password(password, user.password_hash):
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "E-mail ou senha inválidos", "email": email, "next": _safe_next(next)},
                status_code=401,
            )
        role, uid = user.role, user.id
    dest = _safe_next(next) or _home_for_role(role)
    response = RedirectResponse(url=dest, status_code=302)
    _set_auth_cookie(response, auth.create_jwt(uid))
    return response


@app.post("/sair")
def sair():
    response = RedirectResponse(url=f"{settings.base_path}/entrar", status_code=302)
    _clear_auth_cookie(response)
    return response


@app.get("/cadastro/{slug}")
def cadastro_page(slug: str, request: Request):
    with get_session() as s:
        company = s.query(Company).filter(Company.slug == slug.lower().strip()).first()
        if company is None:
            return templates.TemplateResponse(
                "login.html", {"request": request, "error": "Link de convite inválido ou empresa não encontrada."}, status_code=404
            )
        company_ctx = {"nome": company.nome, "slug": company.slug}
    return templates.TemplateResponse("cadastro.html", {"request": request, "company": company_ctx, "form": {}})


@app.post("/cadastro/{slug}")
def cadastro_submit(
    slug: str,
    request: Request,
    nome: str = Form(...),
    sobrenome: str = Form(""),
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    email_norm = email.lower().strip()
    with get_session() as s:
        company = s.query(Company).filter(Company.slug == slug.lower().strip()).first()
        if company is None:
            return templates.TemplateResponse(
                "login.html", {"request": request, "error": "Link de convite inválido."}, status_code=404
            )
        company_ctx = {"nome": company.nome, "slug": company.slug}
        form = {"nome": nome, "sobrenome": sobrenome, "email": email}

        def err(msg):
            return templates.TemplateResponse(
                "cadastro.html", {"request": request, "company": company_ctx, "form": form, "error": msg}, status_code=400
            )

        if password != password2:
            return err("As senhas não coincidem")
        if len(password) < 8:
            return err("A senha precisa ter pelo menos 8 caracteres")
        if settings.super_admin_email and email_norm == settings.super_admin_email.lower().strip():
            return err("E-mail já cadastrado")
        if s.query(User).filter(User.email == email_norm).first() is not None:
            return err("E-mail já cadastrado. Faça login.")
        user = User(
            id=auth.new_user_id(),
            email=email_norm,
            password_hash=auth.hash_password(password),
            nome=nome.strip(),
            sobrenome=sobrenome.strip(),
            whatsapp="",
            role=auth.MEMBER,
            tenant_id=company.id,
        )
        s.add(user)
        s.commit()
        uid = user.id
    response = RedirectResponse(url=f"{settings.base_path}/testes", status_code=302)
    _set_auth_cookie(response, auth.create_jwt(uid))
    return response


@app.get("/esqueci-senha")
def esqueci_page(request: Request):
    return templates.TemplateResponse("esqueci.html", {"request": request})


@app.post("/esqueci-senha")
def esqueci_submit(request: Request, email: str = Form(...)):
    email_norm = email.lower().strip()
    with get_session() as s:
        user = s.query(User).filter(User.email == email_norm).first()
        if user is not None and not user.blocked:
            s.query(PasswordResetToken).filter(
                PasswordResetToken.user_id == user.id, PasswordResetToken.used == False  # noqa: E712
            ).update({"used": True})
            token_value = auth.generate_reset_token()
            s.add(PasswordResetToken(user_id=user.id, token=token_value, expires_at=datetime.utcnow() + timedelta(hours=1)))
            s.commit()
            link = f"{settings.public_base_url}/reset?token={quote(token_value)}"
            try:
                mailer.send_password_reset(email_norm, user.nome, link)
            except Exception:
                log.warning("Falha ao enviar e-mail de reset para %s", email_norm)
    return templates.TemplateResponse("esqueci.html", {"request": request, "sent": True})


@app.get("/reset")
def reset_page(request: Request, token: str | None = None):
    return templates.TemplateResponse("reset.html", {"request": request, "token": token})


@app.post("/reset")
def reset_submit(request: Request, token: str = Form(...), password: str = Form(...), password2: str = Form(...)):
    def err(msg):
        return templates.TemplateResponse("reset.html", {"request": request, "token": token, "error": msg}, status_code=400)

    if password != password2:
        return err("As senhas não coincidem")
    if len(password) < 8:
        return err("A senha precisa ter pelo menos 8 caracteres")
    with get_session() as s:
        record = s.query(PasswordResetToken).filter(PasswordResetToken.token == token).first()
        if record is None or record.used or record.expires_at < datetime.utcnow():
            return err("Link inválido ou expirado")
        user = s.get(User, record.user_id)
        if user is None or user.blocked:
            return err("Conta indisponível")
        user.password_hash = auth.hash_password(password)
        record.used = True
        s.commit()
    return templates.TemplateResponse("reset.html", {"request": request, "token": token, "done": True})


# =========================================================================
# AUTH API (JSON — legado, mantido para compat)
# =========================================================================
class RegisterIn(BaseModel):
    nome: str = Field(..., min_length=1, max_length=120)
    sobrenome: str = Field(..., min_length=1, max_length=120)
    whatsapp: str = Field(..., min_length=6, max_length=40)
    email: EmailStr
    profissao: str = Field("", max_length=200)
    origem: str = Field("", max_length=200)
    password: str = Field(..., min_length=8, max_length=128)
    # Auto-cadastro é sempre pelo link da empresa (?empresa=slug). 100% B2B.
    company_slug: str = Field(..., min_length=1, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(..., min_length=16, max_length=128)
    password: str = Field(..., min_length=8, max_length=128)


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=auth.JWT_COOKIE,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,  # True quando a URL pública é HTTPS (prod atrás do Traefik).
        samesite="lax",
        max_age=settings.jwt_expire_hours * 3600,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=auth.JWT_COOKIE, path="/")
    # Limpa também eventual impersonation (super admin que saiu pela SPA).
    response.delete_cookie(key=auth.IMPERSONATE_COOKIE, path="/")


def _redirect_for_role(role: str) -> str | None:
    """Para onde o front leva após o login. member fica na SPA (None)."""
    if role == auth.SUPER_ADMIN:
        return f"{settings.base_path}/admin"
    if role == auth.ADMIN:
        return f"{settings.base_path}/empresa"
    return None


def _user_company_context(user: User) -> dict | None:
    """Empresa (tenant) do usuário, com áreas — para a SPA montar o seletor de área.

    Sem isto, um colaborador logado (sem ?empresa= na URL) não teria o contexto da
    empresa e cairia num beco no COPSOQ.
    """
    if not user.tenant_id:
        return None
    with get_session() as s:
        company = s.get(Company, user.tenant_id)
        if company is None:
            return None
        areas = [
            a.nome
            for a in s.query(CompanyArea).filter_by(company_id=company.id).order_by(CompanyArea.nome.asc()).all()
        ]
        return {"nome": company.nome, "slug": company.slug, "areas": areas}


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "nome": user.nome,
        "sobrenome": user.sobrenome,
        "whatsapp": user.whatsapp,
        "profissao": user.profissao,
        "origem": user.origem,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@app.post("/api/auth/register")
def register(data: RegisterIn, response: Response):
    email = data.email.lower().strip()
    # O e-mail do super admin é reservado: se um User comum fosse criado com ele,
    # o login sempre cairia no branch de super admin e a conta ficaria inacessível.
    if settings.super_admin_email and email == settings.super_admin_email.lower().strip():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    slug = (data.company_slug or "").lower().strip()
    with get_session() as s:
        # 100% B2B: o cadastro só existe vinculado a uma empresa (link ?empresa=slug).
        company = s.query(Company).filter(Company.slug == slug).first() if slug else None
        if company is None:
            raise HTTPException(status_code=400, detail="Cadastro disponível apenas pelo link da sua empresa")
        existing = s.query(User).filter(User.email == email).first()
        if existing is not None:
            raise HTTPException(status_code=400, detail="E-mail já cadastrado. Faça login.")
        user = User(
            id=auth.new_user_id(),
            email=email,
            password_hash=auth.hash_password(data.password),
            nome=data.nome.strip(),
            sobrenome=data.sobrenome.strip(),
            whatsapp=data.whatsapp.strip(),
            profissao=data.profissao.strip(),
            origem=data.origem.strip(),
            role=auth.MEMBER,
            tenant_id=company.id,
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        user_dict = _user_to_dict(user)
        areas = [
            a.nome
            for a in s.query(CompanyArea).filter_by(company_id=company.id).order_by(CompanyArea.nome.asc()).all()
        ]
        company_ctx = {"nome": company.nome, "slug": company.slug, "areas": areas}

    token = auth.create_jwt(user_dict["id"])
    _set_auth_cookie(response, token)
    return {"user": user_dict, "role": auth.MEMBER, "redirect": None, "company": company_ctx}


@app.post("/api/auth/login")
def login(data: LoginIn, response: Response):
    email = data.email.lower().strip()
    with get_session() as s:
        user = s.query(User).filter(User.email == email).first()
        if user is None or user.blocked or not auth.verify_password(data.password, user.password_hash):
            raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
        user_dict = _user_to_dict(user)
        role = user.role

    token = auth.create_jwt(user_dict["id"])
    _set_auth_cookie(response, token)
    # O papel decide o destino: super_admin→/admin, admin→/empresa, member→SPA.
    company = _user_company_context(user) if role != auth.SUPER_ADMIN else None
    return {"user": user_dict, "role": role, "redirect": _redirect_for_role(role), "company": company}


@app.post("/api/auth/logout")
def logout(response: Response):
    _clear_auth_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(auth.get_current_user)):
    return {"user": _user_to_dict(user), "company": _user_company_context(user)}


@app.post("/api/auth/forgot-password")
def forgot_password(data: ForgotIn):
    email = data.email.lower().strip()
    with get_session() as s:
        user = s.query(User).filter(User.email == email).first()
        if user is None or user.blocked:
            return {"ok": True}
        s.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used == False,  # noqa: E712
        ).update({"used": True})
        token_value = auth.generate_reset_token()
        reset = PasswordResetToken(
            user_id=user.id,
            token=token_value,
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        s.add(reset)
        s.commit()
        nome = user.nome

    link = f"{settings.public_base_url}/reset?token={quote(token_value)}"
    try:
        mailer.send_password_reset(email, nome, link)
    except Exception:
        raise HTTPException(status_code=500, detail="Não foi possível enviar o e-mail")
    return {"ok": True}


@app.post("/api/auth/reset-password")
def reset_password(data: ResetIn):
    with get_session() as s:
        record = s.query(PasswordResetToken).filter(PasswordResetToken.token == data.token).first()
        if record is None or record.used or record.expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Link inválido ou expirado")
        user = s.get(User, record.user_id)
        if user is None or user.blocked:
            raise HTTPException(status_code=400, detail="Conta indisponível")
        user.password_hash = auth.hash_password(data.password)
        record.used = True
        s.commit()
    return {"ok": True}


# =========================================================================
# TESTS (área logada)
# =========================================================================
@app.get("/api/tests")
def list_tests(user: User = Depends(auth.get_current_user)):
    return {"tests": TESTS}


@app.get("/api/tests/{test_id}/questions")
def test_questions(test_id: int, user: User = Depends(auth.get_current_user)):
    engine = get_engine(test_id)
    if engine is None:
        raise HTTPException(404, "Teste não encontrado")
    return {"questions": engine.public_questions(), "kind": engine.kind}


@app.get("/api/questions")
def get_questions(user: User = Depends(auth.get_current_user)):
    # compat: teste de arquétipos
    return {"questions": get_engine(1).public_questions()}


@app.get("/api/company/{slug}")
def company_by_slug(slug: str):
    with get_session() as s:
        company = s.query(Company).filter(Company.slug == slug.lower().strip()).first()
        if company is None:
            raise HTTPException(404, "Empresa não encontrada")
        areas = [a.nome for a in s.query(CompanyArea).filter_by(company_id=company.id).order_by(CompanyArea.nome.asc()).all()]
        return {"nome": company.nome, "slug": company.slug, "areas": areas}


@app.get("/api/tests/{test_id}/history")
def test_history(test_id: int, user: User = Depends(auth.get_current_user)):
    if get_test(test_id) is None:
        raise HTTPException(404, "Teste não encontrado")
    with get_session() as s:
        leads = (
            s.query(Lead)
            .filter(Lead.user_id == user.id, Lead.test_id == test_id, Lead.concluido_em.isnot(None))
            .order_by(Lead.concluido_em.desc())
            .all()
        )
        items = [
            {
                "token": l.token,
                "concluido_em": l.concluido_em.isoformat() if l.concluido_em else None,
                "area": l.area,
                "resumo": _history_resumo(l),
            }
            for l in leads
        ]
    return {"test": get_test(test_id), "history": items}


class StartIn(BaseModel):
    area: str | None = None


@app.post("/api/tests/{test_id}/start")
def start_test(test_id: int, data: StartIn, bg: BackgroundTasks, user: User = Depends(auth.get_current_user)):
    test = get_test(test_id)
    if test is None:
        raise HTTPException(404, "Teste não encontrado")
    if not test["ativo"]:
        raise HTTPException(400, "Teste indisponível no momento")

    # O tenant vem SEMPRE do próprio usuário (nunca do cliente): isola por empresa
    # e impede um colaborador de carimbar o Lead em outra empresa. Super admin
    # (tenant NULL) — inclusive impersonando — não inicia teste de empresa.
    company_id = user.tenant_id
    area = None
    if is_empresa_test(test_id):
        if not company_id:
            raise HTTPException(400, "Sua conta não está vinculada a uma empresa")
        with get_session() as s:
            area_names = {a.nome for a in s.query(CompanyArea).filter_by(company_id=company_id).all()}
        if not data.area or data.area not in area_names:
            raise HTTPException(400, "Selecione uma área válida da empresa")
        area = data.area

    token = uuid.uuid4().hex
    with get_session() as s:
        lead = Lead(
            token=token,
            user_id=user.id,
            test_id=test_id,
            nome=user.nome,
            sobrenome=user.sobrenome,
            whatsapp=user.whatsapp,
            email=user.email,
            profissao=user.profissao,
            origem=user.origem,
            company_id=company_id,
            area=area,
        )
        s.add(lead)
        s.commit()
        lead_dict = _lead_to_dict(lead)
    bg.add_task(sheets.append_lead, lead_dict)
    return {"token": token}


def _require_lead_owner(s, token: str, user: User) -> Lead:
    lead = s.get(Lead, token)
    if lead is None:
        raise HTTPException(404, "Teste não encontrado")
    if lead.user_id != user.id:
        raise HTTPException(404, "Teste não encontrado")
    return lead


class AnswersPatch(BaseModel):
    answers: dict[str, str]


@app.patch("/api/lead/{token}/answers")
def save_answers(token: str, data: AnswersPatch, user: User = Depends(auth.get_current_user)):
    with get_session() as s:
        lead = _require_lead_owner(s, token, user)
        engine = get_engine(lead.test_id)
        if engine is None:
            raise HTTPException(400, "Teste inválido")
        existing = {a.question_id: a for a in s.query(Answer).filter_by(token=token).all()}
        for qid, value in data.answers.items():
            if not engine.valid_value(qid, value):
                continue
            if qid in existing:
                existing[qid].value = value
            else:
                s.add(Answer(token=token, question_id=qid, value=value))
        s.commit()
    return {"ok": True}


class SubmitIn(BaseModel):
    answers: dict[str, str] | None = None


@app.post("/api/lead/{token}/submit")
def submit(token: str, bg: BackgroundTasks, data: SubmitIn | None = None, user: User = Depends(auth.get_current_user)):
    with get_session() as s:
        lead = _require_lead_owner(s, token, user)
        engine = get_engine(lead.test_id)
        if engine is None:
            raise HTTPException(400, "Teste inválido")
        # O submit é a fonte de verdade: faz upsert das respostas enviadas antes de
        # pontuar, cobrindo PATCHes que tenham falhado ou chegado fora de ordem.
        if data and data.answers:
            existing = {a.question_id: a for a in s.query(Answer).filter_by(token=token).all()}
            for qid, value in data.answers.items():
                if not engine.valid_value(qid, value):
                    continue
                if qid in existing:
                    existing[qid].value = value
                else:
                    s.add(Answer(token=token, question_id=qid, value=value))
            s.flush()
        answers = {a.question_id: a.value for a in s.query(Answer).filter_by(token=token).all()}
        missing = engine.missing(answers)
        if missing:
            raise HTTPException(400, "Responda todas as perguntas antes de enviar")

        result = engine.score(answers)
        lead.result_json = json.dumps(result, ensure_ascii=False)
        lead.concluido_em = datetime.utcnow()
        if result.get("type") == "archetype":
            perc = result["perc"]
            lead.perc_tubarao = perc["tubarao"]
            lead.perc_lobo = perc["lobo"]
            lead.perc_aguia = perc["aguia"]
            lead.perc_gato = perc["gato"]
        s.commit()
        lead_dict = _lead_to_dict(lead)

    bg.add_task(sheets.update_result, token, result)
    bg.add_task(mailer.send_result_email, lead_dict["email"], lead_dict["nome"], result, token)
    bg.add_task(notifier.notify_new_lead, lead_dict, result, token)

    return {"result": result}


@app.get("/api/lead/{token}")
def get_lead(token: str, user: User = Depends(auth.get_current_user)):
    with get_session() as s:
        lead = _require_lead_owner(s, token, user)
        answers = {a.question_id: a.value for a in s.query(Answer).filter_by(token=token).all()}
        messages = [
            {"role": m.role, "content": m.content}
            for m in s.query(ChatMessage).filter_by(token=token).order_by(ChatMessage.id.asc()).all()
        ]
        result = _lead_result(lead)
        company_nome = None
        if lead.company_id:
            company = s.get(Company, lead.company_id)
            company_nome = company.nome if company else None
        test = get_test(lead.test_id) or {}
        return {
            "lead": {
                "nome": lead.nome,
                "sobrenome": lead.sobrenome,
                "email": lead.email,
                "whatsapp": lead.whatsapp,
                "profissao": lead.profissao,
                "origem": lead.origem,
                "test_id": lead.test_id,
                "test_kind": test.get("kind", "choice"),
                "test_nome": test.get("nome", ""),
                "area": lead.area,
                "company_nome": company_nome,
            },
            "answers": answers,
            "result": result,
            "chat_history": messages,
        }


# =========================================================================
# CHAT (analista IA)
# =========================================================================
@app.post("/api/chat/{token}/init")
def chat_init(token: str, user: User = Depends(auth.get_current_user)):
    with get_session() as s:
        lead = _require_lead_owner(s, token, user)
        if lead.concluido_em is None:
            raise HTTPException(400, "Teste ainda não concluído")
        existing = s.query(ChatMessage).filter_by(token=token).first()
        if existing is not None:
            return {"skipped": True}
        result = _lead_result(lead)
        msg = gemini_client.initial_message(result)
        s.add(ChatMessage(token=token, role="assistant", content=msg))
        s.commit()
    return {"message": msg}


class ChatIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


@app.post("/api/chat/{token}")
def chat(token: str, data: ChatIn, user: User = Depends(auth.get_current_user)):
    with get_session() as s:
        lead = _require_lead_owner(s, token, user)
        if lead.concluido_em is None:
            raise HTTPException(400, "Teste ainda não concluído")
        result = _lead_result(lead)
        history = [
            {"role": m.role, "content": m.content}
            for m in s.query(ChatMessage).filter_by(token=token).order_by(ChatMessage.id.asc()).all()
        ]
        s.add(ChatMessage(token=token, role="user", content=data.content))
        s.commit()
    history.append({"role": "user", "content": data.content})

    def event_stream():
        buffer = []
        try:
            for piece in gemini_client.stream_chat(history, result):
                buffer.append(piece)
                yield f"data: {_sse_escape(piece)}\n\n"
        except Exception as exc:
            log.error("Erro no streaming Gemini: %s", exc)
            yield "event: error\ndata: Falha ao gerar resposta\n\n"
            return
        full = "".join(buffer)
        with get_session() as s2:
            s2.add(ChatMessage(token=token, role="assistant", content=full))
            s2.commit()
        yield "event: done\ndata: end\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse_escape(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\n", "\ndata: ")


# =========================================================================
# PÁGINAS DO FLUXO DE TESTES (server-rendered, com shell)
# =========================================================================
@app.get("/testes")
def testes_page(request: Request):
    user, redir = _page_user(request)
    if redir:
        return redir
    # Os testes comportamentais estão ocultos: nenhum deles tem perguntas prontas, e
    # exibir cards "Em breve" só gera dúvida no cliente.
    nr1 = [t for t in TESTS if t.get("grupo") == "nr1"]
    aviso = user.role == auth.MEMBER and not user.tenant_id
    return templates.TemplateResponse(
        "testes.html",
        {"request": request, "nr1": nr1, "aviso_sem_empresa": aviso, **_shell_ctx(user, "testes")},
    )


@app.get("/testes/{test_id}")
def teste_detalhe_page(test_id: int, request: Request):
    user, redir = _page_user(request)
    if redir:
        return redir
    test = get_test(test_id)
    if test is None:
        raise HTTPException(404, "Teste não encontrado")
    with get_session() as s:
        leads = (
            s.query(Lead)
            .filter(Lead.user_id == user.id, Lead.test_id == test_id, Lead.concluido_em.isnot(None))
            .order_by(Lead.concluido_em.desc())
            .all()
        )
        history = [{"token": l.token, "concluido_em": l.concluido_em, "area": l.area, "resumo": _history_resumo(l)} for l in leads]
    company = _user_company_context(user)
    needs_area = bool(test.get("empresa"))
    return templates.TemplateResponse(
        "teste_detalhe.html",
        {"request": request, "test": test, "history": history, "company": company, "needs_area": needs_area, **_shell_ctx(user, "testes")},
    )


@app.post("/testes/{test_id}/iniciar")
def teste_iniciar(test_id: int, request: Request, bg: BackgroundTasks, area: str = Form("")):
    user, redir = _page_user(request)
    if redir:
        return redir
    test = get_test(test_id)
    if test is None or not test["ativo"]:
        raise HTTPException(400, "Teste indisponível")
    company_id = user.tenant_id
    area_val = None
    if is_empresa_test(test_id):
        if not company_id:
            return RedirectResponse(url=f"{settings.base_path}/testes/{test_id}", status_code=302)
        with get_session() as s:
            area_names = {a.nome for a in s.query(CompanyArea).filter_by(company_id=company_id).all()}
        if not area or area not in area_names:
            return RedirectResponse(url=f"{settings.base_path}/testes/{test_id}", status_code=302)
        area_val = area
    token = uuid.uuid4().hex
    with get_session() as s:
        lead = Lead(
            token=token, user_id=user.id, test_id=test_id, nome=user.nome, sobrenome=user.sobrenome,
            whatsapp=user.whatsapp, email=user.email, profissao=user.profissao, origem=user.origem,
            company_id=company_id, area=area_val,
        )
        s.add(lead)
        s.commit()
        lead_dict = _lead_to_dict(lead)
    bg.add_task(sheets.append_lead, lead_dict)
    return RedirectResponse(url=f"{settings.base_path}/responder/{token}", status_code=302)


@app.get("/responder/{token}")
def responder_page(token: str, request: Request):
    user, redir = _page_user(request)
    if redir:
        return redir
    with get_session() as s:
        lead = s.get(Lead, token)
        if lead is None or lead.user_id != user.id:
            raise HTTPException(404, "Teste não encontrado")
        if lead.concluido_em is not None:
            return RedirectResponse(url=f"{settings.base_path}/resultado/{token}", status_code=302)
        test = get_test(lead.test_id) or {}
        ctx = {"token": token, "test_id": lead.test_id, "test_nome": test.get("nome", ""), "area": lead.area}
    return templates.TemplateResponse("responder.html", {"request": request, **ctx, **_shell_ctx(user, "testes")})


@app.get("/resultado/{token}")
def resultado_page(token: str, request: Request):
    user = auth.get_current_user_optional(request)
    if user is None:
        nxt = quote(f"{settings.base_path}/resultado/{token}")
        return RedirectResponse(url=f"{settings.base_path}/entrar?next={nxt}", status_code=302)
    with get_session() as s:
        lead = s.get(Lead, token)
        if lead is None or lead.user_id != user.id:
            raise HTTPException(404, "Resultado não encontrado")
        if lead.concluido_em is None:
            return RedirectResponse(url=f"{settings.base_path}/responder/{token}", status_code=302)
        test_id = lead.test_id
    return templates.TemplateResponse("resultado.html", {"request": request, "token": token, "test_id": test_id, **_shell_ctx(user, "testes")})


# =========================================================================
# RESPONDENTE CONVIDADO (link único por e-mail, sem senha)
# =========================================================================
def _invite_ctx(s, invite_token: str) -> tuple[CampaignInvite | None, Campaign | None, Company | None, bool]:
    """Contexto do convite + se o acesso da empresa está bloqueado.

    Este é o segundo (e último) ponto de checagem de bloqueio do sistema: o
    colaborador não tem conta, então o gate de `deps.page_user` não o alcança. Vale
    para as 3 páginas /nr1/* e as 3 rotas /api/nr1/* (via `_invite_lead`).
    """
    convite = s.query(CampaignInvite).filter(CampaignInvite.token == invite_token).first()
    if convite is None:
        return None, None, None, False
    campaign = s.get(Campaign, convite.campaign_id)
    company = s.get(Company, campaign.company_id) if campaign else None
    bloqueado = billing.acesso(s, company, auth.MEMBER).bloqueado if company else False
    return convite, campaign, company, bloqueado


def _nr1_status_page(request: Request, estado: str, empresa: str = "", prazo: str = "", status_code: int = 200):
    """Telas terminais do fluxo por convite: link inválido, prazo encerrado, obrigado."""
    return templates.TemplateResponse(
        "nr1_status.html",
        {"request": request, "estado": estado, "empresa": empresa, "prazo": prazo},
        status_code=status_code,
    )


@app.get("/nr1/{invite_token}")
def nr1_intro(invite_token: str, request: Request):
    with get_session() as s:
        convite, campaign, company, bloqueado = _invite_ctx(s, invite_token)
        if convite is None or campaign is None or company is None:
            return _nr1_status_page(request, "invalido", status_code=404)
        empresa, prazo = company.nome, _fmt_data(campaign.fim)
        if bloqueado:
            return _nr1_status_page(request, "indisponivel", empresa, prazo)
        if convite.respondido_em is not None:
            return _nr1_status_page(request, "respondido", empresa, prazo)
        if not campaign.esta_aberta:
            return _nr1_status_page(request, "encerrado", empresa, prazo)
        ctx = {"nome": convite.nome, "area": convite.area, "empresa": empresa, "prazo": prazo}
    return templates.TemplateResponse(
        "nr1_intro.html", {"request": request, "invite_token": invite_token, **ctx}
    )


@app.post("/nr1/{invite_token}/iniciar")
def nr1_iniciar(invite_token: str, request: Request):
    with get_session() as s:
        convite, campaign, company, bloqueado = _invite_ctx(s, invite_token)
        if convite is None or campaign is None or company is None:
            return _nr1_status_page(request, "invalido", status_code=404)
        if bloqueado:
            return _nr1_status_page(request, "indisponivel", company.nome, _fmt_data(campaign.fim))
        if convite.respondido_em is not None:
            return _nr1_status_page(request, "respondido", company.nome, _fmt_data(campaign.fim))
        if not campaign.esta_aberta:
            return _nr1_status_page(request, "encerrado", company.nome, _fmt_data(campaign.fim))

        # Retoma o rascunho anterior se o colaborador fechou a aba no meio.
        lead = None
        if convite.lead_token:
            lead = s.get(Lead, convite.lead_token)
        if lead is None:
            partes = (convite.nome or "").split()
            lead = Lead(
                token=uuid.uuid4().hex,
                user_id=None,
                test_id=campaign.test_id or COPSOQ_TEST_ID,
                nome=partes[0] if partes else convite.nome,
                sobrenome=" ".join(partes[1:]) if len(partes) > 1 else "",
                whatsapp="",
                email=convite.email,
                company_id=company.id,
                area=convite.area,
                campaign_id=campaign.id,
            )
            s.add(lead)
            convite.lead_token = lead.token
            s.commit()
    return RedirectResponse(url=f"{settings.base_path}/nr1/{invite_token}/responder", status_code=302)


@app.get("/nr1/{invite_token}/responder")
def nr1_responder(invite_token: str, request: Request):
    with get_session() as s:
        convite, campaign, company, bloqueado = _invite_ctx(s, invite_token)
        if convite is None or campaign is None or company is None:
            return _nr1_status_page(request, "invalido", status_code=404)
        if bloqueado:
            return _nr1_status_page(request, "indisponivel", company.nome, _fmt_data(campaign.fim))
        if convite.respondido_em is not None:
            return _nr1_status_page(request, "respondido", company.nome, _fmt_data(campaign.fim))
        if not campaign.esta_aberta:
            return _nr1_status_page(request, "encerrado", company.nome, _fmt_data(campaign.fim))
        if not convite.lead_token:
            return RedirectResponse(url=f"{settings.base_path}/nr1/{invite_token}", status_code=302)
        test = get_test(campaign.test_id or COPSOQ_TEST_ID) or {}
        ctx = {
            "invite_token": invite_token,
            "test_id": campaign.test_id or COPSOQ_TEST_ID,
            "test_nome": test.get("nome", ""),
            "nome": convite.nome,
            "empresa": company.nome,
        }
    return templates.TemplateResponse("nr1_responder.html", {"request": request, **ctx})


def _invite_lead(s, invite_token: str) -> tuple[CampaignInvite, Campaign, Lead]:
    """Convite ativo + lead em aberto, ou 404/410 explicando o motivo."""
    convite, campaign, _company, bloqueado = _invite_ctx(s, invite_token)
    if convite is None or campaign is None:
        raise HTTPException(404, "Link inválido")
    if bloqueado:
        raise HTTPException(410, "Este teste está temporariamente indisponível. Fale com o RH da sua empresa.")
    if not campaign.esta_aberta:
        raise HTTPException(410, "O prazo para responder este teste já encerrou.")
    if convite.respondido_em is not None:
        raise HTTPException(410, "Este teste já foi respondido.")
    lead = s.get(Lead, convite.lead_token) if convite.lead_token else None
    if lead is None:
        raise HTTPException(404, "Sessão do teste não encontrada")
    return convite, campaign, lead


@app.get("/api/nr1/{invite_token}/tests/{test_id}/questions")
def nr1_questions(invite_token: str, test_id: int):
    with get_session() as s:
        _convite, _campaign, _lead = _invite_lead(s, invite_token)
    engine = get_engine(test_id)
    if engine is None:
        raise HTTPException(404, "Teste não encontrado")
    return {"questions": engine.public_questions(), "kind": engine.kind}


@app.patch("/api/nr1/{invite_token}/answers")
def nr1_save_answers(invite_token: str, data: AnswersPatch):
    with get_session() as s:
        _convite, _campaign, lead = _invite_lead(s, invite_token)
        engine = get_engine(lead.test_id)
        if engine is None:
            raise HTTPException(400, "Teste inválido")
        existentes = {a.question_id: a for a in s.query(Answer).filter(Answer.token == lead.token).all()}
        for qid, value in data.answers.items():
            if not engine.valid_value(qid, value):
                continue
            if qid in existentes:
                existentes[qid].value = value
            else:
                s.add(Answer(token=lead.token, question_id=qid, value=value))
        s.commit()
    return {"ok": True}


@app.post("/api/nr1/{invite_token}/submit")
def nr1_submit(invite_token: str, data: SubmitIn | None = None):
    with get_session() as s:
        convite, _campaign, lead = _invite_lead(s, invite_token)
        engine = get_engine(lead.test_id)
        if engine is None:
            raise HTTPException(400, "Teste inválido")

        existentes = {a.question_id: a for a in s.query(Answer).filter(Answer.token == lead.token).all()}
        for qid, value in ((data.answers if data else None) or {}).items():
            if not engine.valid_value(qid, value):
                continue
            if qid in existentes:
                existentes[qid].value = value
            else:
                s.add(Answer(token=lead.token, question_id=qid, value=value))
        s.commit()

        respostas = {a.question_id: a.value for a in s.query(Answer).filter(Answer.token == lead.token).all()}
        faltando = engine.missing(respostas)
        if faltando:
            raise HTTPException(400, f"Faltam {len(faltando)} resposta(s)")

        lead.result_json = json.dumps(engine.score(respostas), ensure_ascii=False)
        lead.concluido_em = datetime.utcnow()
        convite.respondido_em = lead.concluido_em
        s.commit()
    return {"ok": True, "redirect": f"{settings.base_path}/nr1/{invite_token}"}


# =========================================================================
# GESTOR DA EMPRESA (painel do cliente)
# =========================================================================
@app.post("/empresa/logout")
def empresa_logout():
    response = RedirectResponse(url=f"{settings.base_path}/", status_code=302)
    response.delete_cookie(key=auth.JWT_COOKIE, path="/")
    response.delete_cookie(key=auth.IMPERSONATE_COOKIE, path="/")
    return response


@app.get("/empresa")
def empresa_gestao(request: Request, ok: str | None = None, error: str | None = None):
    user, tenant_id, company_ctx, impersonating, redir = deps.gestor_page(request)
    if redir:
        return redir
    return templates.TemplateResponse(
        "empresa_gestao.html",
        {
            "request": request,
            "company": company_ctx,
            "areas": _company_areas_com_contagem(tenant_id),
            "ok": ok,
            "error": error,
            **_shell_ctx(
                user, "empresa", impersonating=impersonating, role=auth.ADMIN,
                trilha=deps.trilha_ctx(request, user),
            ),
        },
    )


# =========================================================================
# CAMPANHA NR-1 (convites por e-mail + prazo de resposta)
# =========================================================================
@app.get("/empresa/avaliacao")
def empresa_avaliacao(request: Request, ok: str | None = None, error: str | None = None):
    user, tenant_id, company_data, impersonating, redir = deps.gestor_page(request)
    if redir:
        return redir

    with get_session() as s:
        campaign = _campanha_atual(s, tenant_id)
        rows = (
            s.query(CampaignInvite)
            .filter(CampaignInvite.campaign_id == campaign.id)
            .order_by(CampaignInvite.area.asc(), CampaignInvite.nome.asc())
            .all()
            if campaign else []
        )
        campanha = _campanha_ctx(campaign, rows)
        convidados = [
            {
                "id": i.id,
                "nome": i.nome,
                "email": i.email,
                "area": i.area,
                "respondeu": i.respondido_em is not None,
                "erro": i.erro_envio,
                "recebeu": i.recebeu,
                "reengajado": i.reengajado_em is not None,
            }
            for i in rows
        ]
        areas = [a.nome for a in s.query(CompanyArea).filter_by(company_id=tenant_id).order_by(CompanyArea.nome.asc()).all()]

    return templates.TemplateResponse(
        "empresa_avaliacao.html",
        {
            "request": request,
            "company": company_data,
            "campanha": campanha,
            "convidados": convidados,
            "areas": areas,
            "min_data": (deps.hoje_sp() + timedelta(days=1)).isoformat(),
            "ok": ok,
            "error": error,
            **_shell_ctx(
                user, "avaliacao", impersonating=impersonating, role=auth.ADMIN,
                trilha=deps.trilha_ctx(request, user),
            ),
        },
    )


@app.get("/empresa/avaliacao/modelo.xlsx")
def empresa_avaliacao_modelo(request: Request):
    """Planilha modelo com o cabeçalho que o sistema reconhece."""
    _user, _tid, _c, _imp, redir = deps.gestor_page(request)
    if redir:
        return redir
    return Response(
        content=invites.modelo_xlsx(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="modelo-colaboradores.xlsx"'},
    )


@app.post("/empresa/avaliacao/preview")
async def empresa_avaliacao_preview(
    request: Request,
    planilha: UploadFile = File(...),
    data_fim: str = Form(...),
):
    """Lê a planilha e mostra a prévia. Nada é gravado nesta etapa.

    Quando o cabeçalho não permite identificar as três colunas, em vez de recusar o
    arquivo caímos na tela de mapeamento para o gestor apontar qual coluna é qual.
    """
    user, tenant_id, company_data, impersonating, redir = deps.gestor_page(request)
    if redir:
        return redir

    fim = _valida_data_fim(data_fim)
    if fim is None:
        return deps.redirect(
            "/empresa/avaliacao", error="A data de fim precisa ser uma data válida e posterior a hoje."
        )

    conteudo = await planilha.read()
    try:
        grade = invites.ler_grade(planilha.filename or "", conteudo)
    except ValueError as exc:
        return deps.redirect("/empresa/avaliacao", error=str(exc))
    except Exception:
        log.exception("Falha ao ler a planilha de convites")
        return deps.redirect(
            "/empresa/avaliacao", error="Não consegui ler esse arquivo. Envie uma planilha .xlsx ou .csv."
        )

    mapa = invites.sugerir_mapa(grade)
    if invites.campos_faltando(mapa):
        return templates.TemplateResponse(
            "empresa_avaliacao_mapear.html",
            {
                "request": request,
                "company": company_data,
                "colunas": invites.colunas_para_escolha(grade),
                "mapa": mapa,
                "total_linhas": len(grade) - 1,
                "data_fim": data_fim,
                "data_fim_br": fim.strftime("%d/%m/%Y"),
                "grade_json": json.dumps(grade, ensure_ascii=False),
                **_shell_ctx(user, "avaliacao", impersonating=impersonating, role=auth.ADMIN),
            },
        )

    linhas, erros = invites.mapear_e_validar(grade, mapa)
    return _tela_preview(
        request, user, tenant_id, company_data, impersonating, linhas, erros, data_fim, fim
    )


def _valida_data_fim(data_fim: str) -> date | None:
    """Data de fim válida (posterior a hoje em São Paulo) ou None."""
    try:
        fim = date.fromisoformat(data_fim)
    except ValueError:
        return None
    return fim if fim > deps.hoje_sp() else None


def _tela_preview(request, user, tenant_id, company_data, impersonating, linhas, erros, data_fim, fim):
    """Prévia do envio: o que será criado, o que foi descartado e as áreas novas."""
    if not linhas:
        return deps.redirect(
            "/empresa/avaliacao",
            error="Não encontrei nenhuma linha válida na planilha. Confira as colunas e tente de novo.",
        )
    with get_session() as s:
        existentes = {a.nome for a in s.query(CompanyArea).filter_by(company_id=tenant_id).all()}
    areas_novas = [a for a in sorted({l["area"] for l in linhas}) if a not in existentes]

    return templates.TemplateResponse(
        "empresa_avaliacao_preview.html",
        {
            "request": request,
            "company": company_data,
            "linhas": linhas,
            "erros": erros,
            "areas_novas": areas_novas,
            "data_fim": data_fim,
            "data_fim_br": fim.strftime("%d/%m/%Y"),
            "payload": json.dumps(linhas, ensure_ascii=False),
            **_shell_ctx(user, "avaliacao", impersonating=impersonating, role=auth.ADMIN),
        },
    )


@app.post("/empresa/avaliacao/mapear")
def empresa_avaliacao_mapear(
    request: Request,
    grade_json: str = Form(...),
    data_fim: str = Form(...),
    col_nome: int = Form(...),
    col_email: int = Form(...),
    col_area: int = Form(...),
):
    """Aplica o mapeamento escolhido pelo gestor e segue para a prévia."""
    user, tenant_id, company_data, impersonating, redir = deps.gestor_page(request)
    if redir:
        return redir

    fim = _valida_data_fim(data_fim)
    if fim is None:
        return deps.redirect("/empresa/avaliacao", error="A data de fim precisa ser posterior a hoje.")

    try:
        grade = json.loads(grade_json)
    except (ValueError, json.JSONDecodeError):
        return deps.redirect(
            "/empresa/avaliacao", error="Não consegui processar a planilha. Envie o arquivo de novo."
        )

    if len({col_nome, col_email, col_area}) < 3:
        return deps.redirect(
            "/empresa/avaliacao", error="Escolha uma coluna diferente para nome, e-mail e área."
        )
    try:
        linhas, erros = invites.mapear_e_validar(
            grade, {"nome": col_nome, "email": col_email, "area": col_area}
        )
    except ValueError as exc:
        return deps.redirect("/empresa/avaliacao", error=str(exc))

    return _tela_preview(
        request, user, tenant_id, company_data, impersonating, linhas, erros, data_fim, fim
    )


def _enviar_convites(campaign_id: str) -> None:
    """Dispara os e-mails da campanha (roda em background)."""
    with get_session() as s:
        campaign = s.get(Campaign, campaign_id)
        if campaign is None:
            return
        company = s.get(Company, campaign.company_id)
        empresa_nome = company.nome if company else "sua empresa"
        prazo = _fmt_data(campaign.fim)
        pendentes = (
            s.query(CampaignInvite)
            .filter(CampaignInvite.campaign_id == campaign_id, CampaignInvite.enviado_em.is_(None))
            .all()
        )
        for convite in pendentes:
            link = f"{settings.public_base_url}{settings.base_path}/nr1/{convite.token}"
            try:
                mailer.send_invite_email(convite.email, convite.nome, empresa_nome, prazo, link)
                convite.enviado_em = datetime.utcnow()
                convite.erro_envio = None
            except Exception as exc:
                log.error("Falha ao enviar convite para %s: %s", convite.email, exc)
                convite.erro_envio = str(exc)[:300]
            s.commit()


@app.post("/empresa/avaliacao/enviar")
def empresa_avaliacao_enviar(
    request: Request,
    bg: BackgroundTasks,
    payload: str = Form(...),
    data_fim: str = Form(...),
):
    """Confirma a prévia: cria a campanha, os convites e dispara os e-mails."""
    user, tenant_id, _company_data, _imp, redir = deps.gestor_page(request)
    if redir:
        return redir

    def falhou(msg: str):
        return deps.redirect("/empresa/avaliacao", error=msg)

    try:
        linhas = json.loads(payload)
    except (ValueError, json.JSONDecodeError):
        return falhou("Não consegui processar o envio. Refaça o upload da planilha.")
    fim = _valida_data_fim(data_fim)
    if fim is None:
        return falhou("A data de fim precisa ser posterior a hoje.")
    if not linhas:
        return falhou("Nenhum colaborador para convidar.")

    with get_session() as s:
        # Guarda contra duplo envio (duplo clique / F5 na confirmação): enquanto
        # houver campanha aberta, não se cria outra.
        atual = _campanha_atual(s, tenant_id)
        if atual is not None and atual.esta_aberta:
            return falhou("Já existe um teste em andamento. Aguarde a data de fim para iniciar outro.")

        company = s.get(Company, tenant_id)
        campaign = Campaign(
            id=uuid.uuid4().hex,
            company_id=tenant_id,
            test_id=COPSOQ_TEST_ID,
            titulo=f"Avaliação NR-1 — {deps.hoje_sp().strftime('%d/%m/%Y')}",
            inicio=datetime.utcnow(),
            fim=_fim_do_dia_utc(fim),
            created_by=user.id,
        )
        s.add(campaign)

        existentes = {a.nome for a in s.query(CompanyArea).filter_by(company_id=tenant_id).all()}
        for area_nome in sorted({l["area"] for l in linhas}):
            if area_nome not in existentes:
                s.add(CompanyArea(company_id=tenant_id, nome=area_nome))

        for linha in linhas:
            s.add(CampaignInvite(
                campaign_id=campaign.id,
                token=uuid.uuid4().hex,
                nome=linha["nome"],
                email=linha["email"],
                area=linha["area"],
            ))
        s.commit()
        campaign_id = campaign.id
        total = len(linhas)
        empresa_nome = company.nome if company else ""

    log.info("Campanha %s criada para %s com %s convites", campaign_id, empresa_nome, total)
    bg.add_task(_enviar_convites, campaign_id)
    return deps.redirect(
        "/empresa/avaliacao",
        ok=f"Convites criados. Estamos enviando o e-mail para {total} colaborador(es).",
    )


# ---- Convites avulsos (quem ficou de fora da planilha) -------------------
def _adicionar_convidados(tenant_id: str, linhas: list[dict]) -> tuple[str | None, int, int, str | None]:
    """Cria convites novos na campanha aberta.

    Devolve `(campaign_id, criados, repetidos, erro)`. Quem já está convidado é
    ignorado em silêncio (contado em `repetidos`) — reenviar link para a mesma
    pessoa criaria dois tokens para um respondente só.
    """
    with get_session() as s:
        campaign = _campanha_atual(s, tenant_id)
        if campaign is None or not campaign.esta_aberta:
            return None, 0, 0, "Não há teste em andamento. Envie a planilha para começar um."
        ja_convidados = {
            i.email
            for i in s.query(CampaignInvite).filter(CampaignInvite.campaign_id == campaign.id).all()
        }
        existentes = {a.nome for a in s.query(CompanyArea).filter_by(company_id=tenant_id).all()}
        criados = repetidos = 0
        for linha in linhas:
            if linha["email"] in ja_convidados:
                repetidos += 1
                continue
            if linha["area"] not in existentes:
                s.add(CompanyArea(company_id=tenant_id, nome=linha["area"]))
                existentes.add(linha["area"])
            s.add(CampaignInvite(
                campaign_id=campaign.id,
                token=uuid.uuid4().hex,
                nome=linha["nome"],
                email=linha["email"],
                area=linha["area"],
            ))
            ja_convidados.add(linha["email"])
            criados += 1
        s.commit()
        return campaign.id, criados, repetidos, None


@app.post("/empresa/avaliacao/adicionar")
def empresa_avaliacao_adicionar(
    request: Request,
    bg: BackgroundTasks,
    nome: str = Form(...),
    email: str = Form(...),
    area: str = Form(...),
):
    """Adiciona uma pessoa a um teste já em andamento."""
    _user, tenant_id, _c, _imp, redir = deps.gestor_page(request)
    if redir:
        return redir
    linhas, erros = invites.parse_colado(f"{nome.strip()};{email.strip()};{area.strip()}")
    if not linhas:
        return deps.redirect(
            "/empresa/avaliacao", error=erros[0] if erros else "Confira nome, e-mail e área."
        )
    campaign_id, criados, repetidos, erro = _adicionar_convidados(tenant_id, linhas)
    if erro:
        return deps.redirect("/empresa/avaliacao", error=erro)
    if not criados:
        return deps.redirect("/empresa/avaliacao", error="Essa pessoa já foi convidada neste teste.")
    bg.add_task(_enviar_convites, campaign_id)
    return deps.redirect("/empresa/avaliacao", ok=f"Convite enviado para {linhas[0]['email']}.")


@app.post("/empresa/avaliacao/adicionar-lote")
def empresa_avaliacao_adicionar_lote(request: Request, bg: BackgroundTasks, lista: str = Form(...)):
    """Adiciona várias pessoas de uma vez a partir de uma lista colada."""
    _user, tenant_id, _c, _imp, redir = deps.gestor_page(request)
    if redir:
        return redir
    linhas, erros = invites.parse_colado(lista)
    if not linhas:
        return deps.redirect(
            "/empresa/avaliacao",
            error=erros[0] if erros else "Nenhuma linha válida. Use o formato Nome; e-mail; Área.",
        )
    campaign_id, criados, repetidos, erro = _adicionar_convidados(tenant_id, linhas)
    if erro:
        return deps.redirect("/empresa/avaliacao", error=erro)
    if not criados:
        return deps.redirect("/empresa/avaliacao", error="Todas essas pessoas já estavam convidadas.")
    bg.add_task(_enviar_convites, campaign_id)
    partes = [f"Convite enviado para {criados} pessoa(s)"]
    if repetidos:
        partes.append(f"{repetidos} já estavam na lista")
    if erros:
        partes.append(f"{len(erros)} linha(s) com problema foram ignoradas")
    return deps.redirect("/empresa/avaliacao", ok=". ".join(partes) + ".")


# ---- Reengajamento -------------------------------------------------------
def _enviar_reengajamento(campaign_id: str) -> None:
    """Lembrete para quem recebeu o link e não respondeu (roda em background)."""
    with get_session() as s:
        campaign = s.get(Campaign, campaign_id)
        if campaign is None:
            return
        company = s.get(Company, campaign.company_id)
        empresa_nome = company.nome if company else "sua empresa"
        prazo = _fmt_data(campaign.fim)
        alvos = (
            s.query(CampaignInvite)
            .filter(
                CampaignInvite.campaign_id == campaign_id,
                CampaignInvite.respondido_em.is_(None),
                CampaignInvite.enviado_em.isnot(None),
                CampaignInvite.erro_envio.is_(None),
            )
            .all()
        )
        for convite in alvos:
            link = f"{settings.public_base_url}{settings.base_path}/nr1/{convite.token}"
            # Carimba ANTES de enviar: se o processo cair no meio, o pior caso é
            # alguém não receber o lembrete — nunca receber dois.
            convite.reengajado_em = datetime.utcnow()
            s.commit()
            try:
                mailer.send_reengagement_email(convite.email, convite.nome, empresa_nome, prazo, link)
            except Exception as exc:
                log.error("Falha no reengajamento de %s: %s", convite.email, exc)


@app.post("/empresa/avaliacao/reengajar")
def empresa_avaliacao_reengajar(request: Request, bg: BackgroundTasks):
    """Manda um lembrete (e-mail próprio, não o convite repetido) para quem não respondeu."""
    _user, tenant_id, _company_data, _imp, redir = deps.gestor_page(request)
    if redir:
        return redir

    with get_session() as s:
        campaign = _campanha_atual(s, tenant_id)
        if campaign is None or not campaign.esta_aberta:
            return deps.redirect("/empresa/avaliacao", error="Não há teste em andamento.")
        n = (
            s.query(CampaignInvite)
            .filter(
                CampaignInvite.campaign_id == campaign.id,
                CampaignInvite.respondido_em.is_(None),
                CampaignInvite.enviado_em.isnot(None),
                CampaignInvite.erro_envio.is_(None),
            )
            .count()
        )
        campaign_id = campaign.id

    if not n:
        return deps.redirect("/empresa/avaliacao", error="Todo mundo que recebeu o link já respondeu.")
    bg.add_task(_enviar_reengajamento, campaign_id)
    return deps.redirect(
        "/empresa/avaliacao", ok=f"Enviando lembrete para {n} pessoa(s) que ainda não responderam."
    )


@app.post("/empresa/avaliacao/reenviar")
def empresa_avaliacao_reenviar(request: Request, bg: BackgroundTasks):
    """Alias do reengajamento, mantido porque a tela antiga aponta para cá."""
    return empresa_avaliacao_reengajar(request, bg)


# =========================================================================
# RESULTADOS DO GESTOR — abas Gráfico e Relatório
# =========================================================================
def _resultados_ctx(request: Request, tenant_id: str, company_data: dict, area: str | None, aba: str) -> dict:
    with get_session() as s:
        campaign = _campanha_atual(s, tenant_id)
        rows = (
            s.query(CampaignInvite).filter(CampaignInvite.campaign_id == campaign.id).all()
            if campaign else []
        )
        campanha = _campanha_ctx(campaign, rows)

    areas = _company_areas_com_contagem(tenant_id)
    total = sum(a["respondentes"] for a in areas)
    scope = area or None
    agg = _copsoq_agg_for(tenant_id, scope)

    return {
        "request": request,
        "company": company_data,
        "areas": areas,
        "total_respondentes": total,
        "scope": scope,
        "agg": agg,
        "aba": aba,
        "campanha": campanha,
        "min_respondentes": MIN_RESPONDENTES,
    }


@app.get("/empresa/resultados")
def empresa_resultados(request: Request, area: str | None = None, aba: str = "grafico"):
    user, tenant_id, company_data, impersonating, redir = deps.gestor_page(request)
    if redir:
        return redir
    aba = aba if aba in ("grafico", "relatorio") else "grafico"
    ctx = _resultados_ctx(request, tenant_id, company_data, area, aba)
    campanha = ctx["campanha"]

    # O relatório só é liberado quando o teste encerra. Sem campanha cadastrada,
    # não há prazo a respeitar e o relatório fica disponível.
    relatorio_liberado = campanha is None or not campanha["aberta"]
    ctx["relatorio_liberado"] = relatorio_liberado
    # O chip de área vale nas duas abas: na aba Relatório, filtrar é o que torna a
    # leitura por setor viável (a lista completa é longa).
    ctx["secoes"] = (
        queries.secoes_relatorio(tenant_id, escopo=ctx["scope"])
        if (aba == "relatorio" and relatorio_liberado) else []
    )
    ctx["pdf_disponivel"] = pdf.disponivel()

    return templates.TemplateResponse(
        "empresa_resultados.html",
        {
            **ctx,
            **_shell_ctx(
                user, "resultados", impersonating=impersonating, role=auth.ADMIN,
                trilha=deps.trilha_ctx(request, user),
            ),
        },
    )


def _pdf_response(html: str, filename: str) -> StreamingResponse:
    try:
        buffer = pdf.html_para_pdf(html, base_url=str(APP_DIR))
    except pdf.PdfIndisponivel as exc:
        raise HTTPException(503, str(exc))
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/empresa/relatorio.pdf")
def empresa_relatorio_pdf(request: Request):
    _user, tenant_id, company_data, _imp, redir = deps.gestor_page(request)
    if redir:
        return redir

    with get_session() as s:
        campaign = _campanha_atual(s, tenant_id)
        campanha = _campanha_ctx(campaign, [])
    if campanha and campanha["aberta"]:
        raise HTTPException(403, "O relatório só fica disponível quando o teste é encerrado.")

    # O PDF sai sempre completo (geral + todas as áreas): é o artefato de arquivo e
    # de auditoria, diferente da tela, onde o chip recorta.
    html = templates.get_template("relatorio_pdf.html").render(
        company=company_data,
        secoes=queries.secoes_relatorio(tenant_id),
        campanha=campanha,
        gerado_em=deps.hoje_sp().strftime("%d/%m/%Y"),
        nivel_cor=copsoq_report.NIVEL_COR,
        nivel_txt=copsoq_report.NIVEL_LABEL,
        base_path=settings.base_path,
    )
    slug = _slugify(company_data["nome"]) if company_data else "empresa"
    return _pdf_response(html, f"relatorio-nr1-{slug}-{deps.hoje_sp().isoformat()}.pdf")


@app.get("/empresa/graficos.pdf")
def empresa_graficos_pdf(request: Request, area: str | None = None):
    """PDF do painel de gráficos. Disponível a qualquer momento (inclusive com o
    teste aberto) — é uma foto do andamento, não o relatório final."""
    _user, tenant_id, company_data, _imp, redir = deps.gestor_page(request)
    if redir:
        return redir

    with get_session() as s:
        campaign = _campanha_atual(s, tenant_id)
        rows = (
            s.query(CampaignInvite).filter(CampaignInvite.campaign_id == campaign.id).all()
            if campaign else []
        )
        campanha = _campanha_ctx(campaign, rows)

    areas = _company_areas_com_contagem(tenant_id)
    escopo = area or None
    if escopo:
        alvo = next((a for a in areas if a["nome"] == escopo), None)
        if alvo is None:
            raise HTTPException(404, "Área não encontrada.")
        paineis = [{"titulo": f"Área: {escopo}", "agg": _copsoq_agg_for(tenant_id, escopo)}]
    else:
        paineis = [{"titulo": "Geral da empresa", "agg": _copsoq_agg_for(tenant_id, None)}]
        paineis += [
            {"titulo": f"Área: {a['nome']}", "agg": _copsoq_agg_for(tenant_id, a["nome"])}
            for a in areas
            if a["respondentes"] >= MIN_RESPONDENTES
        ]

    paineis = [p for p in paineis if p["agg"]["respondentes"] >= MIN_RESPONDENTES]
    if not paineis:
        raise HTTPException(
            403,
            f"Ainda não há respostas suficientes para gerar o PDF (mínimo de {MIN_RESPONDENTES} respondentes).",
        )

    html = templates.get_template("graficos_pdf.html").render(
        company=company_data,
        paineis=[{**p, "blocos": copsoq_report.build_report(p["agg"])} for p in paineis],
        campanha=campanha,
        escopo=escopo,
        gerado_em=deps.hoje_sp().strftime("%d/%m/%Y"),
        nivel_cor=copsoq_report.NIVEL_COR,
        nivel_txt=copsoq_report.NIVEL_LABEL,
        base_path=settings.base_path,
    )
    slug = _slugify(company_data["nome"]) if company_data else "empresa"
    return _pdf_response(html, f"graficos-nr1-{slug}-{deps.hoje_sp().isoformat()}.pdf")


@app.post("/empresa/nome")
def empresa_rename(request: Request, nome: str = Form(...)):
    _user, tenant_id, _c, _i, redir = deps.gestor_page(request)
    if redir:
        return redir
    nome = nome.strip()
    if nome:
        with get_session() as s:
            company = s.get(Company, tenant_id)
            if company is not None:
                company.nome = nome
                s.commit()
    return RedirectResponse(url=f"{settings.base_path}/empresa", status_code=302)


@app.post("/empresa/areas/{area_id}/rename")
def empresa_rename_area(area_id: int, request: Request, nome: str = Form(...)):
    _user, tenant_id, _c, _i, redir = deps.gestor_page(request)
    if redir:
        return redir
    novo = nome.strip()
    with get_session() as s:
        area = s.get(CompanyArea, area_id)
        if area is not None and area.company_id == tenant_id and novo and novo != area.nome:
            dup = s.query(CompanyArea).filter_by(company_id=tenant_id, nome=novo).first()
            if dup is None:
                antigo = area.nome
                area.nome = novo
                # Cascata: mantém o histórico ligado ao novo nome (Lead.area é string).
                s.query(Lead).filter(Lead.company_id == tenant_id, Lead.area == antigo).update({Lead.area: novo})
                s.commit()
    return RedirectResponse(url=f"{settings.base_path}/empresa", status_code=302)


# As rotas /empresa/colaboradores/* foram removidas junto com o card "Colaboradores":
# sem tela que as chame, seriam mutação exposta sem uso. Os colaboradores seguem no
# banco, continuam entrando em /testes e aparecem em /admin/usuarios.


# O gestor de cada empresa gerencia as próprias áreas (não o super admin).
@app.post("/empresa/areas")
def empresa_add_area(request: Request, nome: str = Form(...)):
    _user, tenant_id, _company, _imp, redir = deps.gestor_page(request)
    if redir:
        return redir
    nome = nome.strip()
    with get_session() as s:
        if nome and s.query(CompanyArea).filter_by(company_id=tenant_id, nome=nome).first() is None:
            s.add(CompanyArea(company_id=tenant_id, nome=nome))
            s.commit()
    return RedirectResponse(url=f"{settings.base_path}/empresa", status_code=302)


@app.post("/empresa/areas/{area_id}/delete")
def empresa_delete_area(area_id: int, request: Request):
    _user, tenant_id, _company, _imp, redir = deps.gestor_page(request)
    if redir:
        return redir
    with get_session() as s:
        area = s.get(CompanyArea, area_id)
        if area is not None and area.company_id == tenant_id:
            s.delete(area)
            s.commit()
    return RedirectResponse(url=f"{settings.base_path}/empresa", status_code=302)


# =========================================================================
# CONFIGURAÇÕES (conta + administradores)
# =========================================================================
def _cfg_redirect(ok: str | None = None, error: str | None = None):
    q = f"?ok={quote(ok)}" if ok else (f"?error={quote(error)}" if error else "")
    return RedirectResponse(url=f"{settings.base_path}/configuracoes{q}", status_code=302)


@app.get("/configuracoes")
def configuracoes_page(request: Request, ok: str | None = None, error: str | None = None):
    user, redir = _page_user(request)
    if redir:
        return redir
    # Consultor também gerencia quem entra no painel da consultoria dele.
    is_admin = user.role in (auth.ADMIN, auth.CONSULTANT)
    admins = []
    if is_admin and user.tenant_id:
        with get_session() as s:
            rows = (
                s.query(User)
                .filter(User.tenant_id == user.tenant_id, User.role == user.role)
                .order_by(User.created_at.asc())
                .all()
            )
            admins = [{"id": a.id, "nome": f"{a.nome} {a.sobrenome}".strip() or a.email, "email": a.email} for a in rows]
    perfil = {"nome": user.nome, "sobrenome": user.sobrenome, "email": user.email}
    return templates.TemplateResponse(
        "configuracoes.html",
        {"request": request, "perfil": perfil, "is_admin": is_admin, "admins": admins, "me_id": user.id,
         "ok": ok, "error": error, **_shell_ctx(user, "configuracoes")},
    )


@app.post("/configuracoes/perfil")
def configuracoes_perfil(request: Request, nome: str = Form(...), sobrenome: str = Form(""), email: str = Form(...)):
    user, redir = _page_user(request)
    if redir:
        return redir
    email_norm = email.lower().strip()
    with get_session() as s:
        u = s.get(User, user.id)
        if u is None:
            return RedirectResponse(url=f"{settings.base_path}/entrar", status_code=302)
        reserved = settings.super_admin_email and email_norm == settings.super_admin_email.lower().strip()
        clash = s.query(User).filter(User.email == email_norm, User.id != u.id).first()
        if clash is not None or (reserved and u.role != auth.SUPER_ADMIN):
            return _cfg_redirect(error="Esse e-mail já está em uso")
        u.nome = nome.strip()
        u.sobrenome = sobrenome.strip()
        u.email = email_norm
        s.commit()
    return _cfg_redirect(ok="Dados atualizados")


@app.post("/configuracoes/senha")
def configuracoes_senha(request: Request, atual: str = Form(...), nova: str = Form(...), nova2: str = Form(...)):
    user, redir = _page_user(request)
    if redir:
        return redir
    if nova != nova2:
        return _cfg_redirect(error="As senhas não coincidem")
    if len(nova) < 8:
        return _cfg_redirect(error="A senha precisa ter ao menos 8 caracteres")
    with get_session() as s:
        u = s.get(User, user.id)
        if u is None or not auth.verify_password(atual, u.password_hash):
            return _cfg_redirect(error="Senha atual incorreta")
        u.password_hash = auth.hash_password(nova)
        s.commit()
    return _cfg_redirect(ok="Senha alterada")


@app.post("/configuracoes/admins")
def configuracoes_add_admin(request: Request, nome: str = Form(...), sobrenome: str = Form(""), email: str = Form(...), senha: str = Form(...)):
    user, redir = _page_user(request, auth.ADMIN, auth.CONSULTANT)
    if redir:
        return redir
    if not user.tenant_id:
        return _cfg_redirect(error="Sua conta não está vinculada a uma empresa")
    email_norm = email.lower().strip()
    if len(senha) < 8:
        return _cfg_redirect(error="A senha precisa ter ao menos 8 caracteres")
    if settings.super_admin_email and email_norm == settings.super_admin_email.lower().strip():
        return _cfg_redirect(error="Esse e-mail é reservado")
    with get_session() as s:
        if s.query(User).filter(User.email == email_norm).first() is not None:
            return _cfg_redirect(error="Esse e-mail já está em uso")
        s.add(User(
            id=auth.new_user_id(), email=email_norm, password_hash=auth.hash_password(senha),
            nome=nome.strip(), sobrenome=sobrenome.strip(), whatsapp="", role=user.role, tenant_id=user.tenant_id,
        ))
        s.commit()
    return _cfg_redirect(ok="Administrador adicionado")


@app.post("/configuracoes/admins/{admin_id}/delete")
def configuracoes_del_admin(admin_id: str, request: Request):
    user, redir = _page_user(request, auth.ADMIN, auth.CONSULTANT)
    if redir:
        return redir
    if admin_id == user.id:
        return _cfg_redirect(error="Você não pode remover a si mesmo")
    with get_session() as s:
        target = s.get(User, admin_id)
        if target is not None and target.tenant_id == user.tenant_id and target.role == user.role:
            count = s.query(User).filter(User.tenant_id == user.tenant_id, User.role == user.role).count()
            if count > 1:
                try:
                    s.delete(target)
                    s.commit()
                except Exception:
                    # Admin com registros vinculados (ex.: leads) → apenas revoga o acesso.
                    s.rollback()
                    again = s.get(User, admin_id)
                    if again is not None:
                        again.blocked = True
                        s.commit()
    return _cfg_redirect(ok="Administrador removido")


# =========================================================================
# SUPER ADMIN
# =========================================================================
# O login do super admin é feito na tela inicial (/) — o papel (super_admin)
# decide o destino. /admin/login e /admin/logout só mexem no tpc_session.
@app.get("/admin/login")
def admin_login_page():
    return RedirectResponse(url=f"{settings.base_path}/", status_code=302)


@app.post("/admin/logout")
def admin_logout():
    response = RedirectResponse(url=f"{settings.base_path}/", status_code=302)
    response.delete_cookie(key=auth.JWT_COOKIE, path="/")
    response.delete_cookie(key=auth.IMPERSONATE_COOKIE, path="/")
    return response


@app.post("/admin/impersonate/{tenant_id}")
def admin_impersonate(tenant_id: str, request: Request):
    user, redir = _page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    with get_session() as s:
        alvo = s.get(Company, tenant_id)
        if alvo is None:
            return deps.redirect("/admin", error="Tenant não encontrado.")
        # Trilha completa (consultoria → empresa): é o que faz o "Voltar" subir um
        # nível de cada vez em vez de pular direto para o painel do owner.
        trilha = deps.ancestral_de(s, alvo)
        destino = "/consultor" if alvo.kind == Company.KIND_CONSULTORIA else "/empresa"
    response = RedirectResponse(url=f"{settings.base_path}{destino}", status_code=302)
    deps.set_impersonation(response, trilha)
    return response


@app.post("/admin/impersonate/stop")
def admin_impersonate_stop(request: Request):
    """Alias de /impersonate/stop (o banner antigo aponta para cá)."""
    return consultor.impersonate_stop(request)


@app.get("/admin")
def admin_dashboard(request: Request, ok: str | None = None, error: str | None = None):
    user, redir = _page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    with get_session() as s:
        todos = s.query(Company).order_by(Company.created_at.desc()).all()
        nomes = {c.id: c.nome for c in todos}
        consultorias, empresas = [], []
        for c in todos:
            linha = {
                "id": c.id,
                "nome": c.nome,
                "slug": c.slug,
                "status": c.status,
                "pendente": c.status == Company.STATUS_PENDENTE,
                "billing_mode": c.billing_mode,
                "consultoria": nomes.get(c.parent_id) if c.parent_id else None,
                # Empresa de consultor é aprovada por ele — o owner não age nessa fila.
                "aprova_owner": c.parent_id is None,
                "criado_em": deps.fmt_data(c.created_at),
            }
            (consultorias if c.kind == Company.KIND_CONSULTORIA else empresas).append(linha)
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "consultorias": consultorias,
            "empresas": empresas,
            "pendentes_owner": [
                c for c in consultorias + empresas if c["pendente"] and c["aprova_owner"]
            ],
            "ok": ok,
            "error": error,
            **_shell_ctx(user, "empresas"),
        },
    )


@app.get("/admin/usuarios")
def admin_usuarios(request: Request):
    user, redir = _page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    with get_session() as s:
        users = s.query(User).order_by(User.created_at.desc()).all()
        counts = dict(
            s.query(Lead.user_id, func.count(Lead.token))
            .filter(Lead.concluido_em.isnot(None))
            .group_by(Lead.user_id)
            .all()
        )
        tenant_nomes = {c.id: c.nome for c in s.query(Company).all()}
        rows = [
            {
                "id": u.id,
                "nome": f"{u.nome} {u.sobrenome}".strip(),
                "email": u.email,
                "whatsapp": u.whatsapp,
                "role": u.role,
                "empresa": tenant_nomes.get(u.tenant_id) if u.tenant_id else None,
                "created_at": u.created_at,
                "testes": counts.get(u.id, 0),
            }
            for u in users
        ]
    return templates.TemplateResponse(
        "admin_usuarios.html",
        {"request": request, "users": rows, **_shell_ctx(user, "usuarios")},
    )


@app.get("/admin/users/{user_id}")
def admin_user_detail(user_id: str, request: Request):
    admin_user, redir = _page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    with get_session() as s:
        user = s.get(User, user_id)
        if user is None:
            raise HTTPException(404, "Usuário não encontrado")
        leads = (
            s.query(Lead)
            .filter(Lead.user_id == user_id)
            .order_by(Lead.created_at.desc())
            .all()
        )
        user_data = _user_to_dict(user)
        results = [
            {
                "token": l.token,
                "test_id": l.test_id,
                "test_nome": (get_test(l.test_id) or {}).get("nome", f"Teste {l.test_id}"),
                "created_at": l.created_at,
                "concluido_em": l.concluido_em,
                "area": l.area,
                "resumo": _history_resumo(l) if l.concluido_em else None,
            }
            for l in leads
        ]
    return templates.TemplateResponse(
        "admin_user.html",
        {"request": request, "user": user_data, "results": results, **_shell_ctx(admin_user, "usuarios")},
    )


@app.get("/admin/results/{token}")
def admin_result_detail(token: str, request: Request):
    admin_user, redir = _page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    with get_session() as s:
        lead = s.get(Lead, token)
        if lead is None:
            raise HTTPException(404, "Resultado não encontrado")
        user = s.get(User, lead.user_id) if lead.user_id else None
        messages = [
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in s.query(ChatMessage).filter_by(token=token).order_by(ChatMessage.id.asc()).all()
        ]
        result = _lead_result(lead)
        company_nome = None
        if lead.company_id:
            company = s.get(Company, lead.company_id)
            company_nome = company.nome if company else None
        test = get_test(lead.test_id) or {}
        data = {
            "token": lead.token,
            "test_nome": test.get("nome", f"Teste {lead.test_id}"),
            "test_kind": test.get("kind", "choice"),
            "created_at": lead.created_at,
            "concluido_em": lead.concluido_em,
            "result": result,
            "area": lead.area,
            "company_nome": company_nome,
            "user_id": lead.user_id,
            "user_nome": f"{user.nome} {user.sobrenome}".strip() if user else lead.nome,
            "user_email": user.email if user else lead.email,
        }
    return templates.TemplateResponse(
        "admin_result.html",
        {"request": request, "lead": data, "messages": messages, **_shell_ctx(admin_user, "usuarios")},
    )


# ---- Admin: empresas -----------------------------------------------------
@app.post("/admin/empresas")
def admin_create_empresa(
    request: Request,
    nome: str = Form(...),
    manager_email: str = Form(...),
    manager_password: str = Form(...),
):
    _user, redir = _page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    nome = nome.strip()
    email_norm = manager_email.lower().strip()
    if settings.super_admin_email and email_norm == settings.super_admin_email.lower().strip():
        raise HTTPException(400, "Esse e-mail é reservado ao super admin")
    with get_session() as s:
        existing = s.query(User).filter(User.email == email_norm).first()
        if existing is not None and existing.role == auth.SUPER_ADMIN:
            raise HTTPException(400, "Esse e-mail é de um super admin")
        if existing is not None and existing.tenant_id:
            raise HTTPException(400, "Esse e-mail já pertence a outra empresa")
        base = _slugify(nome)
        slug = base
        i = 2
        while s.query(Company).filter(Company.slug == slug).first() is not None:
            slug = f"{base}-{i}"
            i += 1
        pw_hash = auth.hash_password(manager_password) if manager_password else ""
        # Empresa criada à mão pelo owner já nasce liberada e sem cobrança: a forma de
        # cobrança é definida depois, no card Cobrança da tela da empresa.
        company = Company(
            id=uuid.uuid4().hex,
            nome=nome,
            slug=slug,
            manager_email=email_norm,
            manager_password_hash=pw_hash,
            kind=Company.KIND_EMPRESA,
            status=Company.STATUS_ATIVO,
            billing_mode=Company.BILLING_ISENTO,
            approved_at=datetime.utcnow(),
        )
        s.add(company)
        s.flush()
        # O gestor é um User role=admin do tenant (promove um existente sem tenant,
        # ou cria um novo). É por ele que o gestor loga na tela única.
        if existing is None:
            s.add(User(
                id=auth.new_user_id(),
                email=email_norm,
                password_hash=pw_hash,
                nome=nome,
                sobrenome="",
                whatsapp="",
                role=auth.ADMIN,
                tenant_id=company.id,
            ))
        else:
            existing.role = auth.ADMIN
            existing.tenant_id = company.id
            if manager_password:
                existing.password_hash = pw_hash
        s.commit()
        company_id = company.id
    return RedirectResponse(url=f"{settings.base_path}/admin/empresas/{company_id}", status_code=302)


@app.get("/admin/empresas/{company_id}")
def admin_empresa_detail(company_id: str, request: Request, ok: str | None = None, error: str | None = None):
    admin_user, redir = _page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    with get_session() as s:
        company = s.get(Company, company_id)
        if company is None:
            raise HTTPException(404, "Empresa não encontrada")
        plano = s.get(Plan, company.plan_id) if company.plan_id else None
        consultoria = s.get(Company, company.parent_id) if company.parent_id else None
        company_data = {
            "id": company.id,
            "nome": company.nome,
            "slug": company.slug,
            "manager_email": company.manager_email,
            "kind": company.kind,
            "status": company.status,
            "parent_id": company.parent_id,
            "consultoria": consultoria.nome if consultoria else None,
            "billing_mode": company.billing_mode,
            "plan_id": company.plan_id,
            "plano": {"nome": plano.nome, "valor_centavos": plano.valor_centavos} if plano else None,
            "asaas_erro": company.asaas_erro,
        }
        tipo_plano = Plan.TIPO_CONSULTORIA if company.e_consultoria else Plan.TIPO_EMPRESA
    areas = _company_areas_com_contagem(company_id)
    total = sum(a["respondentes"] for a in areas)
    return templates.TemplateResponse(
        "admin_empresa.html",
        {
            "request": request,
            "company": company_data,
            "areas": areas,
            "total_respondentes": total,
            "planos": plans.listar(tipo=tipo_plano, apenas_ativos=True),
            "hoje": deps.hoje_sp().isoformat(),
            "vencimento_padrao": (
                deps.hoje_sp() + timedelta(days=billing.PRIMEIRA_FATURA_DIAS)
            ).isoformat(),
            "ok": ok,
            "error": error,
            **_shell_ctx(admin_user, "empresas"),
        },
    )


@app.post("/admin/empresas/{company_id}/senha")
def admin_reset_manager_password(company_id: str, request: Request, manager_email: str = Form(...), manager_password: str = Form(...)):
    _user, redir = _page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    email_norm = manager_email.lower().strip()
    if settings.super_admin_email and email_norm == settings.super_admin_email.lower().strip():
        raise HTTPException(400, "Esse e-mail é reservado ao super admin")
    with get_session() as s:
        company = s.get(Company, company_id)
        if company is None:
            raise HTTPException(404, "Empresa não encontrada")
        # E-mail já usado por OUTRA conta (unique global) → recusa sem estourar 500.
        clash = s.query(User).filter(User.email == email_norm).first()
        admin_user = (
            s.query(User)
            .filter(User.tenant_id == company_id, User.role == auth.ADMIN)
            .first()
        )
        if clash is not None and (admin_user is None or clash.id != admin_user.id):
            raise HTTPException(400, "Esse e-mail já está em uso por outra conta")
        pw_hash = auth.hash_password(manager_password) if manager_password else None
        company.manager_email = email_norm
        if pw_hash:
            company.manager_password_hash = pw_hash
        # Reflete no User admin do tenant (é ele quem autentica de fato).
        if admin_user is not None:
            admin_user.email = email_norm
            if pw_hash:
                admin_user.password_hash = pw_hash
        else:
            existing = clash
            if existing is None:
                s.add(User(
                    id=auth.new_user_id(),
                    email=email_norm,
                    password_hash=pw_hash or "",
                    nome=company.nome,
                    sobrenome="",
                    whatsapp="",
                    role=auth.ADMIN,
                    tenant_id=company_id,
                ))
            elif not existing.tenant_id:
                existing.role = auth.ADMIN
                existing.tenant_id = company_id
                if pw_hash:
                    existing.password_hash = pw_hash
        s.commit()
    return RedirectResponse(url=f"{settings.base_path}/admin/empresas/{company_id}", status_code=302)
