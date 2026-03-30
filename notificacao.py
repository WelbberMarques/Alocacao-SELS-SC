"""
Notificacoes por email via Gmail SMTP
"""
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


def enviar_notificacao(destinatario: str, dados: dict,
                       gmail_user: str, gmail_app_password: str):
    """
    Envia email de notificacao ao concluir processamento.
    dados: {
        usuario_nome, xmls, planilha, divergencias, horario
    }
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[CPB Alocacao] Planilha gerada - {dados.get('planilha', '')}"
        msg["From"]    = gmail_user
        msg["To"]      = destinatario

        xmls_list = "\n".join(f"  - {x}" for x in dados.get("xmls", []))
        divs = dados.get("divergencias", 0)
        divs_txt = f"{divs} divergencia(s) corrigida(s) na coluna T" if divs else "Nenhuma divergencia"

        corpo = f"""
CPB Alocacao - Relatorio de Processamento
==========================================

Usuario:        {dados.get("usuario_nome", "")}
Horario:        {dados.get("horario", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))}
Planilha:       {dados.get("planilha", "")}
Divergencias:   {divs_txt}

XMLs processados:
{xmls_list}

==========================================
Sistema CPB Alocacao - SELS-SC
"""
        msg.attach(MIMEText(corpo, "plain", "utf-8"))

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as server:
            server.login(gmail_user, gmail_app_password)
            server.sendmail(gmail_user, destinatario, msg.as_string())

        return True
    except Exception as e:
        print(f"Erro ao enviar email: {e}")
        return False
