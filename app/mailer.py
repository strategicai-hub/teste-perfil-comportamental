import logging
import smtplib
from email.message import EmailMessage

from .config import settings

log = logging.getLogger(__name__)


def _result_html(nome: str, perc: dict[str, int], link: str) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>Seu Perfil Comportamental</title></head>
<body style="font-family: Arial, Helvetica, sans-serif; background:#f5f7fa; margin:0; padding:24px;">
  <div style="max-width:560px; margin:0 auto; background:#ffffff; border-radius:12px; padding:32px; box-shadow:0 2px 8px rgba(0,0,0,0.06);">
    <h1 style="color:#0f766e; margin:0 0 8px 0;">Olá, {nome}!</h1>
    <p style="color:#334155; line-height:1.5;">Aqui está o resultado do seu teste de Perfil Comportamental:</p>

    <table style="width:100%; border-collapse:collapse; margin:24px 0;">
      <tr>
        <td style="padding:12px; text-align:center; background:#0f766e; color:#fff; border-radius:8px;">
          <div style="font-weight:700;">TUBARÃO</div>
          <div style="font-size:28px; font-weight:700; margin-top:4px;">{perc.get('tubarao', 0)}%</div>
        </td>
        <td style="width:8px;"></td>
        <td style="padding:12px; text-align:center; background:#be123c; color:#fff; border-radius:8px;">
          <div style="font-weight:700;">LOBO</div>
          <div style="font-size:28px; font-weight:700; margin-top:4px;">{perc.get('lobo', 0)}%</div>
        </td>
      </tr>
      <tr><td colspan="3" style="height:8px;"></td></tr>
      <tr>
        <td style="padding:12px; text-align:center; background:#ea580c; color:#fff; border-radius:8px;">
          <div style="font-weight:700;">ÁGUIA</div>
          <div style="font-size:28px; font-weight:700; margin-top:4px;">{perc.get('aguia', 0)}%</div>
        </td>
        <td style="width:8px;"></td>
        <td style="padding:12px; text-align:center; background:#16a34a; color:#fff; border-radius:8px;">
          <div style="font-weight:700;">GATO</div>
          <div style="font-size:28px; font-weight:700; margin-top:4px;">{perc.get('gato', 0)}%</div>
        </td>
      </tr>
    </table>

    <p style="color:#334155; line-height:1.5;">
      Você pode voltar a qualquer momento para revisar o resultado e continuar a análise com nosso analista comportamental.
    </p>

    <p style="text-align:center; margin:32px 0;">
      <a href="{link}" style="display:inline-block; background:#0f766e; color:#fff; padding:14px 28px; text-decoration:none; border-radius:8px; font-weight:700;">
        Ver meu resultado e continuar a análise
      </a>
    </p>

    <p style="color:#64748b; font-size:13px; line-height:1.5;">
      Quer uma análise mais profunda e um plano de desenvolvimento personalizado? Basta responder este e-mail.
    </p>
    <p style="color:#94a3b8; font-size:12px; margin-top:24px;">Strategic AI — Perfil Comportamental</p>
  </div>
</body>
</html>"""


_NIVEL_TXT = {"verde": "risco baixo", "amarelo": "risco intermediário", "vermelho": "risco alto"}


def _copsoq_html(nome: str, result: dict, link: str) -> str:
    top = result.get("top_riscos") or []
    linhas = "".join(
        f'<tr><td style="padding:8px 0;color:#334155;">{t["nome"]}</td>'
        f'<td style="padding:8px 0;text-align:right;color:#64748b;">{_NIVEL_TXT.get(t.get("nivel"), "-")}</td></tr>'
        for t in top
    )
    return f"""\
