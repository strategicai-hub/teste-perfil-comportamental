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


def send_result_email(to: str, nome: str, perc: dict[str, int], token: str) -> None:
    if not settings.smtp_host or not settings.smtp_user:
        log.warning("SMTP não configurado — pulando envio de e-mail")
        return

    link = f"{settings.public_base_url}/r/{token}"
    msg = EmailMessage()
    msg["Subject"] = f"{nome}, aqui está seu Perfil Comportamental"
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
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
