import logging
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
from .db import Answer, ChatMessage, Lead, PasswordResetToken, User, get_session, init_db
from .questions import QUESTION_IDS, TESTS, VALID_ARCHETYPES, get_test, public_questions
from .scoring import calculate

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

APP_DIR = Path(__file__).parent.parent
STATIC_DIR = APP_DIR / "static"
ASSETS_DIR = APP_DIR / "assets"
TEMPLATES_DIR = APP_DIR / "templates"
INDEX_FILE = STATIC_DIR / "index.html"
FAVICON_FILE = ASSETS_DIR / "favicon-sai.png"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Strategic AI — Testes Comportamentais")


@app.on_event("startup")
def _startup():
    init_db()


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


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
    return RedirectResponse(url="/", status_code=302)


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
        secure=False,  # TLS is terminated at Traefik; prod cookies travel over HTTPS externally.
        samesite="lax",
        max_age=settings.jwt_expire_hours * 3600,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=auth.JWT_COOKIE, path="/")


def _user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "nome": user.nome,
        "sobrenome": user.sobrenome,
        "whatsapp": user.whatsapp,
        "profissao": user.profissao,
        "origem": user.origem,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@app.post("/api/auth/register")
def register(data: RegisterIn, response: Response):
    email = data.email.lower().strip()
    with get_session() as s:
        existing = s.query(User).filter(User.email == email).first()
        if existing is not None:
            raise HTTPException(status_code=400, detail="E-mail já cadastrado")
        user = User(
            id=auth.new_user_id(),
            email=email,
            password_hash=auth.hash_password(data.password),
            nome=data.nome.strip(),
            sobrenome=data.sobrenome.strip(),
            whatsapp=data.whatsapp.strip(),
            profissao=data.profissao.strip(),
            origem=data.origem.strip(),
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        user_dict = _user_to_dict(user)

    token = auth.create_jwt(user_dict["id"])
    _set_auth_cookie(response, token)
    return {"user": user_dict}


@app.post("/api/auth/login")
def login(data: LoginIn, response: Response):
    email = data.email.lower().strip()
    with get_session() as s:
        user = s.query(User).filter(User.email == email).first()
        if user is None or user.blocked or not auth.verify_password(data.password, user.password_hash):
            raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
        user_dict = _user_to_dict(user)

    token = auth.create_jwt(user_dict["id"])
    _set_auth_cookie(response, token)
    return {"user": user_dict}


@app.post("/api/auth/logout")
def logout(response: Response):
    _clear_auth_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(auth.get_current_user)):
    return {"user": _user_to_dict(user)}


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

@app.get("/api/questions")
def get_questions(user: User = Depends(auth.get_current_user)):
    return {"questions": public_questions()}


@app.get("/api/tests")
def list_tests(user: User = Depends(auth.get_current_user)):
    return {"tests": TESTS}


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
                "perc": {
                    "tubarao": l.perc_tubarao or 0,
                    "lobo": l.perc_lobo or 0,
                    "aguia": l.perc_aguia or 0,
                    "gato": l.perc_gato or 0,
                },
            }
            for l in leads
        ]
    test = get_test(test_id)
    return {"test": test, "history": items}


@app.post("/api/tests/{test_id}/start")
def start_test(test_id: int, bg: BackgroundTasks, user: User = Depends(auth.get_current_user)):
    test = get_test(test_id)
    if test is None:
        raise HTTPException(404, "Teste não encontrado")
    if not test["ativo"]:
        raise HTTPException(400, "Teste indisponível no momento")
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
        _require_lead_owner(s, token, user)
        existing = {a.question_id: a for a in s.query(Answer).filter_by(token=token).all()}
        for qid, value in data.answers.items():
            if qid not in QUESTION_IDS or value not in VALID_ARCHETYPES:
                continue
            if qid in existing:
                existing[qid].value = value
            else:
                s.add(Answer(token=token, question_id=qid, value=value))
        s.commit()
    return {"ok": True}


@app.post("/api/lead/{token}/submit")
def submit(token: str, bg: BackgroundTasks, user: User = Depends(auth.get_current_user)):
    with get_session() as s:
        lead = _require_lead_owner(s, token, user)
        answers = {a.question_id: a.value for a in s.query(Answer).filter_by(token=token).all()}
        if any(qid not in answers for qid in QUESTION_IDS):
            raise HTTPException(400, "Responda todas as perguntas antes de enviar")
        perc = calculate(answers)
        lead.perc_tubarao = perc["tubarao"]
        lead.perc_lobo = perc["lobo"]
        lead.perc_aguia = perc["aguia"]
        lead.perc_gato = perc["gato"]
        lead.concluido_em = datetime.utcnow()
        s.commit()
        lead_dict = _lead_to_dict(lead)

    bg.add_task(sheets.update_result, token, perc)
    bg.add_task(mailer.send_result_email, lead_dict["email"], lead_dict["nome"], perc, token)
    bg.add_task(notifier.notify_new_lead, lead_dict, perc, token)

    return {"percentuais": perc}


