"""Leitura da planilha de colaboradores enviada pelo gestor.

Aceita `.xlsx` (openpyxl) e `.csv` (stdlib, separador `,` ou `;`). Espera as colunas
**Nome**, **E-mail** e **Área** — o cabeçalho é reconhecido sem depender de acento,
caixa ou pontuação, então `E-mail`, `email` e `EMAIL` valem a mesma coisa.

`parse_planilha()` nunca levanta por linha ruim: devolve as linhas válidas e a lista
de erros, para a tela mostrar a prévia antes de gravar qualquer coisa.
"""

import csv
import io
import re
import unicodedata

MAX_LINHAS = 2000

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


def _normaliza_cabecalho(valor: object) -> str:
    """'E-mail ' → 'email'; 'Área' → 'area'. Tolera acento, caixa e pontuação."""
    texto = str(valor or "").strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", texto)


# Sinônimos aceitos para cada coluna, já normalizados.
_COLUNAS = {
    "nome": {"nome", "nomecompleto", "colaborador", "funcionario", "name"},
    "email": {"email", "emails", "correio", "correioeletronico", "mail"},
    "area": {"area", "setor", "departamento", "areasetor", "equipe", "time"},
}


def _mapear_colunas(cabecalho: list[object]) -> dict[str, int]:
    """Índice de cada coluna conhecida no cabeçalho da planilha."""
    mapa: dict[str, int] = {}
    for i, celula in enumerate(cabecalho):
        chave = _normaliza_cabecalho(celula)
        for campo, sinonimos in _COLUNAS.items():
            if chave in sinonimos and campo not in mapa:
                mapa[campo] = i
    return mapa


def _linhas_do_xlsx(conteudo: bytes) -> list[list[object]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    ws = wb.active
    linhas = [list(row) for row in ws.iter_rows(max_row=MAX_LINHAS + 1, values_only=True)]
    wb.close()
    return linhas


def _linhas_do_csv(conteudo: bytes) -> list[list[object]]:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            texto = conteudo.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Não consegui ler o arquivo. Salve como UTF-8 e tente de novo.")

    amostra = texto[:4096]
    try:
        dialect = csv.Sniffer().sniff(amostra, delimiters=",;\t")
        delimitador = dialect.delimiter
    except csv.Error:
        delimitador = ";" if amostra.count(";") > amostra.count(",") else ","

    leitor = csv.reader(io.StringIO(texto), delimiter=delimitador)
    return [linha for _, linha in zip(range(MAX_LINHAS + 1), leitor)]


def parse_planilha(nome_arquivo: str, conteudo: bytes) -> tuple[list[dict], list[str]]:
    """Lê a planilha e devolve `(linhas_validas, erros)`.

    Cada linha válida é `{"nome", "email", "area"}`. E-mails repetidos dentro do
    próprio arquivo são reportados como erro e mantidos só na primeira ocorrência.
    """
    nome = (nome_arquivo or "").lower()
    if nome.endswith(".xlsx"):
        linhas = _linhas_do_xlsx(conteudo)
    elif nome.endswith((".csv", ".txt")):
        linhas = _linhas_do_csv(conteudo)
    else:
        raise ValueError("Formato não suportado. Envie um arquivo .xlsx ou .csv.")

    linhas = [l for l in linhas if any(str(c or "").strip() for c in l)]
    if not linhas:
        raise ValueError("A planilha está vazia.")

    mapa = _mapear_colunas(linhas[0])
    faltando = [c for c in ("nome", "email", "area") if c not in mapa]
    if faltando:
        rotulos = {"nome": "Nome", "email": "E-mail", "area": "Área"}
        nomes = ", ".join(rotulos[c] for c in faltando)
        raise ValueError(f"A planilha precisa ter as colunas Nome, E-mail e Área. Não encontrei: {nomes}.")

    validas: list[dict] = []
    erros: list[str] = []
    vistos: set[str] = set()

    for numero, linha in enumerate(linhas[1:], start=2):
        def celula(campo: str) -> str:
            i = mapa[campo]
            return str(linha[i] or "").strip() if i < len(linha) else ""

        nome_col, email, area = celula("nome"), celula("email").lower(), celula("area")

        if not any((nome_col, email, area)):
            continue
        if not email:
            erros.append(f"Linha {numero}: sem e-mail.")
            continue
        if not _EMAIL_RE.match(email):
            erros.append(f"Linha {numero}: e-mail inválido ({email}).")
            continue
        if email in vistos:
            erros.append(f"Linha {numero}: e-mail repetido na planilha ({email}).")
            continue
        if not nome_col:
            erros.append(f"Linha {numero}: sem nome ({email}).")
            continue
        if not area:
            erros.append(f"Linha {numero}: sem área ({email}).")
            continue

        vistos.add(email)
        validas.append({"nome": nome_col, "email": email, "area": area})

    if len(validas) > MAX_LINHAS:
        raise ValueError(f"A planilha tem mais de {MAX_LINHAS} linhas. Divida em arquivos menores.")

    return validas, erros
