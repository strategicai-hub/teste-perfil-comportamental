import logging

import httpx

from .config import settings

log = logging.getLogger(__name__)


def notify_new_lead(lead: dict, result: dict, token: str) -> None:
    if not settings.uazapi_base_url or not settings.uazapi_token or not settings.alert_phone:
        log.warning("UAZAPI não configurado — pulando notificação")
        return

    link = f"{settings.public_base_url}/r/{token}"
    nome_completo = f"{lead.get('nome','')} {lead.get('sobrenome','')}".strip()

    if result and result.get("type") == "copsoq":
        top = result.get("top_riscos") or []
        riscos = "\n".join(f"• {t['nome']} ({t.get('nivel')})" for t in top[:5]) or "sem dados"
        contexto = ""
        if lead.get("area"):
            contexto = f"Área: {lead.get('area')}\n"
        resultado_txt = f"*Principais riscos:*\n{riscos}"
        titulo = "*Nova resposta — COPSOQ II (Riscos Psicossociais)*"
    else:
        perc = (result or {}).get("perc", {})
        contexto = ""
        resultado_txt = (
            f"Resultado:\n"
            f"Tubarão {perc.get('tubarao',0)}% | Lobo {perc.get('lobo',0)}% | "
            f"Águia {perc.get('aguia',0)}% | Gato {perc.get('gato',0)}%"
        )
        titulo = "*Novo lead no Teste de Perfil*"

    text = (
        f"{titulo}\n\n"
        f"Nome: {nome_completo}\n"
        f"E-mail: {lead.get('email','')}\n"
        f"WhatsApp: {lead.get('whatsapp','')}\n"
        f"{contexto}\n"
        f"{resultado_txt}\n\n"
        f"Ver análise: {link}"
    )

    url = settings.uazapi_base_url.rstrip("/") + "/send/text"
    headers = {"token": settings.uazapi_token, "Content-Type": "application/json"}
    payload = {"number": settings.alert_phone, "text": text}

    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
    except Exception as exc:
        log.error("Falha ao notificar via UAZAPI: %s", exc)
