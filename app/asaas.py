"""Client HTTP do ASAAS.

Padrão validado em produção (ver `INSTRUCAO-ASAAS-PARA-OUTRO-PROJETO.md` no projeto
sai-comercial). Detalhes que NÃO são estilo, são requisito:

- auth é o header `access_token` — `Authorization: Bearer` não funciona;
- `User-Agent` é obrigatório: sem ele alguns endpoints devolvem 403;
- CPF/CNPJ vão só com dígitos (máscara causa erro intermitente);
- `externalReference` em tudo que é criado, senão depurar fica impossível;
- `billingType="UNDEFINED"` faz o ASAAS gerar uma `invoiceUrl` onde o próprio cliente
  escolhe boleto, PIX ou cartão. Fixar em BOLETO tira a opção de PIX dele.

Sem regra de negócio aqui — isso é `app/billing.py`.
"""

import logging
import re

import httpx

from . import settings_store
from .config import settings

log = logging.getLogger(__name__)

BASE_URLS = {
    "production": "https://api.asaas.com/v3",
    "sandbox": "https://api-sandbox.asaas.com/v3",
}
USER_AGENT = "teste-perfil-comportamental/1.0"
TIMEOUT = 25.0


class AsaasNaoConfigurado(RuntimeError):
    """Sem token: a integração ainda não foi configurada em /admin/integracoes."""


class AsaasErro(RuntimeError):
    def __init__(self, status: int, descricao: str, raw: object = None):
        super().__init__(f"ASAAS {status}: {descricao}")
        self.status = status
        self.descricao = descricao
        self.raw = raw


def so_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def config() -> tuple[str, str]:
    """(token, env). O AppSetting vence o .env — trocar de conta não exige deploy."""
    cfg = settings_store.get_many([settings_store.ASAAS_TOKEN, settings_store.ASAAS_ENV])
    token = cfg.get(settings_store.ASAAS_TOKEN) or (settings.asaas_api_key or "").strip()
    env = cfg.get(settings_store.ASAAS_ENV) or (settings.asaas_env or "sandbox").strip()
    if not token:
        raise AsaasNaoConfigurado(
            "A integração com o ASAAS ainda não foi configurada. Informe o token em Integrações."
        )
    return token, ("production" if env == "production" else "sandbox")


def configurado() -> bool:
    try:
        config()
        return True
    except AsaasNaoConfigurado:
        return False


def ambiente() -> str:
    cfg = settings_store.get(settings_store.ASAAS_ENV) or (settings.asaas_env or "sandbox")
    return "production" if cfg == "production" else "sandbox"


def _request(method: str, path: str, body: dict | None = None, params: dict | None = None) -> dict:
    token, env = config()
    url = f"{BASE_URLS[env]}{path}"
    headers = {
        "access_token": token,
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.request(method, url, headers=headers, json=body, params=params, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise AsaasErro(0, f"não consegui falar com o ASAAS ({exc})") from exc

    try:
        data = resp.json() if resp.content else {}
    except ValueError:
        data = {}

    if resp.status_code >= 400:
        erros = data.get("errors") if isinstance(data, dict) else None
        descricao = "erro desconhecido"
        if isinstance(erros, list) and erros:
            descricao = str(erros[0].get("description") or descricao)
        elif resp.text:
            descricao = resp.text[:200]
        raise AsaasErro(resp.status_code, descricao, data)
    return data if isinstance(data, dict) else {"data": data}


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
def find_customer_by_cpf(cpf_cnpj: str) -> dict | None:
    doc = so_digitos(cpf_cnpj)
    if not doc:
        return None
    data = _request("GET", "/customers", params={"cpfCnpj": doc, "limit": 10})
    itens = data.get("data") or []
    return itens[0] if itens else None


def create_customer(
    nome: str,
    cpf_cnpj: str,
    email: str = "",
    telefone: str = "",
    external_reference: str = "",
) -> dict:
    body = {
        "name": nome,
        "cpfCnpj": so_digitos(cpf_cnpj),
        "email": email or None,
        "mobilePhone": so_digitos(telefone) or None,
        "externalReference": external_reference or None,
        "notificationDisabled": False,
    }
    return _request("POST", "/customers", {k: v for k, v in body.items() if v is not None})


def delete_customer(customer_id: str) -> dict:
    return _request("DELETE", f"/customers/{customer_id}")


# ---------------------------------------------------------------------------
# Assinaturas e cobranças
# ---------------------------------------------------------------------------
def create_subscription(
    customer_id: str,
    valor_centavos: int,
    next_due_date: str,
    ciclo: str = "MONTHLY",
    descricao: str = "",
    external_reference: str = "",
) -> dict:
    body = {
        "customer": customer_id,
        "billingType": "UNDEFINED",  # cliente escolhe boleto/PIX/cartão na invoiceUrl
        "value": round(valor_centavos / 100, 2),
        "nextDueDate": next_due_date,
        "cycle": ciclo,
        "description": descricao or "Avaliação de riscos psicossociais (NR-1)",
        "externalReference": external_reference or None,
    }
    return _request("POST", "/subscriptions", {k: v for k, v in body.items() if v is not None})


def delete_subscription(subscription_id: str) -> dict:
    return _request("DELETE", f"/subscriptions/{subscription_id}")


def list_subscription_payments(subscription_id: str) -> list[dict]:
    data = _request("GET", f"/subscriptions/{subscription_id}/payments")
    return data.get("data") or []


def get_payment(payment_id: str) -> dict:
    return _request("GET", f"/payments/{payment_id}")


def delete_payment(payment_id: str) -> dict:
    return _request("DELETE", f"/payments/{payment_id}")


def list_payments_by_customer(customer_id: str, limit: int = 100) -> list[dict]:
    data = _request("GET", "/payments", params={"customer": customer_id, "limit": limit})
    return data.get("data") or []


def ping() -> dict:
    """Teste de conexão da tela de integrações."""
    return _request("GET", "/customers", params={"limit": 1})