@app.get("/api/lead/{token}")
def get_lead(token: str, user: User = Depends(auth.get_current_user)):
    with get_session() as s:
        lead = _require_lead_owner(s, token, user)
        answers = {a.question_id: a.value for a in s.query(Answer).filter_by(token=token).all()}
        messages = [
            {"role": m.role, "content": m.content}
            for m in s.query(ChatMessage).filter_by(token=token).order_by(ChatMessage.id.asc()).all()
        ]
        result = None
        if lead.concluido_em is not None:
            result = {
                "tubarao": lead.perc_tubarao or 0,
                "lobo": lead.perc_lobo or 0,
                "aguia": lead.perc_aguia or 0,
                "gato": lead.perc_gato or 0,
            }
        return {
            "lead": {
                "nome": lead.nome,
                "sobrenome": lead.sobrenome,
                "email": lead.email,
                "whatsapp": lead.whatsapp,
                "profissao": lead.profissao,
                "origem": lead.origem,
                "test_id": lead.test_id,
            },
            "answers": answers,
            "result": result,
            "chat_history": messages,
        }


@app.post("/api/chat/{token}/init")
def chat_init(token: str, user: User = Depends(auth.get_current_user)):
    with get_session() as s:
        lead = _require_lead_owner(s, token, user)
        if lead.concluido_em is None:
            raise HTTPException(400, "Teste ainda não concluído")
        existing = s.query(ChatMessage).filter_by(token=token).first()
        if existing is not None:
            return {"skipped": True}
        perc = {
            "tubarao": lead.perc_tubarao or 0,
            "lobo": lead.perc_lobo or 0,
            "aguia": lead.perc_aguia or 0,
            "gato": lead.perc_gato or 0,
        }
        msg = gemini_client.initial_message(perc)
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
        perc = {
            "tubarao": lead.perc_tubarao or 0,
            "lobo": lead.perc_lobo or 0,
            "aguia": lead.perc_aguia or 0,
            "gato": lead.perc_gato or 0,
        }
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
            for piece in gemini_client.stream_chat(history, perc):
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
    }


# =========================================================================
# ADMIN
# =========================================================================

@app.get("/admin/login")
def admin_login_page(request: Request):
    if auth.is_admin_cookie_valid(request.cookies.get(auth.ADMIN_COOKIE)):
        return RedirectResponse(url="/admin", status_code=302)
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": None})


@app.post("/admin/login")
def admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if (
        settings.admin_user
        and settings.admin_pass
        and username == settings.admin_user
        and password == settings.admin_pass
    ):
        response = RedirectResponse(url="/admin", status_code=302)
        response.set_cookie(
            key=auth.ADMIN_COOKIE,
            value=auth.make_admin_cookie(),
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=12 * 3600,
            path="/",
        )
        return response
    return templates.TemplateResponse(
        "admin_login.html",
        {"request": request, "error": "Credenciais inválidas"},
        status_code=401,
    )


@app.post("/admin/logout")
def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie(key=auth.ADMIN_COOKIE, path="/")
    return response


def _admin_guard(request: Request):
    if not auth.is_admin_cookie_valid(request.cookies.get(auth.ADMIN_COOKIE)):
        return RedirectResponse(url="/admin/login", status_code=302)
    return None


@app.get("/admin")
def admin_dashboard(request: Request):
    guard = _admin_guard(request)
    if guard:
        return guard
    with get_session() as s:
        users = s.query(User).order_by(User.created_at.desc()).all()
        counts = dict(
            s.query(Lead.user_id, func.count(Lead.token))
            .filter(Lead.concluido_em.isnot(None))
            .group_by(Lead.user_id)
            .all()
        )
        rows = [
            {
                "id": u.id,
                "nome": f"{u.nome} {u.sobrenome}".strip(),
                "email": u.email,
                "whatsapp": u.whatsapp,
                "profissao": u.profissao,
                "origem": u.origem,
                "created_at": u.created_at,
                "testes": counts.get(u.id, 0),
            }
            for u in users
        ]
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "users": rows})


@app.get("/admin/users/{user_id}")
def admin_user_detail(user_id: str, request: Request):
    guard = _admin_guard(request)
    if guard:
        return guard
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
                "perc": {
                    "tubarao": l.perc_tubarao or 0,
                    "lobo": l.perc_lobo or 0,
                    "aguia": l.perc_aguia or 0,
                    "gato": l.perc_gato or 0,
                } if l.concluido_em else None,
            }
            for l in leads
        ]
    return templates.TemplateResponse(
        "admin_user.html",
        {"request": request, "user": user_data, "results": results},
    )


@app.get("/admin/results/{token}")
def admin_result_detail(token: str, request: Request):
    guard = _admin_guard(request)
    if guard:
        return guard
    with get_session() as s:
        lead = s.get(Lead, token)
        if lead is None:
            raise HTTPException(404, "Resultado não encontrado")
        user = s.get(User, lead.user_id) if lead.user_id else None
        messages = [
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in s.query(ChatMessage).filter_by(token=token).order_by(ChatMessage.id.asc()).all()
        ]
        perc = None
        if lead.concluido_em:
            perc = {
                "tubarao": lead.perc_tubarao or 0,
                "lobo": lead.perc_lobo or 0,
                "aguia": lead.perc_aguia or 0,
                "gato": lead.perc_gato or 0,
            }
        data = {
            "token": lead.token,
            "test_nome": (get_test(lead.test_id) or {}).get("nome", f"Teste {lead.test_id}"),
            "created_at": lead.created_at,
            "concluido_em": lead.concluido_em,
            "perc": perc,
            "user_id": lead.user_id,
            "user_nome": f"{user.nome} {user.sobrenome}".strip() if user else lead.nome,
            "user_email": user.email if user else lead.email,
        }
    return templates.TemplateResponse(
        "admin_result.html",
        {"request": request, "lead": data, "messages": messages},
    )
