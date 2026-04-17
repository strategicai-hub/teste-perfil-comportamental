from datetime import datetime
from sqlalchemy import create_engine, String, Integer, DateTime, ForeignKey, Text, Boolean
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
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
    _migrate_leads_columns()


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


def get_session():
    return SessionLocal()
