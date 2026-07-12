"""Estrutura oficial do COPSOQ II — versão longa portuguesa (Silva et al., 2011).

Layout de 119 itens / 35 subescalas / 8 domínios. Mapeamento item→subescala,
itens invertidos, direção (risco vs recurso) e escalas de resposta pesquisados e
verificados contra o manual de Aveiro e o estudo de validação de Rosário et al. (2017).

Escoreamento: cada subescala = média dos seus itens (1-5, invertendo os reversos)
→ transformada para 0-100 por (média - 1) * 25. O nível de risco (semáforo) usa os
cortes portugueses 2,33 e 3,66 na média, equivalentes a 33,3 e 66,6 em 0-100,
SEMPRE orientados no sentido do risco (ver `risco_score` em scoring.py).
"""

# --- Escalas de resposta (índice 0 → valor 1 ... índice 4 → valor 5) ---------
# `display_desc=True` inverte apenas a ORDEM de exibição (valores permanecem 1..5).
SCALES: dict[str, dict] = {
    "freq": {
        "labels": ["Nunca ou quase nunca", "Raramente", "Às vezes", "Frequentemente", "Sempre"],
    },
    "intensidade": {
        "labels": ["Nada ou quase nada", "Um pouco", "Moderadamente", "Muito", "Extremamente"],
    },
    "satisfacao": {
        "labels": ["Muito insatisfeito", "Insatisfeito", "Nem satisfeito, nem insatisfeito", "Satisfeito", "Muito satisfeito"],
    },
    "concordancia": {
        "labels": ["Discordo totalmente", "Discordo", "Nem concordo, nem discordo", "Concordo", "Concordo totalmente"],
    },
    "saude": {
        # valor 1 = Deficitária ... valor 5 = Excelente. Exibida da melhor p/ a pior.
        "labels": ["Deficitária", "Razoável", "Boa", "Muito boa", "Excelente"],
        "display_desc": True,
    },
}

# --- Domínios ----------------------------------------------------------------
DOMAINS: list[dict] = [
    {"key": "exigencias_laborais", "nome": "Exigências laborais"},
    {"key": "organizacao_conteudo", "nome": "Organização e conteúdo do trabalho"},
    {"key": "relacoes_sociais_lideranca", "nome": "Relações sociais e liderança"},
    {"key": "interface_trabalho_individuo", "nome": "Interface trabalho–indivíduo"},
    {"key": "valores_local_trabalho", "nome": "Valores no local de trabalho"},
    {"key": "saude_bem_estar", "nome": "Saúde e bem-estar"},
    {"key": "personalidade", "nome": "Personalidade / autoeficácia"},
    {"key": "comportamentos_ofensivos", "nome": "Comportamentos ofensivos"},
]

DOMAIN_NOMES = {d["key"]: d["nome"] for d in DOMAINS}

