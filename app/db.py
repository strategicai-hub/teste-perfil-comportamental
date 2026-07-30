from datetime import datetime
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    nome: Mapped[str] = mapped_column(String(120))
    sobrenome: Mapped[str] = mapped_column(String(120))
    whatsapp: Mapped[str] = mapped_column(String(40))
    profissao: Mapped[str] = mapped_column(String(200), default="")
    origem: Mapped[str] = mapped_column(String(200), default="")
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    # Multi-tenant: papel do usuário e empresa (tenant) à qual pertence.
    # super_admin tem tenant_id NULL (não pertence a nenhum tenant).
    role: Mapped[str] = mapped_column(String(16), default="member", index=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Company(Base):
    """Tenant do sistema — pode ser uma **empresa** (cliente final) ou uma **consultoria**.

    A consultoria é um tenant como qualquer outro: os usuários dela têm
    `User.tenant_id` apontando para cá com `role='consultant'`, e as empresas que ela
    trouxe têm `parent_id` preenchido. Modelar assim (em vez de um FK para um User)
    é o que permite cobrar consultoria e empresa pelo mesmo caminho (`Charge.company_id`)
    e reaproveitar a impersonation existente.
    """

    __tablename__ = "companies"

    KIND_EMPRESA = "empresa"
    KIND_CONSULTORIA = "consultoria"

    STATUS_PENDENTE = "pending"
    STATUS_ATIVO = "ativo"
    STATUS_RECUSADO = "recusado"
    STATUS_SUSPENSO = "suspenso"

    # Quem paga a conta deste tenant.
    BILLING_PROPRIO = "proprio"          # assinatura própria no ASAAS
    BILLING_CONSULTOR = "pelo_consultor"  # coberto pela assinatura da consultoria dona
    BILLING_ISENTO = "isento"             # liberado sem cobrança (nunca bloqueia)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    manager_email: Mapped[str] = mapped_column(String(200), default="", index=True)
    manager_password_hash: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    kind: Mapped[str] = mapped_column(String(16), default=KIND_EMPRESA, index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_PENDENTE, index=True)
    cpf_cnpj: Mapped[str] = mapped_column(String(20), default="")
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    billing_mode: Mapped[str] = mapped_column(String(20), default=BILLING_PROPRIO)
    asaas_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    asaas_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    asaas_erro: Mapped[str | None] = mapped_column(String(300), nullable=True)
    signup_ip: Mapped[str] = mapped_column(String(64), default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    areas: Mapped[list["CompanyArea"]] = relationship(cascade="all, delete-orphan")

    @property
    def e_consultoria(self) -> bool:
        return self.kind == self.KIND_CONSULTORIA

    @property
    def ativo(self) -> bool:
        return (self.status or self.STATUS_ATIVO) == self.STATUS_ATIVO


class CompanyArea(Base):
    __tablename__ = "company_areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    nome: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Campaign(Base):
    """Ciclo de avaliação NR-1 de uma empresa.

    O gestor sobe a planilha de colaboradores e define a data de fim; `inicio` é
    carimbado automaticamente no envio dos convites. Não há job de encerramento:
    a campanha está aberta enquanto `datetime.utcnow() < fim` (ver `esta_aberta`).
    """

    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    test_id: Mapped[int] = mapped_column(Integer, default=11)
    titulo: Mapped[str] = mapped_column(String(200), default="")
    inicio: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fim: Mapped[datetime] = mapped_column(DateTime)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    invites: Mapped[list["CampaignInvite"]] = relationship(cascade="all, delete-orphan")

    @property
    def esta_aberta(self) -> bool:
        return datetime.utcnow() < self.fim


class CampaignInvite(Base):
    """Convite individual: o `token` é o link único que o colaborador recebe."""

    __tablename__ = "campaign_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(200), index=True)
    area: Mapped[str] = mapped_column(String(160), default="")
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    erro_envio: Mapped[str | None] = mapped_column(String(300), nullable=True)
    respondido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lead_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Último reengajamento enviado. Fica separado de `enviado_em` porque este é a prova
    # de que a pessoa recebeu o link — base do percentual de adesão. Zerar `enviado_em`
    # para reenviar (como era antes) apagava exatamente esse dado.
    reengajado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def recebeu(self) -> bool:
        return self.enviado_em is not None and not self.erro_envio


class Lead(Base):
    __tablename__ = "leads"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    test_id: Mapped[int] = mapped_column(Integer, default=1, index=True)
    nome: Mapped[str] = mapped_column(String(120))
    sobrenome: Mapped[str] = mapped_column(String(120))
    whatsapp: Mapped[str] = mapped_column(String(40))
    email: Mapped[str] = mapped_column(String(200), index=True)
    profissao: Mapped[str] = mapped_column(String(200), default="")
    origem: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    perc_tubarao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    perc_lobo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    perc_aguia: Mapped[int | None] = mapped_column(Integer, nullable=True)
    perc_gato: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Resultado genérico de qualquer teste (JSON serializado). COPSOQ usa só isto.
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Contexto organizacional (testes de empresa, ex.: COPSOQ).
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    area: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Campanha NR-1 de origem. Preenchido quando a resposta vem de um convite por
    # e-mail (nesse caso `user_id` fica NULL — o respondente não tem conta).
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)

    answers: Mapped[list["Answer"]] = relationship(cascade="all, delete-orphan")
    messages: Mapped[list["ChatMessage"]] = relationship(cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(ForeignKey("leads.token"), index=True)
    question_id: Mapped[str] = mapped_column(String(8))
    value: Mapped[str] = mapped_column(String(16))


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(ForeignKey("leads.token"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Plan(Base):
    """Plano de assinatura, editável no painel do super admin (sem deploy)."""

    __tablename__ = "plans"

    TIPO_EMPRESA = "empresa"
    TIPO_CONSULTORIA = "consultoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(120))
    # Dinheiro sempre em centavos: Float em SQLite arredonda e vira diferença de caixa.
    valor_centavos: Mapped[int] = mapped_column(Integer, default=0)
    ciclo: Mapped[str] = mapped_column(String(16), default="MONTHLY")
    tipo: Mapped[str] = mapped_column(String(16), default=TIPO_EMPRESA, index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Charge(Base):
    """Cobrança espelhada do ASAAS. `company_id` é sempre o **pagador**."""

    __tablename__ = "charges"

    PENDING = "PENDING"
    RECEIVED = "RECEIVED"
    CONFIRMED = "CONFIRMED"
    OVERDUE = "OVERDUE"
    REFUNDED = "REFUNDED"
    DELETED = "DELETED"

    ABERTOS = (PENDING, OVERDUE)
    PAGOS = (RECEIVED, CONFIRMED)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asaas_payment_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    descricao: Mapped[str] = mapped_column(String(200), default="")
    valor_centavos: Mapped[int] = mapped_column(Integer, default=0)
    net_centavos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    payment_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=PENDING, index=True)
    billing_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    invoice_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    bank_slip_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_charges_company_status", "company_id", "status"),
        Index("ix_charges_company_due", "company_id", "due_date"),
    )

    @property
    def em_aberto(self) -> bool:
        return self.status in self.ABERTOS

    @property
    def pago(self) -> bool:
        return self.status in self.PAGOS


class WebhookEvent(Base):
    """Log de eventos recebidos. A unique tripla é o que garante idempotência:
    o ASAAS reentregar o mesmo evento não pode gerar cobrança duplicada."""

    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(20), default="asaas")
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("provider", "external_id", "event_type", name="uq_webhook_event"),
    )


class AppSetting(Base):
    """Config de runtime (token/ambiente do ASAAS). Vence o `.env` para permitir
    trocar de conta ou de sandbox↔produção sem redeploy."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    Base.metadata.create_all(engine)
    _migrate_users_columns()
    _migrate_leads_columns()
    _migrate_companies_columns()
    _migrate_campaign_invites_columns()
    seed_super_admin()
    migrate_company_managers()
    backfill_member_tenants()
    seed_planos_padrao()


def _migrate_users_columns():
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as conn:
        if "role" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(16) DEFAULT 'member'"))
            conn.execute(text("UPDATE users SET role='member' WHERE role IS NULL"))
        if "tenant_id" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN tenant_id VARCHAR(64)"))


def _migrate_leads_columns():
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "leads" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("leads")}
    with engine.begin() as conn:
        if "user_id" not in cols:
            conn.execute(text("ALTER TABLE leads ADD COLUMN user_id VARCHAR(64)"))
        if "test_id" not in cols:
            conn.execute(text("ALTER TABLE leads ADD COLUMN test_id INTEGER DEFAULT 1"))
        if "result_json" not in cols:
            conn.execute(text("ALTER TABLE leads ADD COLUMN result_json TEXT"))
        if "company_id" not in cols:
            conn.execute(text("ALTER TABLE leads ADD COLUMN company_id VARCHAR(64)"))
        if "area" not in cols:
            conn.execute(text("ALTER TABLE leads ADD COLUMN area VARCHAR(160)"))
        if "campaign_id" not in cols:
            conn.execute(text("ALTER TABLE leads ADD COLUMN campaign_id VARCHAR(64)"))


def _migrate_companies_columns():
    """Colunas de hierarquia e cobrança em `companies`.

    O backfill é parte inseparável da migração: o default do model é
    `status='pending'`, então sem o UPDATE toda empresa que já existe cairia em
    "cadastro em análise" no primeiro boot. Idem `billing_mode='isento'` — cliente
    antigo não passa a ser cobrado (nem bloqueado) por efeito colateral do deploy.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "companies" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("companies")}
    novas = {
        "kind": "VARCHAR(16)",
        "parent_id": "VARCHAR(64)",
        "status": "VARCHAR(16)",
        "cpf_cnpj": "VARCHAR(20)",
        "plan_id": "INTEGER",
        "billing_mode": "VARCHAR(20)",
        "asaas_customer_id": "VARCHAR(64)",
        "asaas_subscription_id": "VARCHAR(64)",
        "asaas_erro": "VARCHAR(300)",
        "signup_ip": "VARCHAR(64)",
        "approved_at": "DATETIME",
        "approved_by": "VARCHAR(64)",
    }
    with engine.begin() as conn:
        for nome, tipo in novas.items():
            if nome not in cols:
                # SQLite não aceita UNIQUE nem default não-constante em ADD COLUMN.
                conn.execute(text(f"ALTER TABLE companies ADD COLUMN {nome} {tipo}"))
        conn.execute(text("UPDATE companies SET kind='empresa' WHERE kind IS NULL OR kind=''"))
        conn.execute(text("UPDATE companies SET status='ativo' WHERE status IS NULL OR status=''"))
        conn.execute(text("UPDATE companies SET cpf_cnpj='' WHERE cpf_cnpj IS NULL"))
        conn.execute(text("UPDATE companies SET signup_ip='' WHERE signup_ip IS NULL"))
        conn.execute(
            text("UPDATE companies SET billing_mode='isento' WHERE billing_mode IS NULL OR billing_mode=''")
        )


