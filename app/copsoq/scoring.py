"""Escoreamento dimensional do COPSOQ II.

- `calculate(answers)` → resultado individual (subescalas + domínios + top de riscos).
- `aggregate(results)` → média das subescalas entre vários respondentes (painel da
  empresa: geral ou por área).

Cada subescala vira média dos itens (1-5, invertendo os reversos), transformada em
0-100 por (média-1)*25. `risco_score` reorienta tudo no sentido do risco
(subescala de recurso: risco = 100 - score), e o semáforo (verde/amarelo/vermelho)
é sempre lido sobre `risco_score` com os cortes 33,3 e 66,6.
"""

import math

from .structure import (
    CUTOFF_VERDE,
    CUTOFF_VERMELHO,
    DOMAINS,
    SUBDIMENSIONS,
)
from .questions import QUESTION_IDS


def _nivel(risco_score: float | None) -> str | None:
    if risco_score is None:
        return None
    if risco_score < CUTOFF_VERDE:
        return "verde"
    if risco_score < CUTOFF_VERMELHO:
        return "amarelo"
    return "vermelho"


def _subscale_score(sub: dict, answers: dict) -> int | None:
    """Média 0-100 da subescala, ou None se menos da metade dos itens foi respondida."""
    vals: list[int] = []
    for n in sub["items"]:
        raw = answers.get(f"q{n}")
        if raw is None:
            continue
        try:
            v = int(raw)
        except (TypeError, ValueError):
            continue
        if v < 1 or v > 5:
            continue
        if n in sub["reverse"]:
            v = 6 - v
        vals.append(v)
    needed = math.ceil(len(sub["items"]) / 2)
    if len(vals) < needed:
        return None
    mean = sum(vals) / len(vals)
    return round((mean - 1) * 25)


def _risco(score: int | None, direcao: str) -> int | None:
    if score is None:
        return None
    return score if direcao == "risco" else 100 - score


def _domains_from_subscales(subs_out: list[dict]) -> list[dict]:
    out = []
    for dom in DOMAINS:
        riscos = [s["risco_score"] for s in subs_out if s["dominio"] == dom["key"] and s["risco_score"] is not None]
        if riscos:
            dr = round(sum(riscos) / len(riscos))
            nivel = _nivel(dr)
        else:
            dr = None
            nivel = None
        out.append({"key": dom["key"], "nome": dom["nome"], "risco_medio": dr, "nivel": nivel})
    return out


def calculate(answers: dict) -> dict:
    """Resultado individual do COPSOQ a partir das respostas (qid -> '1'..'5')."""
    subs_out: list[dict] = []
    for sub in SUBDIMENSIONS:
        score = _subscale_score(sub, answers)
        risco = _risco(score, sub["direcao"])
        subs_out.append({
            "key": sub["key"],
            "nome": sub["nome"],
            "dominio": sub["dominio"],
            "direcao": sub["direcao"],
            "score": score,
            "risco_score": risco,
            "nivel": _nivel(risco),
        })

    answered = sum(1 for qid in QUESTION_IDS if answers.get(qid) is not None)
    ranked = sorted(
        (s for s in subs_out if s["risco_score"] is not None),
        key=lambda s: s["risco_score"],
        reverse=True,
    )
    top_riscos = [
        {"nome": s["nome"], "risco_score": s["risco_score"], "nivel": s["nivel"]}
        for s in ranked[:5]
    ]
    return {
        "type": "copsoq",
        "answered": answered,
        "subscales": subs_out,
        "domains": _domains_from_subscales(subs_out),
        "top_riscos": top_riscos,
    }


def aggregate(results: list[dict]) -> dict:
    """Agrega vários resultados individuais (média das subescalas) — painel da empresa."""
    acc: dict[str, dict] = {}
    for r in results:
        for s in r.get("subscales", []):
            if s.get("score") is None:
                continue
            a = acc.setdefault(s["key"], {"scores": [], "riscos": []})
            a["scores"].append(s["score"])
            a["riscos"].append(s["risco_score"])

    subs_out: list[dict] = []
    for sub in SUBDIMENSIONS:
        a = acc.get(sub["key"])
        if not a or not a["riscos"]:
            subs_out.append({
                "key": sub["key"], "nome": sub["nome"], "dominio": sub["dominio"],
                "direcao": sub["direcao"], "score": None, "risco_score": None, "nivel": None, "n": 0,
            })
            continue
        score = round(sum(a["scores"]) / len(a["scores"]))
        risco = round(sum(a["riscos"]) / len(a["riscos"]))
        subs_out.append({
            "key": sub["key"], "nome": sub["nome"], "dominio": sub["dominio"],
            "direcao": sub["direcao"], "score": score, "risco_score": risco,
            "nivel": _nivel(risco), "n": len(a["riscos"]),
        })

    ranked = sorted(
        (s for s in subs_out if s["risco_score"] is not None),
        key=lambda s: s["risco_score"],
        reverse=True,
    )
    top_riscos = [
        {"nome": s["nome"], "risco_score": s["risco_score"], "nivel": s["nivel"], "n": s["n"]}
        for s in ranked[:5]
    ]
    return {
        "type": "copsoq_agg",
        "respondentes": len(results),
        "subscales": subs_out,
        "domains": _domains_from_subscales(subs_out),
        "top_riscos": top_riscos,
    }
