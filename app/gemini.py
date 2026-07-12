import logging
from pathlib import Path
from typing import Iterator

import google.generativeai as genai

from .config import settings

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPT_ARCHETYPE = PROMPTS_DIR / "analista.txt"
PROMPT_COPSOQ = PROMPTS_DIR / "analista_copsoq.txt"

_ARCH_ROTULOS = {"tubarao": "Tubarão", "lobo": "Lobo", "aguia": "Águia", "gato": "Gato"}
_NIVEL_TXT = {"verde": "risco baixo", "amarelo": "risco intermediário", "vermelho": "risco alto"}

_configured = False


def _ensure_configured():
    global _configured
    if _configured:
        return
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY não configurado")
    genai.configure(api_key=settings.gemini_api_key)
    _configured = True


# ---------------------------------------------------------------------------
# Contexto por tipo de teste
# ---------------------------------------------------------------------------
def _archetype_context(perc: dict) -> str:
    return (
        "\n\n---\nRESULTADO DO TESTE DO USUÁRIO (já realizado, use como base):\n"
        f"- Tubarão: {perc.get('tubarao', 0)}%\n"
        f"- Lobo: {perc.get('lobo', 0)}%\n"
        f"- Águia: {perc.get('aguia', 0)}%\n"
        f"- Gato: {perc.get('gato', 0)}%\n"
    )


def _copsoq_context(result: dict) -> str:
    linhas = ["\n\n---\nRESULTADO DO COPSOQ II DO USUÁRIO (já respondido; use como base da análise)."]
    linhas.append("Escala 0-100 por subescala; semáforo pela orientação de risco (verde=favorável, amarelo=intermediário, vermelho=risco).\n")
    dominios = {d["key"]: d for d in result.get("domains", [])}
    from .copsoq.structure import DOMAINS
    for dom in DOMAINS:
        d = dominios.get(dom["key"])
        if not d:
            continue
        linhas.append(f"\n## {d['nome']} — {_NIVEL_TXT.get(d.get('nivel'), 'sem dados')}")
        for s in result.get("subscales", []):
            if s["dominio"] != dom["key"] or s.get("score") is None:
                continue
            linhas.append(f"- {s['nome']}: {s['score']}/100 ({_NIVEL_TXT.get(s.get('nivel'), '-')})")
    top = result.get("top_riscos") or []
    if top:
        linhas.append("\n## Principais focos de risco (maior para menor):")
        for t in top:
            linhas.append(f"- {t['nome']} ({_NIVEL_TXT.get(t.get('nivel'), '-')})")
    return "\n".join(linhas)


def _system_prompt(result: dict) -> str:
    if result and result.get("type") == "copsoq":
        base = PROMPT_COPSOQ.read_text(encoding="utf-8")
        return base + _copsoq_context(result)
    perc = (result or {}).get("perc", {})
    base = PROMPT_ARCHETYPE.read_text(encoding="utf-8")
    return base + _archetype_context(perc)


# ---------------------------------------------------------------------------
# Mensagem inicial
# ---------------------------------------------------------------------------
def initial_message(result: dict) -> str:
    if result and result.get("type") == "copsoq":
        top = result.get("top_riscos") or []
        vermelhos = [d["nome"] for d in result.get("domains", []) if d.get("nivel") == "vermelho"]
        verdes = [d["nome"] for d in result.get("domains", []) if d.get("nivel") == "verde"]
        foco = ", ".join(t["nome"] for t in top[:3]) if top else "nenhum ponto crítico evidente"
        parte_area = ""
        if vermelhos:
            parte_area = f" As áreas de maior atenção estão em **{', '.join(vermelhos)}**."
        elif verdes:
            parte_area = f" No geral, seus indicadores estão favoráveis (destaque para {', '.join(verdes[:2])})."
        return (
            "Olá! Sou seu analista de **riscos psicossociais no trabalho**, especializado no COPSOQ II. "
            "Já recebi o resultado do seu questionário e organizei seu perfil por dimensões.\n\n"
            f"Os principais focos de atenção são: **{foco}**.{parte_area}\n\n"
            "Posso começar a análise detalhada, explicando o que cada dimensão significa e sugerindo caminhos de melhoria?"
        )
    perc = (result or {}).get("perc", {})
    nome_principal = max(perc, key=perc.get) if perc else "tubarao"
    return (
        f"Olá! Sou seu analista comportamental especializado no teste MyDNA. "
        f"Já recebi o resultado do seu teste: seu arquétipo predominante é **{_ARCH_ROTULOS.get(nome_principal, 'Tubarão')}** "
        f"({perc.get(nome_principal, 0)}%), com a seguinte composição — Tubarão {perc.get('tubarao', 0)}%, "
        f"Lobo {perc.get('lobo', 0)}%, Águia {perc.get('aguia', 0)}%, Gato {perc.get('gato', 0)}%.\n\n"
        f"Posso iniciar a análise completa do seu perfil agora?"
    )


def _to_gemini_history(messages: list[dict]) -> list[dict]:
    history = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        history.append({"role": role, "parts": [m["content"]]})
    return history


def stream_chat(messages: list[dict], result: dict) -> Iterator[str]:
    _ensure_configured()
    model = genai.GenerativeModel(
        "gemini-pro-latest",
        system_instruction=_system_prompt(result),
    )
    history = _to_gemini_history(messages[:-1])
    last = messages[-1]["content"]
    chat = model.start_chat(history=history)
    response = chat.send_message(last, stream=True)
    for chunk in response:
        if chunk.text:
            yield chunk.text
