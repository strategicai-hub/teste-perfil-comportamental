import json
import logging
import re
import unicodedata
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func

from . import auth, gemini as gemini_client, mailer, notifier, sheets
from .config import settings
from .copsoq import scoring as copsoq_scoring
from .db import (
    Answer,
    ChatMessage,
    Company,
    CompanyArea,
    Lead,
    PasswordResetToken,
    User,
    get_session,
    init_db,
)
from .tests_engine import COPSOQ_TEST_ID, TESTS, get_engine, get_test, is_empresa_test

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

APP_DIR = Path(__file__).parent.parent
STATIC_DIR = APP_DIR / "static"
ASSETS_DIR = APP_DIR / "assets"
TEMPLATES_DIR = APP_DIR / "templates"
INDEX_FILE = STATIC_DIR / "index.html"
FAVICON_FILE = ASSETS_DIR / "favicon-sai.png"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["base_path"] = settings.base_path

app = FastAPI(title="Strategic AI — Testes Comportamentais")


@app.on_event("startup")
def _startup():
    init_db()


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


# =========================================================================
# HELPERS
# =========================================================================
def _slugify(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    norm = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    return norm or "empresa"


def _lead_result(lead: Lead) -> dict | None:
    """Resultado canônico (result_json) de um lead concluído; fallback nas colunas legadas."""
    if lead.concluido_em is None:
        return None
    if lead.result_json:
        try:
            return json.loads(lead.result_json)
        except (ValueError, TypeError):
            pass
    return {
        "type": "archetype",
        "perc": {
            "tubarao": lead.perc_tubarao or 0,
            "lobo": lead.perc_lobo or 0,
            "aguia": lead.perc_aguia or 0,
            "gato": lead.perc_gato or 0,
        },
    }


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
def root():
    return FileResponse(INDEX_FILE)


@app.get("/r/{token}")
def retorno_legado(token: str):
    # Link dos e-mails/WhatsApp: abre o app já apontando para o resultado (?r=token).
    return RedirectResponse(url=f"{settings.base_path}/?r={quote(token)}", status_code=302)


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


@app.get("/reset")
def reset_page():
    return FileResponse(INDEX_FILE)


# =========================================================================
# AUTH
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
# GESTOR DA EMPRESA (painel do cliente)
# =========================================================================
def _copsoq_agg_for(company_id: str, area: str | None) -> dict:
    with get_session() as s:
        # Só respondentes 'member' entram no agregado — a resposta do gestor (admin)
        # não distorce as médias nem quebra o anonimato do grupo.
        q = (
            s.query(Lead)
            .join(User, Lead.user_id == User.id)
            .filter(
                Lead.company_id == company_id,
                Lead.test_id == COPSOQ_TEST_ID,
                Lead.concluido_em.isnot(None),
                User.role == auth.MEMBER,
            )
        )
        if area:
            q = q.filter(Lead.area == area)
        results = []
        for lead in q.all():
            r = _lead_result(lead)
            if r and r.get("type") == "copsoq":
                results.append(r)
    return copsoq_scoring.aggregate(results)


def _company_areas_com_contagem(company_id: str) -> list[dict]:
    with get_session() as s:
        areas = s.query(CompanyArea).filter_by(company_id=company_id).order_by(CompanyArea.nome.asc()).all()
        rows = []
        for a in areas:
            n = (
                s.query(func.count(Lead.token))
                .join(User, Lead.user_id == User.id)
                .filter(Lead.company_id == company_id, Lead.test_id == COPSOQ_TEST_ID,
                        Lead.concluido_em.isnot(None), Lead.area == a.nome,
                        User.role == auth.MEMBER)
                .scalar()
            )
            rows.append({"id": a.id, "nome": a.nome, "respondentes": n or 0})
    return rows


def _company_members(company_id: str) -> list[dict]:
    with get_session() as s:
        members = (
            s.query(User)
            .filter(User.tenant_id == company_id, User.role == auth.MEMBER)
            .order_by(User.created_at.desc())
            .all()
        )
        counts = dict(
            s.query(Lead.user_id, func.count(Lead.token))
            .filter(Lead.concluido_em.isnot(None), Lead.company_id == company_id)
            .group_by(Lead.user_id)
            .all()
        )
        return [
            {
                "id": u.id,
                "nome": f"{u.nome} {u.sobrenome}".strip(),
                "email": u.email,
                "whatsapp": u.whatsapp,
                "blocked": u.blocked,
                "testes": counts.get(u.id, 0),
            }
            for u in members
        ]


# Guardas de página (redirecionam para a tela única de login, em vez de 401/403).
def _page_user(request: Request, *roles: str):
    """Retorna (user, None) se logado e com papel permitido, senão (None, redirect)."""
    user = auth.get_current_user_optional(request)
    if user is None or (roles and user.role not in roles):
        return None, RedirectResponse(url=f"{settings.base_path}/", status_code=302)
    return user, None


def _manager_tenant(request: Request, user: User):
    """Tenant efetivo do gestor (o próprio, ou o impersonado se super admin).

    Retorna (tenant_id, company, impersonating_nome|None) ou (None, None, None)
    quando o super admin não está impersonando (deve ir para /admin).
    """
    tenant_id = auth.get_effective_tenant_id(request, user)
    if not tenant_id:
        return None, None, None
    with get_session() as s:
        company = s.get(Company, tenant_id)
        if company is None:
            return None, None, None
        impersonating = company.nome if user.role == auth.SUPER_ADMIN else None
        return tenant_id, {"nome": company.nome, "slug": company.slug}, impersonating


@app.post("/empresa/logout")
def empresa_logout():
    response = RedirectResponse(url=f"{settings.base_path}/", status_code=302)
    response.delete_cookie(key=auth.JWT_COOKIE, path="/")
    response.delete_cookie(key=auth.IMPERSONATE_COOKIE, path="/")
    return response


@app.get("/empresa")
def empresa_dashboard(request: Request, area: str | None = None):
    user, redir = _page_user(request, auth.ADMIN, auth.SUPER_ADMIN)
    if redir:
        return redir
    tenant_id, company_data, impersonating = _manager_tenant(request, user)
    if not tenant_id:
        # super admin sem impersonar → escolher uma empresa no painel admin
        return RedirectResponse(url=f"{settings.base_path}/admin", status_code=302)

    areas = _company_areas_com_contagem(tenant_id)
    total = sum(a["respondentes"] for a in areas)
    scope = area if area else None
    agg = _copsoq_agg_for(tenant_id, scope)
    return templates.TemplateResponse(
        "empresa_dashboard.html",
        {
            "request": request,
            "company": company_data,
            "areas": areas,
            "total_respondentes": total,
            "scope": scope,
            "agg": agg,
            "colaboradores": _company_members(tenant_id),
            "impersonating": impersonating,
        },
    )


# O gestor de cada empresa gerencia as próprias áreas (não o super admin).
@app.post("/empresa/areas")
def empresa_add_area(request: Request, nome: str = Form(...)):
    user, redir = _page_user(request, auth.ADMIN, auth.SUPER_ADMIN)
    if redir:
        return redir
    tenant_id, _company, _imp = _manager_tenant(request, user)
    if not tenant_id:
        return RedirectResponse(url=f"{settings.base_path}/admin", status_code=302)
    nome = nome.strip()
    with get_session() as s:
        if nome and s.query(CompanyArea).filter_by(company_id=tenant_id, nome=nome).first() is None:
            s.add(CompanyArea(company_id=tenant_id, nome=nome))
            s.commit()
    return RedirectResponse(url=f"{settings.base_path}/empresa", status_code=302)


@app.post("/empresa/areas/{area_id}/delete")
def empresa_delete_area(area_id: int, request: Request):
    user, redir = _page_user(request, auth.ADMIN, auth.SUPER_ADMIN)
    if redir:
        return redir
    tenant_id, _company, _imp = _manager_tenant(request, user)
    if not tenant_id:
        return RedirectResponse(url=f"{settings.base_path}/admin", status_code=302)
    with get_session() as s:
        area = s.get(CompanyArea, area_id)
        if area is not None and area.company_id == tenant_id:
            s.delete(area)
            s.commit()
    return RedirectResponse(url=f"{settings.base_path}/empresa", status_code=302)


@app.post("/empresa/colaboradores/{user_id}/block")
def empresa_toggle_block(user_id: str, request: Request):
    user, redir = _page_user(request, auth.ADMIN, auth.SUPER_ADMIN)
    if redir:
        return redir
    tenant_id, _company, _imp = _manager_tenant(request, user)
    if not tenant_id:
        return RedirectResponse(url=f"{settings.base_path}/admin", status_code=302)
    with get_session() as s:
        target = s.get(User, user_id)
        # Só age sobre colaborador (member) do próprio tenant — nunca outro tenant/papel.
        if target is not None and target.tenant_id == tenant_id and target.role == auth.MEMBER:
            target.blocked = not target.blocked
            s.commit()
    return RedirectResponse(url=f"{settings.base_path}/empresa", status_code=302)


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
        if s.get(Company, tenant_id) is None:
            return RedirectResponse(url=f"{settings.base_path}/admin", status_code=302)
    response = RedirectResponse(url=f"{settings.base_path}/empresa", status_code=302)
    response.set_cookie(
        key=auth.IMPERSONATE_COOKIE,
        value=auth.make_impersonation_token(tenant_id),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=8 * 3600,
        path="/",
    )
    return response


@app.post("/admin/impersonate/stop")
def admin_impersonate_stop():
    response = RedirectResponse(url=f"{settings.base_path}/admin", status_code=302)
    response.delete_cookie(key=auth.IMPERSONATE_COOKIE, path="/")
    return response


@app.get("/admin")
def admin_dashboard(request: Request):
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
                "profissao": u.profissao,
                "origem": u.origem,
                "role": u.role,
                "empresa": tenant_nomes.get(u.tenant_id) if u.tenant_id else None,
                "created_at": u.created_at,
                "testes": counts.get(u.id, 0),
            }
            for u in users
        ]
        empresas = s.query(Company).order_by(Company.created_at.desc()).all()
        empresas_rows = [{"id": c.id, "nome": c.nome, "slug": c.slug} for c in empresas]
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {"request": request, "users": rows, "empresas": empresas_rows},
    )