<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>Seu resultado COPSOQ II</title></head>
<body style="font-family: Arial, Helvetica, sans-serif; background:#f5f7fa; margin:0; padding:24px;">
  <div style="max-width:560px; margin:0 auto; background:#ffffff; border-radius:12px; padding:32px; box-shadow:0 2px 8px rgba(0,0,0,0.06);">
    <h1 style="color:#0f766e; margin:0 0 8px 0;">Olá, {nome}!</h1>
    <p style="color:#334155; line-height:1.5;">Você concluiu o questionário de riscos psicossociais (COPSOQ II). Estes são os seus principais focos de atenção:</p>
    <table style="width:100%; border-collapse:collapse; margin:16px 0;">{linhas}</table>
    <p style="text-align:center; margin:32px 0;">
      <a href="{link}" style="display:inline-block; background:#0f766e; color:#fff; padding:14px 28px; text-decoration:none; border-radius:8px; font-weight:700;">
        Ver meu resultado completo e conversar com o analista
      </a>
    </p>
    <p style="color:#94a3b8; font-size:12px; margin-top:24px;">Strategic AI — Riscos Psicossociais</p>
  </div>
</body>
</html>"""


def send_result_email(to: str, nome: str, result: dict, token: str) -> None:
    if not settings.smtp_host or not settings.smtp_user:
        log.warning("SMTP não configurado — pulando envio de e-mail")
        return

    link = f"{settings.public_base_url}/r/{token}"
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to

    if result and result.get("type") == "copsoq":
        top = result.get("top_riscos") or []
        msg["Subject"] = f"{nome}, aqui está seu resultado do COPSOQ II"
        linhas_txt = "\n".join(f"- {t['nome']} ({_NIVEL_TXT.get(t.get('nivel'), '-')})" for t in top)
        msg.set_content(
            f"Olá {nome},\n\n"
            f"Você concluiu o questionário de riscos psicossociais (COPSOQ II).\n"
            f"Principais focos de atenção:\n{linhas_txt}\n\n"
            f"Acesse seu resultado completo e continue a análise: {link}\n\n"
            f"Strategic AI"
        )
        msg.add_alternative(_copsoq_html(nome, result, link), subtype="html")
    else:
        perc = (result or {}).get("perc", {})
        msg["Subject"] = f"{nome}, aqui está seu Perfil Comportamental"
        msg.set_content(
            f"Olá {nome},\n\n"
            f"Seu resultado:\n"
            f"- Tubarão: {perc.get('tubarao', 0)}%\n"
            f"- Lobo: {perc.get('lobo', 0)}%\n"
            f"- Águia: {perc.get('aguia', 0)}%\n"
            f"- Gato: {perc.get('gato', 0)}%\n\n"
            f"Acesse seu resultado e continue a análise: {link}\n\n"
            f"Strategic AI"
        )
        msg.add_alternative(_result_html(nome, perc, link), subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_pass)
            smtp.send_message(msg)
    except Exception as exc:
        log.error("Falha ao enviar e-mail: %s", exc)


def _invite_html(nome: str, empresa: str, prazo: str, link: str) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>Teste da NR-1</title></head>
<body style="font-family: Arial, Helvetica, sans-serif; background:#f5f7fa; margin:0; padding:24px;">
  <div style="max-width:560px; margin:0 auto; background:#ffffff; border-radius:12px; padding:32px; box-shadow:0 2px 8px rgba(0,0,0,0.06);">
    <h1 style="color:#0f766e; margin:0 0 16px 0; font-size:22px;">Olá, {nome}.</h1>

    <p style="color:#334155; line-height:1.6; margin:0 0 16px 0;">
      A <strong>{empresa}</strong> está fazendo a avaliação de saúde e bem-estar no trabalho
      exigida pela <strong>NR-1</strong>. Sua participação é importante.
    </p>

    <p style="color:#334155; line-height:1.6; margin:0 0 16px 0;">
      São perguntas rápidas e leva cerca de <strong>15 minutos</strong>.
    </p>

    <p style="color:#334155; line-height:1.6; margin:0 0 16px 0;">
      Suas respostas são confidenciais: a empresa vê apenas o resultado do grupo,
      nunca as respostas de uma pessoa.
    </p>

    <div style="background:#f0fdfa; border-left:4px solid #0f766e; padding:12px 16px; margin:0 0 24px 0;">
      <p style="color:#0f766e; margin:0; font-weight:700;">Você pode responder até {prazo}.</p>
    </div>

    <p style="text-align:center; margin:0 0 24px 0;">
      <a href="{link}" style="display:inline-block; background:#0f766e; color:#fff; padding:14px 32px; text-decoration:none; border-radius:8px; font-weight:700;">
        Responder o teste agora
      </a>
    </p>

    <p style="color:#64748b; font-size:13px; line-height:1.6; margin:0;">
      Se o botão não funcionar, copie e cole este endereço no seu navegador:<br>
      <a href="{link}" style="color:#0f766e; word-break:break-all;">{link}</a>
    </p>

    <p style="color:#94a3b8; font-size:12px; margin-top:28px;">Strategic AI — Riscos Psicossociais (NR-1)</p>
  </div>
</body>
</html>"""


