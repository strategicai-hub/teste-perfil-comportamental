"""Regra de cobrança e de liberação de acesso.

Dois modelos de cobrança convivem:

- `proprio`: a empresa (ou consultoria) tem assinatura própria no ASAAS;
- `pelo_consultor`: a empresa foi trazida por uma consultoria e é ela quem paga —
  a empresa não gera assinatura nenhuma;
- `isento`: liberado sem cobrança (primeiros clientes, cortesias). Nunca bloqueia.

`acesso()` é a única porta de bloqueio do sistema e **nunca** chama o ASAAS: só lê o
banco. Gateway fora do ar não pode derrubar o painel de quem está em dia.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import asaas, auth
from .db import Charge, Company, Plan, WebhookEvent, get_session
from .web.deps import hoje_sp

log = logging.getLogger(__name__)

# Dias de tolerância após o vencimento antes de travar o acesso.
GRACE_DAYS = 7
# Sem período de teste: a primeira fatura vence poucos dias após a aprovação.
# A tela de aprovação pode sobrescrever essa data (é assim que se dá cortesia longa).
PRIMEIRA_FATURA_DIAS = 5

MOTIVO_TEXTO = {
    "pendente_aprovacao": "Seu cadastro está em análise.",
    "recusado": "Este cadastro não foi aprovado.",
    "inadimplente": "Há uma fatura em aberto vencida há mais de 7 dias.",
    "suspenso": "O acesso deste cadastro está suspenso.",
}


@dataclass
class Acesso:
    bloqueado: bool = False
    motivo: str = ""
    dias_atraso: int = 0
    pagador_id: str | None = None
    pagador_nome: str = ""

    @property
    def texto(self) -> str:
        return MOTIVO_TEXTO.get(self.motivo, "")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def map_status(status: str | None) -> str:
    s = (status or "").upper()
    if s in ("RECEIVED", "RECEIVED_IN_CASH"):
        return Charge.RECEIVED
    if s == "CONFIRMED":
        return Charge.CONFIRMED
    if s == "OVERDUE":
        return Charge.OVERDUE
    if s in ("REFUNDED", "REFUND_REQUESTED", "CHARGEBACK_REQUESTED", "CHARGEBACK_DISPUTE"):
        return Charge.REFUNDED
    if s == "DELETED":
        return Charge.DELETED
    return Charge.PENDING


def _para_datetime(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _centavos(valor: object) -> int:
    try:
        return int(round(float(valor) * 100))
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Quem paga
# ---------------------------------------------------------------------------
def pagador(s, company: Company | None) -> Company | None:
    """Tenant responsável pela fatura deste tenant.

    Empresa marcada como coberta pelo consultor devolve a consultoria dona — é por
    isso que a inadimplência do consultor derruba todas as empresas dele de graça.
    """
    if company is None:
        return None
    if company.billing_mode == Company.BILLING_CONSULTOR and company.parent_id:
        pai = s.get(Company, company.parent_id)
        if pai is not None:
            return pai
    return company


# ---------------------------------------------------------------------------
# Assinatura
# ---------------------------------------------------------------------------
def ensure_subscription(company_id: str, primeira_fatura: date | None = None) -> None:
    """Cria customer + assinatura no ASAAS para o tenant, se ainda não existir.

    Idempotente por `asaas_subscription_id` — duplo clique em "aprovar" não pode
    gerar duas assinaturas reais. Sai sem fazer nada em `isento` e `pelo_consultor`:
    a única porta para começar a cobrar quem está isento é trocar o `billing_mode`
    antes de chamar esta função.
    """
    with get_session() as s:
        company = s.get(Company, company_id)
        if company is None:
            return
        if company.billing_mode in (Company.BILLING_ISENTO, Company.BILLING_CONSULTOR):
            return
        if company.asaas_subscription_id:
            return
        plano = s.get(Plan, company.plan_id) if company.plan_id else None
        if plano is None:
            plano = (
                s.query(Plan)
                .filter(Plan.ativo == True, Plan.tipo == _tipo_plano(company))  # noqa: E712
                .order_by(Plan.ordem.asc(), Plan.id.asc())
                .first()
            )
        if plano is None or plano.valor_centavos <= 0:
            company.asaas_erro = "Nenhum plano com valor definido para este cadastro."
            s.commit()
            return
        dados = {
            "nome": company.nome,
            "cpf_cnpj": company.cpf_cnpj,
            "email": company.manager_email,
            "customer_id": company.asaas_customer_id,
            "valor": plano.valor_centavos,
            "ciclo": plano.ciclo,
            "plano_nome": plano.nome,
        }

    vencimento = primeira_fatura or (hoje_sp() + timedelta(days=PRIMEIRA_FATURA_DIAS))
    ref = f"company:{company_id}"
    try:
        customer_id = dados["customer_id"]
        if not customer_id:
            # Reusar o customer por documento evita duplicar cadastro no ASAAS.
            existente = asaas.find_customer_by_cpf(dados["cpf_cnpj"])
            if existente and existente.get("id"):
                customer_id = existente["id"]
            else:
                criado = asaas.create_customer(
                    nome=dados["nome"],
                    cpf_cnpj=dados["cpf_cnpj"],
                    email=dados["email"],
                    external_reference=ref,
                )
                customer_id = criado.get("id")
        if not customer_id:
            raise asaas.AsaasErro(0, "ASAAS não devolveu o id do cliente")

        assinatura = asaas.create_subscription(
            customer_id=customer_id,
            valor_centavos=dados["valor"],
            next_due_date=vencimento.isoformat(),
            ciclo=dados["ciclo"],
            descricao=f"{dados['plano_nome']} — NR-1",
            external_reference=ref,
        )
    except (asaas.AsaasErro, asaas.AsaasNaoConfigurado) as exc:
        log.error("Falha ao criar assinatura do tenant %s: %s", company_id, exc)
        with get_session() as s:
            company = s.get(Company, company_id)
            if company is not None:
                company.asaas_erro = str(exc)[:300]
                s.commit()
        return

    with get_session() as s:
        company = s.get(Company, company_id)
        if company is None:
            return
        company.asaas_customer_id = customer_id
        company.asaas_subscription_id = assinatura.get("id")
        company.asaas_erro = None
        s.commit()

    # As cobranças da assinatura já nascem aqui — trazer agora evita a tela de
    # faturas ficar vazia até o primeiro webhook chegar.
    try:
        for pagamento in asaas.list_subscription_payments(assinatura.get("id") or ""):
            upsert_charge(pagamento, company_id)
    except (asaas.AsaasErro, asaas.AsaasNaoConfigurado) as exc:
        log.warning("Assinatura criada mas não consegui listar as cobranças: %s", exc)


def _tipo_plano(company: Company) -> str:
    return Plan.TIPO_CONSULTORIA if company.e_consultoria else Plan.TIPO_EMPRESA


def cancelar_assinatura(company_id: str) -> None:
    """Cancela a assinatura e apaga as cobranças futuras ainda não pagas.

    Só o DELETE da assinatura não basta: as cobranças já geradas continuam de pé e
    o cliente recebe boleto de algo que cancelou.
    """
    with get_session() as s:
        company = s.get(Company, company_id)
        if company is None or not company.asaas_subscription_id:
            return
        sub_id, customer_id = company.asaas_subscription_id, company.asaas_customer_id

    try:
        asaas.delete_subscription(sub_id)
        if customer_id:
            hoje = hoje_sp()
            for pagamento in asaas.list_payments_by_customer(customer_id):
                venc = _para_datetime(pagamento.get("dueDate"))
                if map_status(pagamento.get("status")) == Charge.PENDING and venc and venc.date() >= hoje:
                    try:
                        asaas.delete_payment(pagamento["id"])
                    except asaas.AsaasErro as exc:
                        log.warning("Não consegui apagar a cobrança %s: %s", pagamento.get("id"), exc)
    except (asaas.AsaasErro, asaas.AsaasNaoConfigurado) as exc:
        log.error("Falha ao cancelar assinatura do tenant %s: %s", company_id, exc)
        return

    with get_session() as s:
        company = s.get(Company, company_id)
        if company is not None:
            company.asaas_subscription_id = None
            s.commit()


# ---------------------------------------------------------------------------
# Cobranças
# ---------------------------------------------------------------------------
def _resolve_company_id(s, pagamento: dict) -> str | None:
    ref = str(pagamento.get("externalReference") or "")
    if ref.startswith("company:"):
        cid = ref.split(":", 1)[1]
        if s.get(Company, cid) is not None:
            return cid
    customer = pagamento.get("customer")
    if customer:
        achado = s.query(Company).filter(Company.asaas_customer_id == customer).first()
        if achado is not None:
            return achado.id
    return None


def upsert_charge(pagamento: dict, company_id: str | None = None) -> Charge | None:
    """Espelha uma cobrança do ASAAS no banco. Chave é `asaas_payment_id` (unique)."""
    payment_id = pagamento.get("id")
    if not payment_id:
        return None
    with get_session() as s:
        cid = company_id or _resolve_company_id(s, pagamento)
        if not cid:
            log.warning("[asaas] cobrança %s sem tenant associado", payment_id)
            return None
        charge = s.query(Charge).filter(Charge.asaas_payment_id == payment_id).first()
        if charge is None:
            charge = Charge(id=uuid.uuid4().hex, asaas_payment_id=payment_id, company_id=cid)
            s.add(charge)
        charge.company_id = cid
        charge.descricao = str(pagamento.get("description") or "Assinatura")[:200]
        charge.valor_centavos = _centavos(pagamento.get("value"))
        charge.net_centavos = _centavos(pagamento.get("netValue")) or None
        charge.due_date = _para_datetime(pagamento.get("dueDate")) or datetime.utcnow()
        charge.payment_date = _para_datetime(
            pagamento.get("paymentDate") or pagamento.get("clientPaymentDate")
        )
        charge.status = map_status(pagamento.get("status"))
        charge.billing_type = pagamento.get("billingType")
        charge.invoice_url = pagamento.get("invoiceUrl")
        charge.bank_slip_url = pagamento.get("bankSlipUrl")
        s.commit()
        s.refresh(charge)
        s.expunge(charge)
        return charge


def registrar_evento(external_id: str, event_type: str, payload: str) -> bool:
    """Grava o evento e devolve True se ele é novo (deve ser processado).

    A unique `(provider, external_id, event_type)` é a idempotência: reentrega do
    mesmo evento colide e volta False.
    """
    from sqlalchemy.exc import IntegrityError

    with get_session() as s:
        try:
            s.add(WebhookEvent(
                provider="asaas", external_id=external_id, event_type=event_type, payload=payload[:20000]
            ))
            s.commit()
            return True
        except IntegrityError:
            s.rollback()
            return False


def marcar_evento_processado(external_id: str, event_type: str) -> None:
    with get_session() as s:
        row = (
            s.query(WebhookEvent)
            .filter(
                WebhookEvent.provider == "asaas",
                WebhookEvent.external_id == external_id,
                WebhookEvent.event_type == event_type,
            )
            .first()
        )
        if row is not None:
            row.processed = True
            s.commit()


def reconciliar(limite: int = 100) -> int:
    """Confere no ASAAS as cobranças em aberto que já venceram ou vencem em breve.

    Rede de segurança para webhook perdido (deploy no meio, header errado, timeout).
    """
    if not asaas.configurado():
        return 0
    limite_data = datetime.utcnow() + timedelta(days=7)
    with get_session() as s:
        pendentes = [
            c.asaas_payment_id
            for c in s.query(Charge)
            .filter(Charge.status.in_(Charge.ABERTOS), Charge.due_date <= limite_data)
            .order_by(Charge.due_date.asc())
            .limit(limite)
            .all()
        ]
    atualizadas = 0
    for payment_id in pendentes:
        try:
            if upsert_charge(asaas.get_payment(payment_id)) is not None:
                atualizadas += 1
        except (asaas.AsaasErro, asaas.AsaasNaoConfigurado) as exc:
            log.warning("Reconciliação falhou para %s: %s", payment_id, exc)
    if atualizadas:
        log.info("Reconciliação ASAAS: %s cobrança(s) conferida(s)", atualizadas)
    return atualizadas


# ---------------------------------------------------------------------------
# Acesso
# ---------------------------------------------------------------------------
def acesso(s, company: Company | None, user_role: str) -> Acesso:
    """Decide se o tenant pode usar o sistema. Só lê o banco — nunca chama o ASAAS."""
    # O owner nunca é bloqueado: sem essa trava, um erro de cobrança tranca a
    # própria administração do sistema.
    if user_role == auth.SUPER_ADMIN:
        return Acesso()
    if company is None:
        return Acesso()

    status = company.status or Company.STATUS_ATIVO
    if status == Company.STATUS_PENDENTE:
        return Acesso(True, "pendente_aprovacao")
    if status == Company.STATUS_RECUSADO:
        return Acesso(True, "recusado")
    if status == Company.STATUS_SUSPENSO:
        return Acesso(True, "suspenso")

    if company.billing_mode == Company.BILLING_ISENTO:
        return Acesso()

    quem_paga = pagador(s, company)
    if quem_paga is None:
        return Acesso()
    if quem_paga.id != company.id:
        # Empresa coberta pelo consultor: o estado dela segue o do pagador.
        if (quem_paga.status or Company.STATUS_ATIVO) != Company.STATUS_ATIVO:
            return Acesso(True, "suspenso", pagador_id=quem_paga.id, pagador_nome=quem_paga.nome)
        if quem_paga.billing_mode == Company.BILLING_ISENTO:
            return Acesso(pagador_id=quem_paga.id, pagador_nome=quem_paga.nome)

    limite = datetime.utcnow() - timedelta(days=GRACE_DAYS)
    vencida = (
        s.query(Charge)
        .filter(
            Charge.company_id == quem_paga.id,
            Charge.status.in_(Charge.ABERTOS),
            Charge.due_date < limite,
        )
        .order_by(Charge.due_date.asc())
        .first()
    )
    if vencida is not None:
        atraso = (datetime.utcnow() - vencida.due_date).days
        return Acesso(True, "inadimplente", atraso, quem_paga.id, quem_paga.nome)
    return Acesso(pagador_id=quem_paga.id, pagador_nome=quem_paga.nome)


def empresa_bloqueada(company_id: str | None) -> bool:
    """Usado pelo fluxo público `/nr1/{token}`: o colaborador não tem conta, então a
    checagem é direta pelo tenant da campanha."""
    if not company_id:
        return False
    with get_session() as s:
        company = s.get(Company, company_id)
        return acesso(s, company, auth.MEMBER).bloqueado


# ---------------------------------------------------------------------------
# Leitura para a tela de faturas
# ---------------------------------------------------------------------------
def faturas_do_tenant(company_id: str) -> dict:
    with get_session() as s:
        company = s.get(Company, company_id)
        if company is None:
            return {"pagas": [], "abertas": [], "coberto_por": None, "isento": False, "plano": None}

        quem_paga = pagador(s, company)
        coberto_por = quem_paga.nome if quem_paga and quem_paga.id != company.id else None
        plano = s.get(Plan, quem_paga.plan_id) if quem_paga and quem_paga.plan_id else None
        plano_ctx = (
            {"nome": plano.nome, "valor_centavos": plano.valor_centavos, "ciclo": plano.ciclo}
            if plano else None
        )
        isento = bool(quem_paga and quem_paga.billing_mode == Company.BILLING_ISENTO)

        rows = []
        if quem_paga is not None and not coberto_por:
            rows = (
                s.query(Charge)
                .filter(Charge.company_id == quem_paga.id, Charge.status != Charge.DELETED)
                .order_by(Charge.due_date.desc())
                .all()
            )
        hoje = datetime.utcnow()
        pagas, abertas = [], []
        for c in rows:
            item = {
                "id": c.id,
                "descricao": c.descricao,
                "valor_centavos": c.valor_centavos,
                "vencimento": c.due_date,
                "pagamento": c.payment_date,
                "status": c.status,
                "invoice_url": c.invoice_url,
                "vencida": c.em_aberto and c.due_date < hoje,
            }
            (pagas if c.pago else abertas).append(item)
    return {
        "pagas": pagas,
        "abertas": abertas,
        "coberto_por": coberto_por,
        "isento": isento,
        "plano": plano_ctx,
    }


def payment_link(charge_id: str, company_id: str) -> str | None:
    """URL de pagamento da fatura, com fallback no ASAAS se ela não foi salva."""
    with get_session() as s:
        company = s.get(Company, company_id)
        quem_paga = pagador(s, company)
        if quem_paga is None:
            return None
        charge = s.query(Charge).filter(Charge.id == charge_id, Charge.company_id == quem_paga.id).first()
        if charge is None or charge.pago:
            return None
        if charge.invoice_url:
            return charge.invoice_url
        payment_id = charge.asaas_payment_id

    try:
        fresco = asaas.get_payment(payment_id)
    except (asaas.AsaasErro, asaas.AsaasNaoConfigurado) as exc:
        log.warning("Sem link de pagamento para %s: %s", charge_id, exc)
        return None
    atualizada = upsert_charge(fresco)
    return atualizada.invoice_url if atualizada else None
