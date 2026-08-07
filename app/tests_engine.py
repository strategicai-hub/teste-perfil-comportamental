"""Catálogo de testes e dispatch por engine.

Cada teste tem um `kind` ("choice" | "likert") e um engine que sabe servir as
perguntas, validar respostas e calcular o resultado (`result_json`). O COPSOQ II é
o primeiro da lista. O teste de arquétipos (id 1) continua funcionando como antes,
com dupla escrita nas colunas legadas `perc_*` (feita em main.py).
"""

from . import scoring as _arch_scoring
from .questions import (
    QUESTION_IDS as _ARCH_QIDS,
    VALID_ARCHETYPES,
    public_questions as _arch_public_questions,
)
from .copsoq import scoring as _copsoq_scoring
from .copsoq.questions import (
    QUESTION_IDS as _COPSOQ_QIDS,
    QUESTIONS as _COPSOQ_QUESTIONS,
    QUESTION_IDS_CURTA as _COPSOQ_QIDS_CURTA,
    QUESTIONS_CURTA as _COPSOQ_QUESTIONS_CURTA,
)

ARCHETYPE_TEST_ID = 1
COPSOQ_TEST_ID = 11        # versão longa (119 itens) — só quando o cliente pede
COPSOQ_CURTO_TEST_ID = 12  # versão curta (41 itens) — PADRÃO

# Os dois ids respondem pelo mesmo teste: entram juntos no painel e no relatório.
COPSOQ_TEST_IDS = (COPSOQ_TEST_ID, COPSOQ_CURTO_TEST_ID)

# Versão do questionário ("curta" | "longa") ↔ id do teste.
TEST_ID_POR_VERSAO = {"curta": COPSOQ_CURTO_TEST_ID, "longa": COPSOQ_TEST_ID}
VERSAO_PADRAO = "curta"

_LIKERT_VALUES = {"1", "2", "3", "4", "5"}
_ARCH_QID_SET = set(_ARCH_QIDS)


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------
class TestEngine:
    kind = "choice"

    def public_questions(self) -> list[dict]:
        raise NotImplementedError

    def question_ids(self) -> list[str]:
        raise NotImplementedError

    def valid_value(self, qid: str, value: str) -> bool:
        raise NotImplementedError

    def missing(self, answers: dict) -> list[str]:
        return [q for q in self.question_ids() if q not in answers]

    def score(self, answers: dict) -> dict:
        raise NotImplementedError


class ArchetypeEngine(TestEngine):
    kind = "choice"

    def public_questions(self):
        return _arch_public_questions()

    def question_ids(self):
        return list(_ARCH_QIDS)

    def valid_value(self, qid, value):
        return qid in _ARCH_QID_SET and value in VALID_ARCHETYPES

    def score(self, answers):
        perc = _arch_scoring.calculate(answers)  # {tubarao, lobo, aguia, gato}
        return {"type": "archetype", "perc": perc}