@app.get("/admin/users/{user_id}")
def admin_user_detail(user_id: str, request: Request):
    _user, redir = _page_user(request, auth.SUPER_ADMIN)
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
        {"request": request, "user": user_data, "results": results},
    )


@app.get("/admin/results/{token}")
def admin_result_detail(token: str, request: Request):
    _user, redir = _page_user(request, auth.SUPER_ADMIN)
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
        {"request": request, "lead": data, "messages": messages},
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
        company = Company(
            id=uuid.uuid4().hex,
            nome=nome,
            slug=slug,
            manager_email=email_norm,
            manager_password_hash=pw_hash,
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
def admin_empresa_detail(company_id: str, request: Request):
    _user, redir = _page_user(request, auth.SUPER_ADMIN)
    if redir:
        return redir
    with get_session() as s:
        company = s.get(Company, company_id)
        if company is None:
            raise HTTPException(404, "Empresa não encontrada")
        company_data = {
            "id": company.id,
            "nome": company.nome,
            "slug": company.slug,
            "manager_email": company.manager_email,
        }
    areas = _company_areas_com_contagem(company_id)
    total = sum(a["respondentes"] for a in areas)
    link = f"{settings.public_base_url}/?empresa={company_data['slug']}"
    return templates.TemplateResponse(
        "admin_empresa.html",
        {
            "request": request,
            "company": company_data,
            "areas": areas,
            "total_respondentes": total,
            "link": link,
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
