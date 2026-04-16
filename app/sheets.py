import json
import logging
from datetime import datetime
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from .config import settings

log = logging.getLogger(__name__)

HEADERS = [
    "timestamp",
    "token",
    "nome",
    "sobrenome",
    "whatsapp",
    "email",
    "profissao",
    "origem",
    "perc_tubarao",
    "perc_lobo",
    "perc_aguia",
    "perc_gato",
    "concluido_em",
    "link_retorno",
]

_client = None
_worksheet = None


def _get_worksheet():
    global _client, _worksheet
    if _worksheet is not None:
        return _worksheet
    if not settings.google_credentials_json or not settings.google_sheet_id:
        log.warning("Google Sheets não configurado — pulando persistência externa")
        return None
    info = json.loads(settings.google_credentials_json)
    creds = Credentials.from_service_account_info(
        info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    _client = gspread.authorize(creds)
    sh = _client.open_by_key(settings.google_sheet_id)
    ws = sh.sheet1
    existing = ws.row_values(1)
    if existing != HEADERS:
        ws.update("A1", [HEADERS])
    _worksheet = ws
    return _worksheet


def append_lead(lead: dict[str, Any]) -> None:
    ws = _get_worksheet()
    if ws is None:
        return
    try:
        link = f"{settings.public_base_url}/r/{lead['token']}"
        ws.append_row(
            [
                datetime.utcnow().isoformat(),
                lead["token"],
                lead.get("nome", ""),
                lead.get("sobrenome", ""),
                lead.get("whatsapp", ""),
                lead.get("email", ""),
                lead.get("profissao", ""),
                lead.get("origem", ""),
                "",
                "",
                "",
                "",
                "",
                link,
            ],
            value_input_option="USER_ENTERED",
        )
    except Exception as exc:
        log.error("Falha ao inserir lead no Sheets: %s", exc)


def update_result(token: str, percentuais: dict[str, int]) -> None:
    ws = _get_worksheet()
    if ws is None:
        return
    try:
        cell = ws.find(token, in_column=2)
        if cell is None:
            return
        row = cell.row
        ws.update(
            f"I{row}:M{row}",
            [
                [
                    percentuais.get("tubarao", 0),
                    percentuais.get("lobo", 0),
                    percentuais.get("aguia", 0),
                    percentuais.get("gato", 0),
                    datetime.utcnow().isoformat(),
                ]
            ],
            value_input_option="USER_ENTERED",
        )
    except Exception as exc:
        log.error("Falha ao atualizar resultado no Sheets: %s", exc)
