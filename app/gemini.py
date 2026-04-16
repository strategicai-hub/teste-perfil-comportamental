import logging
from pathlib import Path
from typing import Iterator

import google.generativeai as genai

from .config import settings

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "analista.txt"

_configured = False


def _ensure_configured():
    global _configured
    if _configured:
        return
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY não configurado")
    genai.configure(api_key=settings.gemini_api_key)
    _configured = True


def _system_prompt(perc: dict[str, int]) -> str:
    base = PROMPT_PATH.read_text(encoding="utf-8")
    contexto = (
        "\n\n---\nRESULTADO DO TESTE DO USUÁRIO (já realizado, use como base):\n"
        f"- Tubarão: {perc.get('tubarao', 0)}%\n"
        f"- Lobo: {perc.get('lobo', 0)}%\n"
        f"- Águia: {perc.get('aguia', 0)}%\n"
        f"- Gato: {perc.get('gato', 0)}%\n"
    )
    return base + contexto


def _to_gemini_history(messages: list[dict]) -> list[dict]:
    history = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        history.append({"role": role, "parts": [m["content"]]})
    return history


def initial_message(perc: dict[str, int]) -> str:
    nome_principal = max(perc, key=perc.get)
    rotulos = {"tubarao": "Tubarão", "lobo": "Lobo", "aguia": "Águia", "gato": "Gato"}
    return (
        f"Olá! Sou seu analista comportamental especializado no teste MyDNA. "
        f"Já recebi o resultado do seu teste: seu arquétipo predominante é **{rotulos[nome_principal]}** "
        f"({perc[nome_principal]}%), com a seguinte composição — Tubarão {perc.get('tubarao',0)}%, "
        f"Lobo {perc.get('lobo',0)}%, Águia {perc.get('aguia',0)}%, Gato {perc.get('gato',0)}%.\n\n"
        f"Posso iniciar a análise completa do seu perfil agora?"
    )


def stream_chat(messages: list[dict], perc: dict[str, int]) -> Iterator[str]:
    _ensure_configured()
    model = genai.GenerativeModel(
        "gemini-2.5-pro",
        system_instruction=_system_prompt(perc),
    )
    history = _to_gemini_history(messages[:-1])
    last = messages[-1]["content"]
    chat = model.start_chat(history=history)
    response = chat.send_message(last, stream=True)
    for chunk in response:
        if chunk.text:
            yield chunk.text
