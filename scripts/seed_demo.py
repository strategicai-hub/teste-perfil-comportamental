"""Gera 10 respondentes de demonstração do COPSOQ II para uma empresa.

As respostas são desenhadas para o resultado agregado cobrir os TRÊS status
(favorável, atenção e risco alto), em vez de ficar quase tudo em "Atenção".

Como funciona: para cada subescala definimos um alvo em escala de RISCO (0-100,
maior = pior, já normalizado pela direção). O alvo é convertido de volta para a
média Likert que o produziria — `media = score/25 + 1` — e cada item recebe esse
valor com um pequeno jitter determinístico (`random.Random(SEED)`), invertendo os
itens reversos para que o escoreamento real chegue no alvo.

Idempotente: apaga os dados de demonstração anteriores (e-mails `@demo.local`)
antes de recriar.

Uso:
    python -m scripts.seed_demo --empresa-slug <slug>
    python -m scripts.seed_demo --listar
"""

import argparse
import json
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.copsoq import scoring as copsoq_scoring  # noqa: E402
from app.copsoq.structure import SUBDIMENSIONS, SUBDIMENSIONS_CURTA  # noqa: E402
from app.db import (  # noqa: E402
    Answer,
    Campaign,
    CampaignInvite,
    Company,
    CompanyArea,
    Lead,
    User,
    get_session,
    init_db,
)
from app.tests_engine import VERSAO_PADRAO, copsoq_test_id  # noqa: E402

SEED = 42
EMAIL_DOMINIO = "demo.local"
# Domínios já usados por dados de demonstração — todos são limpos antes de recriar.
# `fake.local` é o legado da primeira leva de 10 respondentes.
DOMINIOS_DEMO = (EMAIL_DOMINIO, "fake.local")

# Alvo em escala de RISCO (0-100; maior = pior). O escoreamento reorienta pela
# direção da subescala, então isto vale igual para demandas e recursos.
ALVO_RISCO_ALTO = 80
ALVO_ATENCAO = 50
ALVO_FAVORAVEL = 16

# Dimensões que o agregado deve mostrar em RISCO ALTO (vermelho).
RISCO_ALTO = {
    "ritmo_trabalho",
    "exigencias_emocionais",
    "exigencias_quantitativas",
    "recompensas_reconhecimento",
    "confianca_vertical",
    "burnout",
    "problemas_sono",
}

# Dimensões que o agregado deve mostrar como FAVORÁVEL (verde).
FAVORAVEL = {
    "significado_trabalho",
    "apoio_colegas",
    "autoeficacia",
    "inclusao_social",
    "comportamentos_ofensivos",
    "variacao_trabalho",
    "clareza_papel",
    "saude_geral",
    "conflito_familia_trabalho",
}

# Áreas da demonstração: cada uma puxa o risco para cima ou para baixo, para o
# relatório por área ficar diferente do consolidado geral.
AREAS = [
    {"nome": "Operações", "offset": 10, "pessoas": 4},
    {"nome": "Comercial", "offset": 0, "pessoas": 3},
    {"nome": "Administrativo", "offset": -10, "pessoas": 3},
]

NOMES = [
    "Ana Ribeiro", "Bruno Carvalho", "Carla Menezes", "Diego Fontes", "Elisa Prado",
    "Felipe Barros", "Gabriela Nunes", "Henrique Dias", "Isabela Moraes", "João Vitor Salles",
]


def _alvo_base(key: str) -> int:
    if key in RISCO_ALTO:
        return ALVO_RISCO_ALTO
    if key in FAVORAVEL:
        return ALVO_FAVORAVEL
    return ALVO_ATENCAO


def _respostas_do_respondente(rnd: random.Random, offset: int, versao: str) -> dict[str, str]:
    """Monta as respostas da versão escolhida a partir dos alvos por subescala."""
    respostas: dict[str, str] = {}
    for sub in (SUBDIMENSIONS_CURTA if versao == "curta" else SUBDIMENSIONS):
        risco_alvo = max(4, min(96, _alvo_base(sub["key"]) + offset + rnd.randint(-6, 6)))
        # risco → escore da subescala (desfaz a reorientação por direção)
        score = risco_alvo if sub["direcao"] == "risco" else 100 - risco_alvo
        media = score / 25 + 1  # inverso de (media - 1) * 25

        for n in sub["items"]:
            valor = round(media + rnd.choice((-1, 0, 0, 0, 1)))
            valor = max(1, min(5, valor))
            # O escoreamento inverte os itens reversos; grava-se o valor "cru".
            if n in sub["reverse"]:
                valor = 6 - valor
            respostas[f"q{n}"] = str(valor)
    return respostas


def _e_demo(email: str | None) -> bool:
    return bool(email) and email.lower().endswith(tuple(f"@{d}" for d in DOMINIOS_DEMO))


def _limpar_demo(s, company_id: str) -> int:
    """Remove leads, respostas, usuários, convites e campanhas de demonstração anteriores."""
    leads = [
        l for l in s.query(Lead).filter(Lead.company_id == company_id).all()
        if _e_demo(l.email)
    ]
    user_ids = {l.user_id for l in leads if l.user_id}
    for lead in leads:
        s.query(Answer).filter(Answer.token == lead.token).delete(synchronize_session=False)
        s.delete(lead)

    # Usuários criados só para a demonstração (levas antigas os criavam de verdade).
    for user in s.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []:
        if _e_demo(user.email):
            s.delete(user)

    campanhas = (
        s.query(Campaign)
        .filter(Campaign.company_id == company_id, Campaign.titulo.like("%(demonstração)%"))
        .all()
    )
    for c in campanhas:
        s.query(CampaignInvite).filter(CampaignInvite.campaign_id == c.id).delete(synchronize_session=False)
        s.delete(c)

    s.commit()
    return len(leads)