def send_invite_email(to: str, nome: str, empresa: str, prazo: str, link: str) -> None:
    """Convite do teste da NR-1 para um colaborador. Levanta em caso de falha.

    O chamador registra o erro em `CampaignInvite.erro_envio` para o gestor poder
    reenviar só para quem não recebeu.
    """
    if not settings.smtp_host or not settings.smtp_user:
        raise RuntimeError("SMTP não configurado")

    primeiro_nome = (nome or "").split()[0] if nome else ""

    msg = EmailMessage()
    msg["Subject"] = f"{primeiro_nome}, aqui está seu link para responder o teste da NR-1"
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg.set_content(
        f"Olá, {primeiro_nome}.\n\n"
        f"A {empresa} está fazendo a avaliação de saúde e bem-estar no trabalho "
        f"exigida pela NR-1. Sua participação é importante.\n\n"
        f"São perguntas rápidas e leva cerca de 15 minutos.\n"
        f"Suas respostas são confidenciais: a empresa vê apenas o resultado do grupo, "
        f"nunca as respostas de uma pessoa.\n\n"
        f"Você pode responder até {prazo}.\n\n"
        f"Responda aqui: {link}\n\n"
        f"Strategic AI — Riscos Psicossociais (NR-1)"
    )
    msg.add_alternative(_invite_html(primeiro_nome, empresa, prazo, link), subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_pass)
        smtp.send_message(msg)


def _reset_html(nome: str, link: str) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>Redefinir senha</title></head>
<body style="font-family: Arial, Helvetica, sans-serif; background:#f5f7fa; margin:0; padding:24px;">
  <div style="max-width:520px; margin:0 auto; background:#ffffff; border-radius:12px; padding:32px; box-shadow:0 2px 8px rgba(0,0,0,0.06);">
    <h1 style="color:#0f766e; margin:0 0 12px 0; font-size:22px;">Olá, {nome}.</h1>
    <p style="color:#334155; line-height:1.6;">Recebemos uma solicitação para redefinir a senha da sua conta nos Testes Comportamentais da Strategic AI.</p>
    <p style="text-align:center; margin:28px 0;">
      <a href="{link}" style="display:inline-block; background:#0f766e; color:#fff; padding:12px 28px; text-decoration:none; border-radius:8px; font-weight:700;">
        Redefinir minha senha
      </a>
    </p>
    <p style="color:#64748b; font-size:13px; line-height:1.6;">
      O link expira em <strong>1 hora</strong>. Se você não solicitou a redefinição, basta ignorar este e-mail.
    </p>
    <p style="color:#94a3b8; font-size:12px; margin-top:24px;">Strategic AI — Testes Comportamentais</p>
  </div>
</body>
</html>"""


def send_password_reset(to: str, nome: str, reset_link: str) -> None:
    if not settings.smtp_host or not settings.smtp_user:
        log.warning("SMTP não configurado — pulando envio de reset")
        return

    msg = EmailMessage()
    msg["Subject"] = "Redefinir senha — Strategic AI"
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg.set_content(
        f"Olá {nome},\n\n"
        f"Acesse o link abaixo para redefinir sua senha (expira em 1 hora):\n\n"
        f"{reset_link}\n\n"
        f"Se não foi você, ignore este e-mail.\n\n"
        f"Strategic AI"
    )
    msg.add_alternative(_reset_html(nome, reset_link), subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_pass)
            smtp.send_message(msg)
    except Exception as exc:
        log.error("Falha ao enviar e-mail de reset: %s", exc)
        raise
