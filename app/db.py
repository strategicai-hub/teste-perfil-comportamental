from datetime import datetime
from sqlalchemy import create_engine, String, Integer, DateTime, ForeignKey, Text, Boolean
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
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    manager_email: Mapped[str] = mapped_column(String(200), default="", index=True)
    manager_password_hash: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    areas: Mapped[list["CompanyArea"]] = relationship(cascade="all, delete-orphan")


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    Base.metadata.create_all(engine)
    _migrate_users_columns()
    _migrate_leads_columns()
    seed_super_admin()
    migrate_company_managers()
    backfill_member_tenants()


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
    """
    import logging
    import uuid

    log = logging.getLogger(__name__)
    super_email = (settings.super_admin_email or "").strip().lower()
    with get_session() as s:
        companies = s.query(Company).all()
        for company in companies:
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
