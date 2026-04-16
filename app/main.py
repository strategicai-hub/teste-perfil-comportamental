import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from . import gemini as gemini_client
from . import mailer, notifier, sheets
from .db import Answer, ChatMessage, Lead, get_session, init_db
from .questions import QUESTION_IDS, VALID_ARCHETYPES, public_questions
from .scoring import calculate

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

APP_DIR = Path(__file__).parent.parent
STATIC_DIR = APP_DIR / "static"
ASSETS_DIR = APP_DIR / "assets"
INDEX_FILE = STATIC_DIR / "index.html"
FAVICON_FILE = ASSETS_DIR / "favicon-sai.png"

app = FastAPI(title="Teste de Perfil Comportamental")


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
def retorno(token: str):
    return FileResponse(INDEX_FILE)


@app.get("/api/questions")
def get_questions():
    return {"questions": public_questions()}


class LeadIn(BaseModel):
    nome: str = Field(..., min_length=1, max_length=120)
    sobrenome: str = Field(..., min_length=1, max_length=120)
    whatsapp: str = Field(..., min_length=6, max_length=40)
    email: EmailStr
    profissao: str = Field("", max_length=200)
    origem: str = Field("", max_length=200)


@app.post("/api/lead")
def create_lead(data: LeadIn, bg: BackgroundTasks):
    token = uuid.uuid4().hex
    with get_session() as s:
        lead = Lead(
            token=token,
            nome=data.nome.strip(),
            sobrenome=data.sobrenome.strip(),
            whatsapp=data.whatsapp.strip(),
            email=data.email.strip(),
            profissao=data.profissao.strip(),
            origem=data.origem.strip(),
        )
        s.add(lead)
        s.commit()
        lead_dict = _lead_to_dict(lead)
    bg.add_task(sheets.append_lead, lead_dict)
    return {"token": token}


class AnswersPatch(BaseModel):
    answers: dict[str, str]


@app.patch("/api/lead/{token}/answers")
def save_answers(token: str, data: AnswersPatch):
    with get_session() as s:
        lead = s.get(Lead, token)
        if lead is None:
            raise HTTPException(404, "Lead não encontrado")
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
def submit(token: str, bg: BackgroundTasks):
    with get_session() as s:
        lead = s.get(Lead, token)
        if lead is None:
            raise HTTPException(404, "Lead não encontrado")
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


@app.post("/api/lead/{token}/retake")
def retake(token: str, bg: BackgroundTasks):
    with get_session() as s:
        old = s.get(Lead, token)
        if old is None:
            raise HTTPException(404, "Lead não encontrado")
        new_token = uuid.uuid4().hex
        new_lead = Lead(
            token=new_token,
            nome=old.nome,
            sobrenome=old.sobrenome,
            whatsapp=old.whatsapp,
            email=old.email,
            profissao=old.profissao,
            origem=old.origem,
        )
        s.add(new_lead)
        s.commit()
        lead_dict = _lead_to_dict(new_lead)
    bg.add_task(sheets.append_lead, lead_dict)
    return {"token": new_token}


@app.get("/api/lead/{token}")
def get_lead(token: str):
    with get_session() as s:
        lead = s.get(Lead, token)
        if lead is None:
            raise HTTPException(404, "Lead não encontrado")
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
            },
            "answers": answers,
            "result": result,
            "chat_history": messages,
        }


@app.post("/api/chat/{token}/init")
def chat_init(token: str):
    with get_session() as s:
        lead = s.get(Lead, token)
        if lead is None or lead.concluido_em is None:
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
def chat(token: str, data: ChatIn):
    with get_session() as s:
        lead = s.get(Lead, token)
        if lead is None or lead.concluido_em is None:
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
        "nome": lead.nome,
        "sobrenome": lead.sobrenome,
        "whatsapp": lead.whatsapp,
        "email": lead.email,
        "profissao": lead.profissao,
        "origem": lead.origem,
    }