# --- Subescalas --------------------------------------------------------------
# direcao: "risco"   → pontuação alta = mais risco à saúde (alto = vermelho)
#          "recurso" → pontuação alta = mais recurso/proteção (alto = verde)
# reverse: números de item (na numeração do PDF) invertidos antes da média.
SUBDIMENSIONS: list[dict] = [
    # Exigências laborais (risco)
    {"key": "exigencias_quantitativas", "nome": "Exigências quantitativas", "dominio": "exigencias_laborais", "items": [1, 2, 3], "reverse": [], "direcao": "risco"},
    {"key": "ritmo_trabalho", "nome": "Ritmo de trabalho", "dominio": "exigencias_laborais", "items": [4], "reverse": [], "direcao": "risco"},
    {"key": "exigencias_cognitivas", "nome": "Exigências cognitivas", "dominio": "exigencias_laborais", "items": [5, 6, 7], "reverse": [], "direcao": "risco"},
    {"key": "exigencias_emocionais", "nome": "Exigências emocionais", "dominio": "exigencias_laborais", "items": [8, 9, 10], "reverse": [], "direcao": "risco"},
    {"key": "esconder_emocoes", "nome": "Exigências para esconder emoções", "dominio": "exigencias_laborais", "items": [11, 12, 13, 14], "reverse": [], "direcao": "risco"},
    # Organização e conteúdo do trabalho (recurso)
    {"key": "influencia_trabalho", "nome": "Influência no trabalho", "dominio": "organizacao_conteudo", "items": [15, 16, 17, 18], "reverse": [], "direcao": "recurso"},
    {"key": "possibilidades_desenvolvimento", "nome": "Possibilidades de desenvolvimento", "dominio": "organizacao_conteudo", "items": [19, 20, 21], "reverse": [], "direcao": "recurso"},
    {"key": "variacao_trabalho", "nome": "Variação do trabalho", "dominio": "organizacao_conteudo", "items": [22], "reverse": [], "direcao": "recurso"},
    {"key": "significado_trabalho", "nome": "Significado do trabalho", "dominio": "organizacao_conteudo", "items": [63, 64, 65], "reverse": [], "direcao": "recurso"},
    {"key": "compromisso_local", "nome": "Compromisso com o local de trabalho", "dominio": "organizacao_conteudo", "items": [66, 67, 68], "reverse": [], "direcao": "recurso"},
    # Relações sociais e liderança
    {"key": "previsibilidade", "nome": "Previsibilidade", "dominio": "relacoes_sociais_lideranca", "items": [23, 24], "reverse": [], "direcao": "recurso"},
    {"key": "clareza_papel", "nome": "Clareza do papel", "dominio": "relacoes_sociais_lideranca", "items": [25, 26, 27], "reverse": [], "direcao": "recurso"},
    {"key": "recompensas_reconhecimento", "nome": "Recompensas / reconhecimento", "dominio": "relacoes_sociais_lideranca", "items": [28, 29, 30, 31], "reverse": [], "direcao": "recurso"},
    {"key": "conflitos_papel", "nome": "Conflitos de papéis", "dominio": "relacoes_sociais_lideranca", "items": [32, 33, 34, 35], "reverse": [], "direcao": "risco"},
    {"key": "apoio_colegas", "nome": "Apoio social de colegas", "dominio": "relacoes_sociais_lideranca", "items": [36, 37, 38], "reverse": [], "direcao": "recurso"},
    {"key": "apoio_superiores", "nome": "Apoio social de superiores", "dominio": "relacoes_sociais_lideranca", "items": [39, 40, 41], "reverse": [], "direcao": "recurso"},
    {"key": "comunidade_social", "nome": "Comunidade social no trabalho", "dominio": "relacoes_sociais_lideranca", "items": [42, 43, 44], "reverse": [], "direcao": "recurso"},
    {"key": "qualidade_lideranca", "nome": "Qualidade da liderança", "dominio": "relacoes_sociais_lideranca", "items": [45, 46, 47, 48], "reverse": [], "direcao": "recurso"},
    # Valores no local de trabalho (recurso)
    {"key": "confianca_horizontal", "nome": "Confiança horizontal (entre colegas)", "dominio": "valores_local_trabalho", "items": [49, 50, 51], "reverse": [49, 50], "direcao": "recurso"},
    {"key": "confianca_vertical", "nome": "Confiança vertical (na gestão)", "dominio": "valores_local_trabalho", "items": [52, 53, 54], "reverse": [54], "direcao": "recurso"},
    {"key": "justica_respeito", "nome": "Justiça e respeito", "dominio": "valores_local_trabalho", "items": [55, 56, 57, 58], "reverse": [], "direcao": "recurso"},
    {"key": "inclusao_social", "nome": "Inclusão / responsabilidade social", "dominio": "valores_local_trabalho", "items": [59, 60, 61, 62], "reverse": [], "direcao": "recurso"},
    # Interface trabalho–indivíduo
    {"key": "satisfacao_trabalho", "nome": "Satisfação no trabalho", "dominio": "interface_trabalho_individuo", "items": [69, 70, 71, 72], "reverse": [], "direcao": "recurso"},
    {"key": "inseguranca_laboral", "nome": "Insegurança laboral", "dominio": "interface_trabalho_individuo", "items": [73, 74, 75, 76], "reverse": [], "direcao": "risco"},
    {"key": "conflito_trabalho_familia", "nome": "Conflito trabalho–família", "dominio": "interface_trabalho_individuo", "items": [78, 79, 80], "reverse": [], "direcao": "risco"},
    {"key": "conflito_familia_trabalho", "nome": "Conflito família–trabalho", "dominio": "interface_trabalho_individuo", "items": [81, 82], "reverse": [], "direcao": "risco"},
    # Saúde e bem-estar
    {"key": "saude_geral", "nome": "Saúde geral (autopercepção)", "dominio": "saude_bem_estar", "items": [77], "reverse": [], "direcao": "recurso"},
    {"key": "problemas_sono", "nome": "Problemas de sono", "dominio": "saude_bem_estar", "items": [83, 84, 85, 86], "reverse": [], "direcao": "risco"},
    {"key": "burnout", "nome": "Burnout (esgotamento)", "dominio": "saude_bem_estar", "items": [87, 88, 89, 90], "reverse": [], "direcao": "risco"},
    {"key": "stress", "nome": "Estresse", "dominio": "saude_bem_estar", "items": [91, 92, 93, 94], "reverse": [], "direcao": "risco"},
    {"key": "sintomas_depressivos", "nome": "Sintomas depressivos", "dominio": "saude_bem_estar", "items": [95, 96, 97, 98], "reverse": [], "direcao": "risco"},
    {"key": "stress_somatico", "nome": "Sintomas somáticos de estresse", "dominio": "saude_bem_estar", "items": [99, 100, 101, 102, 103], "reverse": [], "direcao": "risco"},
    {"key": "stress_cognitivo", "nome": "Sintomas cognitivos de estresse", "dominio": "saude_bem_estar", "items": [104, 105, 106, 107], "reverse": [], "direcao": "risco"},
    # Personalidade / autoeficácia (recurso)
    {"key": "autoeficacia", "nome": "Autoeficácia", "dominio": "personalidade", "items": [108, 109, 110, 111, 112, 113], "reverse": [], "direcao": "recurso"},
    # Comportamentos ofensivos (risco)
    {"key": "comportamentos_ofensivos", "nome": "Comportamentos ofensivos", "dominio": "comportamentos_ofensivos", "items": [114, 115, 116, 117, 118, 119], "reverse": [], "direcao": "risco"},
]

# Conjunto de todos os números de item invertidos (49, 50, 54).
REVERSE_ITEMS: set[int] = {n for sub in SUBDIMENSIONS for n in sub["reverse"]}

# Cortes de risco (em 0-100) equivalentes aos cortes portugueses 2,33 e 3,66.
CUTOFF_VERDE = 100 / 3       # ~33,3  → abaixo disto: risco baixo (verde)
CUTOFF_VERMELHO = 200 / 3    # ~66,6  → acima disto: risco alto (vermelho)

TOTAL_ITENS = 119
