"""Montagem do relatório NR-1 — 100% determinística, sem LLM.

O texto de cada indicador vem pronto de `knowledge.KNOWLEDGE`, indexado por
(subescala, faixa do semáforo). Este módulo só cruza o resultado agregado de
`scoring.aggregate()` com essa base e organiza a saída nos 8 itens macro.

Funções puras e testáveis:

- `build_report(agg)`     — o relatório exibido na tela e no PDF;
- `top_gargalos(agg)`     — as 3 maiores vulnerabilidades (resumo de abertura);
- `correlacoes(agg)`      — análise cruzada da §5 da base. NÃO é renderizado hoje;
                            fica pronto para a FASE 2 (plano de ação);
- `build_action_plan(agg)`— registros 5W2H. FASE 2, sem tela ainda.
"""

from . import knowledge
from .structure import DOMAINS, SUBDIMENSIONS

# Ordem de gravidade das faixas (para "pior faixa do bloco").
_SEVERIDADE = {"verde": 0, "amarelo": 1, "vermelho": 2}

NIVEL_LABEL = {"verde": "Favorável", "amarelo": "Atenção", "vermelho": "Risco alto"}

# Paleta oficial do produto (Especificacao-Tecnica-SaaS-COPSOQ.md §8).
NIVEL_COR = {"verde": "#1f9d57", "amarelo": "#c9860f", "vermelho": "#d23b3f"}

_SUB_BY_KEY = {s["key"]: s for s in SUBDIMENSIONS}


def _pior_nivel(niveis: list[str]) -> str | None:
    validos = [n for n in niveis if n in _SEVERIDADE]
    if not validos:
        return None
    return max(validos, key=lambda n: _SEVERIDADE[n])


def build_report(agg: dict) -> list[dict]:
    """Relatório por item macro.

    Cada bloco traz número, nome, faixa (pior entre suas dimensões) e a lista de
    indicadores com escore, definição e o texto de status. Não há devolutiva no
    nível do bloco — o cabeçalho vai direto para os indicadores.
    """
    subs = {s["key"]: s for s in agg.get("subscales", [])}
    blocos: list[dict] = []

    for i, dom in enumerate(DOMAINS, start=1):
        indicadores = []
        for sub in SUBDIMENSIONS:
            if sub["dominio"] != dom["key"]:
                continue
            s = subs.get(sub["key"]) or {}
            if s.get("score") is None:
                continue
            base = knowledge.get(sub["key"])
            nivel = s.get("nivel")
            indicadores.append({
                "key": sub["key"],
                "nome": sub["nome"],
                "direcao": sub["direcao"],
                "direcao_label": knowledge.DIRECAO_LABEL.get(sub["direcao"], ""),
                "escore": s.get("score"),
                "risco_score": s.get("risco_score"),
                "nivel": nivel,
                "nivel_label": NIVEL_LABEL.get(nivel, "—"),
                "status_label": knowledge.STATUS_LABEL.get(nivel, ""),
                "definicao": base.get("definicao", ""),
                "texto": knowledge.texto_status(sub["key"], nivel),
                "n": s.get("n"),
            })

        if not indicadores:
            continue

        nivel_bloco = _pior_nivel([ind["nivel"] for ind in indicadores])
        blocos.append({
            "numero": i,
            "key": dom["key"],
            "nome": dom["nome"],
            "nivel": nivel_bloco,
            "nivel_label": NIVEL_LABEL.get(nivel_bloco, "—"),
            "indicadores": indicadores,
            # Mesma lista, do mais grave para o menos grave — usada nos chips da tela.
            "indicadores_por_risco": sorted(
                indicadores,
                key=lambda ind: (
                    ind["risco_score"] is None,
                    -(ind["risco_score"] or 0),
                ),
            ),
        })

    return blocos


def top_gargalos(agg: dict, limite: int = 3) -> list[dict]:
    """As maiores vulnerabilidades: demandas altas ou recursos baixos.

    Implementa o passo 1 da diretriz de geração de relatório da base de conhecimento.
    """
    candidatos = [
        s for s in agg.get("subscales", [])
        if s.get("risco_score") is not None and s.get("nivel") in ("amarelo", "vermelho")
    ]
    candidatos.sort(key=lambda s: s["risco_score"], reverse=True)
    return [
        {
            "key": s["key"],
            "nome": s["nome"],
            "escore": s.get("score"),
            "risco_score": s["risco_score"],
            "nivel": s["nivel"],
            "nivel_label": NIVEL_LABEL.get(s["nivel"], "—"),
        }
        for s in candidatos[:limite]
    ]


def resumo(agg: dict) -> dict:
    """Contagem de indicadores por faixa — cabeçalho do relatório."""
    contagem = {"verde": 0, "amarelo": 0, "vermelho": 0}
    for s in agg.get("subscales", []):
        if s.get("nivel") in contagem:
            contagem[s["nivel"]] += 1
    total = sum(contagem.values())
    nivel_geral = "vermelho" if contagem["vermelho"] else ("amarelo" if contagem["amarelo"] else "verde")
    return {
        "respondentes": agg.get("respondentes", 0),
        "avaliados": total,
        "favoravel": contagem["verde"],
        "atencao": contagem["amarelo"],
        "risco_alto": contagem["vermelho"],
        "nivel_geral": nivel_geral if total else None,
        "nivel_geral_label": NIVEL_LABEL.get(nivel_geral) if total else "—",
    }