def _migrate_campaign_invites_columns():
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "campaign_invites" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("campaign_invites")}
    with engine.begin() as conn:
        if "reengajado_em" not in cols:
            conn.execute(text("ALTER TABLE campaign_invites ADD COLUMN reengajado_em DATETIME"))


def seed_planos_padrao():
    """Cria planos iniciais só se a tabela estiver vazia (o owner edita depois no painel)."""
    with get_session() as s:
        if s.query(Plan).count() > 0:
            return
        s.add_all([
            Plan(nome="NR-1 Essencial", valor_centavos=19700, tipo=Plan.TIPO_EMPRESA, ordem=1),
            Plan(nome="NR-1 Pro", valor_centavos=39700, tipo=Plan.TIPO_EMPRESA, ordem=2),
            Plan(nome="Consultoria", valor_centavos=59700, tipo=Plan.TIPO_CONSULTORIA, ordem=1),
        ])
        try:
            s.commit()
        except IntegrityError:
            s.rollback()


def seed_super_admin():
    """Cria/atualiza o super admin a partir do env (fonte de verdade da senha).

    Idempotente: promove um User existente com o e-mail configurado, ou cria um
    novo. Sincroniza o hash da senha a cada boot. Roda só se houver e-mail e senha.
    """
    import logging
    import uuid

    from . import auth

    email = (settings.super_admin_email or "").strip().lower()
    password = settings.super_admin_password or settings.admin_pass or ""
    if not email or not password:
        return

    log = logging.getLogger(__name__)
    with get_session() as s:
        try:
            user = s.query(User).filter(User.email == email).first()
            pw_hash = auth.hash_password(password)
            if user is None:
                user = User(
                    id=uuid.uuid4().hex,
                    email=email,
                    password_hash=pw_hash,
                    nome="Strategic AI",
                    sobrenome="Admin",
                    whatsapp="",
                    role="super_admin",
                    tenant_id=None,
                    blocked=False,
                )
                s.add(user)
            else:
                user.role = "super_admin"
                user.tenant_id = None
                user.blocked = False
                user.password_hash = pw_hash
            s.commit()
        except IntegrityError:
            s.rollback()
            log.warning("seed_super_admin: colisão ao criar/atualizar %s", email)