class CopsoqEngine(TestEngine):
    """COPSOQ II. A mesma engine serve as duas versões: a curta usa os mesmos ids
    de pergunta da longa, só com menos itens."""

    kind = "likert"

    def __init__(self, versao: str = "longa"):
        self.versao = versao
        self._questions = _COPSOQ_QUESTIONS_CURTA if versao == "curta" else _COPSOQ_QUESTIONS
        self._qids = _COPSOQ_QIDS_CURTA if versao == "curta" else _COPSOQ_QIDS
        self._qid_set = set(self._qids)

    def public_questions(self):
        return [
            {
                "id": q["id"],
                "prompt": q["prompt"],
                "secao": q["secao"],
                "scale": q["scale"],
                "options": q["options"],
            }
            for q in self._questions
        ]

    def question_ids(self):
        return list(self._qids)

    def valid_value(self, qid, value):
        return qid in self._qid_set and value in _LIKERT_VALUES

    def score(self, answers):
        return _copsoq_scoring.calculate(answers, versao=self.versao)


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
# Grupos exibidos na página "Seus testes":
#   - "nr1": testes ligados à NR-1 / riscos psicossociais (COPSOQ II).
#   - "comportamental": bateria comportamental — bloqueada por ora (inclusive o
#     "Perfil Comportamental", que fica com ativo=False até a bateria ser liberada).
TESTS: list[dict] = [
    {
        "id": COPSOQ_CURTO_TEST_ID,
        "nome": "COPSOQ II — Riscos Psicossociais",
        "descricao": "Mapeamento dos fatores psicossociais de risco no trabalho (41 questões). Resultado por área e geral.",
        "icon": "shield",
        "ativo": True,
        "kind": "likert",
        "empresa": True,
        "grupo": "nr1",
        "versao": "curta",
    },
    {
        "id": COPSOQ_TEST_ID,
        "nome": "COPSOQ II — Riscos Psicossociais (versão completa)",
        "descricao": "Versão longa do COPSOQ II (119 questões), com as 35 dimensões do questionário original. Resultado por área e geral.",
        "icon": "shield",
        "ativo": True,
        "kind": "likert",
        "empresa": True,
        "grupo": "nr1",
        "versao": "longa",
    },
    {"id": 1, "nome": "Perfil Comportamental", "descricao": "Descubra seu arquétipo dominante — Tubarão, Lobo, Águia ou Gato.", "icon": "star", "ativo": False, "kind": "choice", "empresa": False, "grupo": "comportamental"},
    {"id": 2, "nome": "Perfil de Liderança", "descricao": "Os quatro estilos de liderança na organização.", "icon": "crown", "ativo": False, "kind": "choice", "empresa": False, "grupo": "comportamental"},
    {"id": 3, "nome": "Sabotadores Comportamentais", "descricao": "Os dez comportamentos tóxicos do profissional.", "icon": "warning", "ativo": False, "kind": "choice", "empresa": False, "grupo": "comportamental"},
    {"id": 4, "nome": "Inteligência Emocional", "descricao": "Os 15 indicadores de relacionamentos interpessoais inteligentes.", "icon": "heart", "ativo": False, "kind": "choice", "empresa": False, "grupo": "comportamental"},
    {"id": 5, "nome": "Trabalho em Equipe", "descricao": "As 5 áreas de contribuição do profissional para o time.", "icon": "users", "ativo": False, "kind": "choice", "empresa": False, "grupo": "comportamental"},
    {"id": 6, "nome": "Fit Cultural", "descricao": "Avaliação do perfil do candidato com a vaga e a cultura da empresa.", "icon": "puzzle", "ativo": False, "kind": "choice", "empresa": False, "grupo": "comportamental"},
    {"id": 7, "nome": "Valores", "descricao": "Os cinco principais valores que norteiam o indivíduo.", "icon": "compass", "ativo": False, "kind": "choice", "empresa": False, "grupo": "comportamental"},
    {"id": 8, "nome": "Personalidade", "descricao": "Baseado no framework das 16 personalidades.", "icon": "sparkles", "ativo": False, "kind": "choice", "empresa": False, "grupo": "comportamental"},
    {"id": 9, "nome": "Tríade do Tempo", "descricao": "Gestão do tempo e produtividade.", "icon": "clock", "ativo": False, "kind": "choice", "empresa": False, "grupo": "comportamental"},
    {"id": 10, "nome": "Avaliação do Líder", "descricao": "As 8 áreas de relacionamento do gestor com o time.", "icon": "briefcase", "ativo": False, "kind": "choice", "empresa": False, "grupo": "comportamental"},
]

_ENGINES: dict[int, TestEngine] = {
    ARCHETYPE_TEST_ID: ArchetypeEngine(),
    COPSOQ_TEST_ID: CopsoqEngine("longa"),
    COPSOQ_CURTO_TEST_ID: CopsoqEngine("curta"),
}


def get_test(test_id: int) -> dict | None:
    return next((t for t in TESTS if t["id"] == test_id), None)


def get_engine(test_id: int) -> TestEngine | None:
    return _ENGINES.get(test_id)


def copsoq_test_id(versao: str | None) -> int:
    """Id do teste COPSOQ para a versão escolhida pela empresa (padrão: curta)."""
    return TEST_ID_POR_VERSAO.get((versao or "").strip().lower(), TEST_ID_POR_VERSAO[VERSAO_PADRAO])


def is_empresa_test(test_id: int) -> bool:
    t = get_test(test_id)
    return bool(t and t.get("empresa"))
