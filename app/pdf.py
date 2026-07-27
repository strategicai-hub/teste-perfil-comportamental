"""Geração do PDF do relatório NR-1.

Renderiza o mesmo parcial Jinja da tela (`_report_body.html`) dentro de um
documento com CSS de impressão e converte com WeasyPrint — assim o PDF sai
idêntico ao que o gestor vê, sem manter dois layouts.

WeasyPrint é importado sob demanda: se as bibliotecas de sistema não estiverem
presentes (ex.: rodando local no Windows), o resto da aplicação continua de pé e
só o download do PDF falha, com mensagem clara.
"""

import functools
import io


class PdfIndisponivel(RuntimeError):
    """WeasyPrint não pôde ser carregado neste ambiente."""


@functools.lru_cache(maxsize=1)
def disponivel() -> bool:
    """A checagem é cara (carrega libs nativas) — resolvida uma vez por processo."""
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return False
    return True


def html_para_pdf(html: str, base_url: str | None = None) -> io.BytesIO:
    try:
        from weasyprint import HTML
    except Exception as exc:  # pragma: no cover - depende do ambiente
        raise PdfIndisponivel(
            "Geração de PDF indisponível neste ambiente (WeasyPrint não carregou)."
        ) from exc

    buffer = io.BytesIO()
    HTML(string=html, base_url=base_url).write_pdf(buffer)
    buffer.seek(0)
    return buffer
