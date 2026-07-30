"""Planos de assinatura — editáveis no painel do super admin, sem deploy."""

from .db import Company, Plan, get_session

CICLOS = {"MONTHLY": "Mensal", "YEARLY": "Anual"}


def _ctx(p: Plan) -> dict:
    return {
        "id": p.id,
        "nome": p.nome,
        "valor_centavos": p.valor_centavos,
        "ciclo": p.ciclo,
        "ciclo_label": CICLOS.get(p.ciclo, p.ciclo),
        "tipo": p.tipo,
        "ativo": p.ativo,
        "ordem": p.ordem,
    }


def listar(tipo: str | None = None, apenas_ativos: bool = False) -> list[dict]:
    with get_session() as s:
        q = s.query(Plan)
        if tipo:
            q = q.filter(Plan.tipo == tipo)
        if apenas_ativos:
            q = q.filter(Plan.ativo == True)  # noqa: E712
        rows = q.order_by(Plan.tipo.asc(), Plan.ordem.asc(), Plan.id.asc()).all()
        return [_ctx(p) for p in rows]


def para_cadastro(kind: str) -> list[dict]:
    """Planos oferecidos no wizard público, conforme o tipo de cadastro."""
    tipo = Plan.TIPO_CONSULTORIA if kind == Company.KIND_CONSULTORIA else Plan.TIPO_EMPRESA
    return listar(tipo=tipo, apenas_ativos=True)


def criar(nome: str, valor_centavos: int, ciclo: str, tipo: str, ordem: int = 0) -> None:
    with get_session() as s:
        s.add(Plan(
            nome=nome.strip()[:120],
            valor_centavos=max(int(valor_centavos), 0),
            ciclo=ciclo if ciclo in CICLOS else "MONTHLY",
            tipo=tipo if tipo in (Plan.TIPO_EMPRESA, Plan.TIPO_CONSULTORIA) else Plan.TIPO_EMPRESA,
            ordem=ordem,
        ))
        s.commit()


def editar(plan_id: int, nome: str, valor_centavos: int, ciclo: str, ordem: int = 0) -> None:
    with get_session() as s:
        p = s.get(Plan, plan_id)
        if p is None:
            return
        p.nome = nome.strip()[:120] or p.nome
        p.valor_centavos = max(int(valor_centavos), 0)
        p.ciclo = ciclo if ciclo in CICLOS else p.ciclo
        p.ordem = ordem
        s.commit()


def alternar_ativo(plan_id: int) -> None:
    """Plano nunca é apagado — só desativado. Apagar quebraria a referência de quem
    já assinou (e o histórico de faturas)."""
    with get_session() as s:
        p = s.get(Plan, plan_id)
        if p is not None:
            p.ativo = not p.ativo
            s.commit()


def valor_de(plan_id: int | None) -> int:
    if not plan_id:
        return 0
    with get_session() as s:
        p = s.get(Plan, plan_id)
        return p.valor_centavos if p else 0


def existe_para(plan_id: int | None, kind: str) -> bool:
    """Valida no submit do cadastro que o plano escolhido serve àquele tipo."""
    if not plan_id:
        return False
    tipo = Plan.TIPO_CONSULTORIA if kind == Company.KIND_CONSULTORIA else Plan.TIPO_EMPRESA
    with get_session() as s:
        p = s.get(Plan, plan_id)
        return bool(p and p.ativo and p.tipo == tipo)


def parse_valor(texto: str) -> int:
    """'R$ 1.234,56' | '1234.56' | '1234,56' → centavos."""
    limpo = (texto or "").replace("R$", "").replace(" ", "").strip()
    if not limpo:
        return 0
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return int(round(float(limpo) * 100))
    except ValueError:
        return 0
