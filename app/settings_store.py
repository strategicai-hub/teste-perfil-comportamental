"""Config de runtime em banco (`AppSetting`).

Existe para o token e o ambiente do ASAAS poderem ser trocados sem redeploy — é o
que permite testar em sandbox e depois virar para produção pela própria tela de
integrações. O valor gravado aqui **vence** o `.env`.
"""

from .db import AppSetting, get_session

ASAAS_TOKEN = "asaas_token"
ASAAS_ENV = "asaas_env"
ASAAS_WEBHOOK_TOKEN = "asaas_webhook_token"


def get(key: str, default: str = "") -> str:
    with get_session() as s:
        row = s.get(AppSetting, key)
        return (row.value or "").strip() if row else default


def get_many(keys: list[str]) -> dict[str, str]:
    with get_session() as s:
        rows = s.query(AppSetting).filter(AppSetting.key.in_(keys)).all()
        return {r.key: (r.value or "").strip() for r in rows}


def set(key: str, value: str) -> None:  # noqa: A001 - nome espelha o get
    with get_session() as s:
        row = s.get(AppSetting, key)
        if row is None:
            s.add(AppSetting(key=key, value=value or ""))
        else:
            row.value = value or ""
        s.commit()


def mask(value: str) -> str:
    """Máscara para exibir um token na tela sem vazá-lo."""
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}{'•' * 12}{value[-4:]}"