def seed(slug: str, versao: str = VERSAO_PADRAO) -> None:
    init_db()
    rnd = random.Random(SEED)
    agora = datetime.utcnow()

    with get_session() as s:
        company = s.query(Company).filter(Company.slug == slug).first()
        if company is None:
            disponiveis = ", ".join(c.slug for c in s.query(Company).all()) or "(nenhuma)"
            raise SystemExit(f"Empresa '{slug}' não encontrada. Empresas: {disponiveis}")

        removidos = _limpar_demo(s, company.id)
        if removidos:
            print(f"Removidos {removidos} respondentes de demonstração anteriores.")

        existentes = {a.nome for a in s.query(CompanyArea).filter_by(company_id=company.id).all()}
        for area in AREAS:
            if area["nome"] not in existentes:
                s.add(CompanyArea(company_id=company.id, nome=area["nome"]))

        # Campanha de demonstração já encerrada — deixa o relatório liberado.
        campaign = Campaign(
            id=uuid.uuid4().hex,
            company_id=company.id,
            test_id=copsoq_test_id(versao),
            titulo="Avaliação NR-1 (demonstração)",
            inicio=agora - timedelta(days=20),
            fim=agora - timedelta(days=1),
        )
        s.add(campaign)
        s.commit()

        i = 0
        for area in AREAS:
            for _ in range(area["pessoas"]):
                nome = NOMES[i]
                primeiro = nome.split()[0].lower()
                email = f"{primeiro}.{i + 1}@{EMAIL_DOMINIO}"
                respostas = _respostas_do_respondente(rnd, area["offset"], versao)
                concluido = agora - timedelta(days=rnd.randint(2, 15))

                lead = Lead(
                    token=uuid.uuid4().hex,
                    user_id=None,
                    test_id=copsoq_test_id(versao),
                    nome=nome.split()[0],
                    sobrenome=" ".join(nome.split()[1:]),
                    whatsapp="",
                    email=email,
                    company_id=company.id,
                    area=area["nome"],
                    campaign_id=campaign.id,
                    created_at=concluido - timedelta(minutes=20),
                    concluido_em=concluido,
                    result_json=json.dumps(
                        copsoq_scoring.calculate(respostas, versao=versao), ensure_ascii=False
                    ),
                )
                s.add(lead)
                for qid, valor in respostas.items():
                    s.add(Answer(token=lead.token, question_id=qid, value=valor))
                s.add(CampaignInvite(
                    campaign_id=campaign.id,
                    token=uuid.uuid4().hex,
                    nome=nome,
                    email=email,
                    area=area["nome"],
                    enviado_em=campaign.inicio,
                    respondido_em=concluido,
                    lead_token=lead.token,
                ))
                i += 1
        s.commit()
        company_id = company.id
        company_nome = company.nome

    _relatar(company_id, company_nome)


def _relatar(company_id: str, company_nome: str) -> None:
    """Confere que o agregado realmente cobre os três status."""
    with get_session() as s:
        leads = [
            l for l in s.query(Lead).filter(Lead.company_id == company_id).all()
            if _e_demo(l.email)
        ]
        resultados = [json.loads(l.result_json) for l in leads if l.result_json]

    agg = copsoq_scoring.aggregate(resultados)
    por_nivel = {"verde": [], "amarelo": [], "vermelho": []}
    for sub in agg["subscales"]:
        if sub["nivel"]:
            por_nivel[sub["nivel"]].append(f"{sub['nome']} ({sub['score']})")

    print(f"\n{len(resultados)} respondentes criados em {company_nome}.\n")
    for nivel, rotulo in (("verde", "FAVORÁVEL"), ("amarelo", "ATENÇÃO"), ("vermelho", "RISCO ALTO")):
        print(f"{rotulo} — {len(por_nivel[nivel])} dimensões")
        for item in por_nivel[nivel]:
            print(f"  · {item}")
        print()

    faltando = [n for n, itens in por_nivel.items() if not itens]
    if faltando:
        print(f"ATENÇÃO: nenhum indicador nas faixas {faltando}. Ajuste os alvos no script.")
    else:
        print("OK — as três faixas estão representadas.")


def listar() -> None:
    init_db()
    with get_session() as s:
        for c in s.query(Company).order_by(Company.nome).all():
            print(f"{c.slug}\t{c.nome}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Respondentes de demonstração do COPSOQ II")
    parser.add_argument("--empresa-slug", help="slug da empresa que vai receber os dados")
    parser.add_argument("--listar", action="store_true", help="lista as empresas cadastradas e sai")
    parser.add_argument(
        "--versao", choices=("curta", "longa"), default=VERSAO_PADRAO,
        help="versao do questionario aplicada na campanha de demonstracao (padrao: curta)",
    )
    args = parser.parse_args()

    if args.listar:
        listar()
        return
    if not args.empresa_slug:
        parser.error("informe --empresa-slug (ou use --listar para ver as opções)")
    seed(args.empresa_slug.lower().strip(), args.versao)


if __name__ == "__main__":
    main()
