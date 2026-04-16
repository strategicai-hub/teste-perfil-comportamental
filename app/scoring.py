from .questions import QUESTION_IDS, VALID_ARCHETYPES


def calculate(answers: dict[str, str]) -> dict[str, int]:
    counts = {a: 0 for a in VALID_ARCHETYPES}
    for qid in QUESTION_IDS:
        value = answers.get(qid)
        if value in counts:
            counts[value] += 1
    total = len(QUESTION_IDS)
    return {a: round(counts[a] / total * 100) for a in counts}