# =========================================================================
# FASE 2 — plano de ação. Prontos e testáveis, ainda sem tela.
# =========================================================================

# Regras de análise cruzada da §5 da base de conhecimento: quando a área de
# consequências (saúde) está ruim, a causa se busca nas áreas de origem.
_CORRELACOES = [
    {
        "efeito": "saude_bem_estar",
        "causas": ["exigencias_laborais", "relacoes_sociais_lideranca"],
        "texto": (
            "Os indicadores de saúde e bem-estar estão comprometidos. Pelo modelo "
            "demanda-controle-apoio, a causa costuma estar nas exigências laborais ou nas "
            "relações sociais e liderança — priorize a investigação nesses blocos."
        ),
    },
    {
        "efeito": "organizacao_conteudo",
        "causas": ["interface_trabalho_individuo"],
        "texto": (
            "A organização e o conteúdo do trabalho estão fragilizados, o que costuma se "
            "refletir diretamente na satisfação com o trabalho."
        ),
    },
]


def correlacoes(agg: dict) -> list[dict]:
    """Análise cruzada causa/efeito entre itens macro (FASE 2 — não renderizado hoje)."""
    doms = {d["key"]: d for d in agg.get("domains", [])}
    achados = []
    for regra in _CORRELACOES:
        efeito = doms.get(regra["efeito"])
        if not efeito or efeito.get("nivel") not in ("amarelo", "vermelho"):
            continue
        causas = [
            doms[c] for c in regra["causas"]
            if doms.get(c) and doms[c].get("nivel") in ("amarelo", "vermelho")
        ]
        if not causas:
            continue
        achados.append({
            "efeito": efeito["nome"],
            "causas": [c["nome"] for c in causas],
            "texto": regra["texto"],
        })
    return achados


# Complementos 5W2H por dimensão (copsoq-config.json → bibliotecaAcoes). Quando a
# dimensão não está mapeada, cai no _DEFAULT e usa `knowledge[...]["acao"]` como medida.
_BIBLIOTECA: dict[str, dict] = {
    "ritmo_trabalho": {
        "tipo": "Controle administrativo (fonte)", "nivel": "Primário",
        "responsavel": "Gestão + RH", "prazo_dias": 90,
        "indicador": "Índice de carga percebida; horas extras por setor",
    },
    "exigencias_emocionais": {
        "tipo": "Treinamento + apoio", "nivel": "Secundário",
        "responsavel": "RH + SESMT", "prazo_dias": 150,
        "indicador": "Adesão ao canal de apoio; escore na reaplicação",
    },
    "conflito_familia_trabalho": {
        "tipo": "Controle administrativo", "nivel": "Primário",
        "responsavel": "Gestão + Diretoria", "prazo_dias": 120,
        "indicador": "Acionamentos fora do horário; escore de conflito",
    },
    "conflitos_papel": {
        "tipo": "Eliminação na fonte", "nivel": "Primário",
        "responsavel": "Gestão + RH", "prazo_dias": 60,
        "indicador": "Nº de retrabalhos; clareza de papel na reaplicação",
    },
    "confianca_vertical": {
        "tipo": "Treinamento + processo", "nivel": "Secundário",
        "responsavel": "Diretoria + RH", "prazo_dias": 180,
        "indicador": "Pulso de clima trimestral; escore de confiança",
    },
    "burnout": {
        "tipo": "Monitoramento (efeito)", "nivel": "Terciário",
        "responsavel": "SESMT + RH", "prazo_dias": 180,
        "indicador": "Afastamentos CID F; absenteísmo; escores de saúde",
    },
}

_DEFAULT_ACAO = {
    "tipo": "A definir", "nivel": "A definir",
    "responsavel": "RH", "prazo_dias": 120,
    "indicador": "Escore da dimensão na reaplicação",
}


def build_action_plan(agg: dict) -> list[dict]:
    """Registros 5W2H para as dimensões em atenção/risco (FASE 2 — sem tela ainda).

    Ordenados por pressão de risco, como manda a especificação: cada registro já
    nasce com medida, tipo, nível de intervenção, responsável, prazo e indicador.
    """
    doms = {d["key"]: d["nome"] for d in DOMAINS}
    priorizadas = [
        s for s in agg.get("subscales", [])
        if s.get("risco_score") is not None and s.get("nivel") in ("amarelo", "vermelho")
    ]
    priorizadas.sort(key=lambda s: s["risco_score"], reverse=True)

    registros = []
    for ordem, s in enumerate(priorizadas, start=1):
        base = knowledge.get(s["key"])
        extra = _BIBLIOTECA.get(s["key"], _DEFAULT_ACAO)
        sub = _SUB_BY_KEY.get(s["key"], {})
        registros.append({
            "ordem": ordem,
            "dimensao_key": s["key"],
            "fator": s["nome"],
            "item_macro": doms.get(sub.get("dominio"), ""),
            "escore": s.get("score"),
            "risco_score": s["risco_score"],
            "nivel": s["nivel"],
            "nivel_label": NIVEL_LABEL.get(s["nivel"], "—"),
            "risco_identificado": base.get("impacto_negativo", ""),
            "medida_controle": base.get("acao", ""),
            "tipo": extra["tipo"],
            "nivel_intervencao": extra["nivel"],
            "responsavel": extra["responsavel"],
            "prazo_dias": extra["prazo_dias"],
            "indicador": extra["indicador"],
        })
    return registros
