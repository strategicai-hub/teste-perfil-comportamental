from datetime import datetime
from sqlalchemy import create_engine, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


class Lead(Base):
    __tablename__ = "leads"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
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


def get_session():
    return SessionLocal()
