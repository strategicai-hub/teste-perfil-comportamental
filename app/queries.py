"""Leituras compartilhadas entre `main.py` e os routers.

Extraído de `main.py` sem mudança de comportamento — ver `app/web/deps.py` para o
motivo (routers não podem importar de `main`).
"""

import json

from . import auth
from .copsoq import report as copsoq_report, scoring as copsoq_scoring
from .db import Campaign, CampaignInvite, Company, CompanyArea, Lead, User, get_session
from .tests_engine import COPSOQ_TEST_ID, COPSOQ_TEST_IDS
from .web.deps import MIN_RESPONDENTES, fmt_data


def lead_result(lead: Lead) -> dict | None:
    """Resultado canônico (result_json) de um lead concluído; fallback nas colunas legadas."""
    if lead.concluido_em is None:
        return None
    if lead.result_json:
        try:
            return json.loads(lead.result_json)
        except (ValueError, TypeError):
            pass
    return {
        "type": "archetype",
        "perc": {
            "tubarao": lead.perc_tubarao or 0,
            "lobo": lead.perc_lobo or 0,
            "aguia": lead.perc_aguia or 0,
            "gato": lead.perc_gato or 0,
        },
    }


def gestor_ids(s, company_id: str) -> set[str]:
    """IDs de quem NÃO entra no agregado: gestores e super admins do tenant.

    A resposta do gestor não pode distorcer as médias nem quebrar o anonimato do
    grupo. Filtrar por exclusão (em vez de exigir `role == member`) é o que permite
    contar também os respondentes anônimos vindos de convite, que não têm conta.
    """
    return {
        u.id for u in s.query(User).filter(User.tenant_id == company_id, User.role != auth.MEMBER).all()
    }


def copsoq_leads(s, company_id: str, area: str | None = None, campaign_id: str | None = None):
    """Leads COPSOQ concluídos que entram no resultado do recorte."""
    q = s.query(Lead).filter(
        Lead.company_id == company_id,
        Lead.test_id.in_(COPSOQ_TEST_IDS),
        Lead.concluido_em.isnot(None),
    )
    if campaign_id:
        q = q.filter(Lead.campaign_id == campaign_id)
    if area:
        q = q.filter(Lead.area == area)
    excluir = gestor_ids(s, company_id)
    return [lead for lead in q.all() if lead.user_id not in excluir]


def copsoq_agg_for(company_id: str, area: str | None, campaign_id: str | None = None) -> dict:
    with get_session() as s:
        results = []
        for lead in copsoq_leads(s, company_id, area, campaign_id):
            r = lead_result(lead)
            if r and r.get("type") == "copsoq":
                results.append(r)
    return copsoq_scoring.aggregate(results)


def company_areas_com_contagem(company_id: str, campaign_id: str | None = None) -> list[dict]:
    with get_session() as s:
        areas = s.query(CompanyArea).filter_by(company_id=company_id).order_by(CompanyArea.nome.asc()).all()
        leads = copsoq_leads(s, company_id, campaign_id=campaign_id)
        contagem: dict[str, int] = {}
        for lead in leads:
            if lead.area:
                contagem[lead.area] = contagem.get(lead.area, 0) + 1
        rows = [{"id": a.id, "nome": a.nome, "respondentes": contagem.get(a.nome, 0)} for a in areas]
    return rows


def campanha_atual(s, company_id: str) -> Campaign | None:
    """Campanha mais recente da empresa (aberta ou já encerrada)."""
    return (
        s.query(Campaign)
        .filter(Campaign.company_id == company_id)
        .order_by(Campaign.created_at.desc())
        .first()
    )


def campanha_ctx(campaign: Campaign | None, invites_rows: list[CampaignInvite] | None = None) -> dict | None:
    if campaign is None:
        return None
    rows = invites_rows or []
    responderam = sum(1 for i in rows if i.respondido_em)
    # "Recebeu" = e-mail saiu sem erro. É a base honesta do percentual de adesão:
    # cobrar resposta de quem nunca recebeu o link não mede nada.
    recebidos = sum(1 for i in rows if i.recebeu)
    base = recebidos or len(rows)
    return {
        "id": campaign.id,
        "titulo": campaign.titulo,
        "inicio": fmt_data(campaign.inicio),
        "fim": fmt_data(campaign.fim),
        "aberta": campaign.esta_aberta,
        "total": len(rows),
        "responderam": responderam,
        "pendentes": len(rows) - responderam,
        "falhas": sum(1 for i in rows if i.erro_envio),
        "recebidos": recebidos,
        "perc": round(responderam * 100 / base) if base else 0,
        # Versão aplicada nesta campanha (a curta é o padrão; a longa, sob demanda).
        "versao": "longa" if campaign.test_id == COPSOQ_TEST_ID else "curta",
        "total_perguntas": 119 if campaign.test_id == COPSOQ_TEST_ID else 41,
        "nao_responderam": max(recebidos - responderam, 0),
    }


def secoes_relatorio(company_id: str, escopo: str | None = None) -> list[dict]:
    """Seções do relatório: consolidado geral + uma por área com respondentes suficientes.

    Com `escopo` preenchido devolve só aquele recorte (é o que o chip da aba Relatório
    usa); sem escopo devolve tudo, que é o formato do PDF.
    """
    def secao(titulo: str, nome_escopo: str, area: str | None) -> dict:
        agg = copsoq_agg_for(company_id, area)
        return {
            "titulo": titulo,
            "escopo": nome_escopo,
            "agg": agg,
            "resumo": copsoq_report.resumo(agg),
            "gargalos": copsoq_report.top_gargalos(agg),
            "blocos": copsoq_report.build_report(agg),
        }

    areas = company_areas_com_contagem(company_id)
    if escopo:
        alvo = next((a for a in areas if a["nome"] == escopo), None)
        if alvo is None or alvo["respondentes"] < MIN_RESPONDENTES:
            return []
        return [secao(f"Área: {escopo}", escopo, escopo)]

    secoes = [secao("Consolidado geral da empresa", "geral", None)]
    for a in areas:
        if a["respondentes"] < MIN_RESPONDENTES:
            continue
        secoes.append(secao(f"Área: {a['nome']}", a["nome"], a["nome"]))
    return secoes


def empresas_do_consultor(consultoria_id: str) -> list[dict]:
    """Empresas trazidas por uma consultoria, com contagem de respostas e pendência."""
    with get_session() as s:
        rows = (
            s.query(Company)
            .filter(Company.parent_id == consultoria_id, Company.kind == Company.KIND_EMPRESA)
            .order_by(Company.created_at.desc())
            .all()
        )
        saida = []
        for c in rows:
            campaign = campanha_atual(s, c.id)
            invites = (
                s.query(CampaignInvite).filter(CampaignInvite.campaign_id == campaign.id).all()
                if campaign else []
            )
            saida.append({
                "id": c.id,
                "nome": c.nome,
                "slug": c.slug,
                "status": c.status,
                "pendente": c.status == Company.STATUS_PENDENTE,
                "manager_email": c.manager_email,
                "criado_em": fmt_data(c.created_at),
                "campanha": campanha_ctx(campaign, invites),
            })
    return saida
