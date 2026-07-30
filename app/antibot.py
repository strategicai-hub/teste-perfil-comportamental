"""Proteção do cadastro público — sem dependência externa.

O link é aberto (qualquer um pode se cadastrar), então as camadas aqui existem para
que um bot não crie centenas de contas. Nenhuma delas depende de reCAPTCHA/hCaptcha:
o app não tem chave de serviço externo, e o desafio é assinado com o próprio
`jwt_secret`.

Camadas, na ordem em que o submit deve aplicá-las:

1. rate limit por IP;
2. honeypot (campo invisível que humano nunca preenche);
3. desafio matemático assinado, com tempo mínimo de preenchimento;
4. validação de e-mail e de CPF/CNPJ.
"""

import hashlib
import hmac
import random
import threading
import time
from collections import deque

from fastapi import Request

from .config import settings

# Janela deslizante em memória. Suficiente com uma réplica (é o caso do compose);
# com duas, cada uma teria a própria contagem — o limite dobraria, sem furar a defesa.
_HITS: dict[str, deque] = {}
_LOCK = threading.Lock()

TEMPO_MINIMO_S = 3
VALIDADE_DESAFIO_S = 1800


def client_ip(request: Request) -> str:
    """IP real do cliente. Em produção o app fica atrás do Traefik, então o primeiro
    salto de X-Forwarded-For é quem interessa."""
    encaminhado = request.headers.get("x-forwarded-for", "")
    if encaminhado:
        return encaminhado.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "desconhecido")[:64]


def rate_limit(chave: str, limite: int, janela_s: int) -> bool:
    """True se a requisição está dentro do limite; False se estourou."""
    agora = time.monotonic()
    with _LOCK:
        fila = _HITS.setdefault(chave, deque())
        while fila and agora - fila[0] > janela_s:
            fila.popleft()
        if len(fila) >= limite:
            return False
        fila.append(agora)
        # Limpeza oportunista: sem isso o dict cresce indefinidamente com IPs antigos.
        if len(_HITS) > 5000:
            for k in [k for k, v in _HITS.items() if not v or agora - v[-1] > janela_s]:
                _HITS.pop(k, None)
        return True


def _assina(dados: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), dados.encode(), hashlib.sha256).hexdigest()[:32]


def novo_desafio() -> tuple[str, str]:
    """('Quanto é 7 + 5?', token). O token carrega a resposta (em hash) e o instante
    de emissão, então o servidor não guarda estado nenhum."""
    a, b = random.randint(2, 9), random.randint(2, 9)
    resposta = str(a + b)
    emitido = int(time.time())
    corpo = f"{emitido}.{_assina(resposta + str(emitido))}"
    token = f"{corpo}.{_assina(corpo)}"
    return f"Quanto é {a} + {b}?", token


def valida_desafio(token: str, resposta: str) -> bool:
    partes = (token or "").split(".")
    if len(partes) != 3:
        return False
    emitido_txt, resposta_hash, assinatura = partes
    if not hmac.compare_digest(assinatura, _assina(f"{emitido_txt}.{resposta_hash}")):
        return False
    try:
        emitido = int(emitido_txt)
    except ValueError:
        return False
    agora = int(time.time())
    # Rápido demais = script. Antigo demais = formulário abandonado/reaproveitado.
    if agora - emitido < TEMPO_MINIMO_S or agora - emitido > VALIDADE_DESAFIO_S:
        return False
    esperado = _assina((resposta or "").strip() + emitido_txt)
    return hmac.compare_digest(resposta_hash, esperado)


# ---------------------------------------------------------------------------
# CPF / CNPJ
# ---------------------------------------------------------------------------
def digitos(valor: str) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


_digitos = digitos  # alias interno


def cpf_valido(cpf: str) -> bool:
    d = _digitos(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d[i]) * (tamanho + 1 - i) for i in range(tamanho))
        dv = (soma * 10) % 11
        dv = 0 if dv == 10 else dv
        if dv != int(d[tamanho]):
            return False
    return True


def cnpj_valido(cnpj: str) -> bool:
    d = _digitos(cnpj)
    if len(d) != 14 or d == d[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        soma = sum(int(d[i]) * pesos[i] for i in range(pos))
        dv = soma % 11
        dv = 0 if dv < 2 else 11 - dv
        if dv != int(d[pos]):
            return False
    return True


def documento_valido(valor: str) -> bool:
    """Valida localmente para não criar no ASAAS uma fatura que nunca vai colar."""
    d = _digitos(valor)
    if len(d) == 11:
        return cpf_valido(d)
    if len(d) == 14:
        return cnpj_valido(d)
    return False