def migrate_company_managers():
    """Converte cada Company.manager_email em um User role=admin do tenant.

    Idempotente e defensivo contra colisões de e-mail (unique global):
    - e-mail reservado do super admin → não rebaixa, pula;
    - User comum sem tenant → promove a admin do tenant (mantém a senha própria);
    - User já em OUTRO tenant → conflito (1 e-mail = 1 tenant), pula e loga;
    - não existe → cria admin reaproveitando o bcrypt de manager_password_hash.

    NÃO toca em tenant fora do status 'ativo': um cadastro público ainda em análise
    não pode ganhar gestor liberado, e esta função reescreve `password_hash` — o que
    sobrescreveria a senha que a pessoa acabou de escolher no wizard.
    """
    import logging
    import uuid

    log = logging.getLogger(__name__)
    super_email = (settings.super_admin_email or "").strip().lower()
    with get_session() as s:
        companies = s.query(Company).all()
        for company in companies:
            if (company.status or Company.STATUS_ATIVO) != Company.STATUS_ATIVO:
                continue
            email = (company.manager_email or "").strip().lower()
            if not email:
                continue
            try:
                user = s.query(User).filter(User.email == email).first()
                if user is None:
                    user = User(
                        id=uuid.uuid4().hex,
                        email=email,
                        password_hash=company.manager_password_hash or "",
                        nome=company.nome or "Gestor",
                        sobrenome="",
                        whatsapp="",
                        role="admin",
                        tenant_id=company.id,
                        blocked=False,
                    )
                    s.add(user)
                    s.commit()
                    continue
                if email == super_email:
                    log.warning("migrate_company_managers: %s é super admin; empresa %s sem gestor", email, company.slug)
                    continue
                if user.role == "super_admin":
                    log.warning("migrate_company_managers: %s é super_admin; pulando empresa %s", email, company.slug)
                    continue
                if user.tenant_id and user.tenant_id != company.id:
                    log.warning(
                        "migrate_company_managers: %s já é de outro tenant; empresa %s precisa de outro e-mail",
                        email, company.slug,
                    )
                    continue
                # User comum sem tenant (ou já deste tenant) → promove a admin.
                user.role = "admin"
                user.tenant_id = company.id
                s.commit()
            except IntegrityError:
                s.rollback()
                log.warning("migrate_company_managers: colisão em %s (empresa %s)", email, company.slug)


def backfill_member_tenants():
    """Vincula members sem tenant à empresa dos próprios leads (dado já registrado).

    Colaboradores legados (cadastro antigo) ficaram com tenant_id NULL, mas seus
    Leads já carregam company_id. Usar essa associação existente evita deixá-los
    travados (não é adivinhação — é o vínculo que eles mesmos criaram ao responder).
    Idempotente: só toca em quem está sem tenant.
    """
    import logging

    log = logging.getLogger(__name__)
    with get_session() as s:
        members = (
            s.query(User)
            .filter(User.role == "member", User.tenant_id.is_(None))
            .all()
        )
        for u in members:
            lead = (
                s.query(Lead)
                .filter(Lead.user_id == u.id, Lead.company_id.isnot(None))
                .order_by(Lead.created_at.desc())
                .first()
            )
            if lead is None:
                continue
            if s.get(Company, lead.company_id) is not None:
                u.tenant_id = lead.company_id
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            log.warning("backfill_member_tenants: falha ao commitar")


def get_session():
    return SessionLocal()
