import os, smtplib, ssl
from email.message import EmailMessage

def send_mail(subject, body, attachment_path=None):
    gmail = os.getenv("GMAIL_ADDRESS", "").strip()
    apppw = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    to    = (os.getenv("ALERT_TO_EMAIL", "").strip() or gmail)

    if not gmail or not apppw or not to:
        return False, "Email not configured"

    try:
        msg = EmailMessage()
        msg["From"] = gmail
        msg["To"]   = to
        msg["Subject"] = subject
        msg.set_content(body)

        if attachment_path and os.path.exists(attachment_path):
            import mimetypes
            ctype, _ = mimetypes.guess_type(attachment_path)
            maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
            with open(attachment_path, "rb") as f:
                msg.add_attachment(f.read(), maintype=maintype, subtype=subtype,
                                   filename=os.path.basename(attachment_path))

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(gmail, apppw)
            server.send_message(msg)
        return True, "sent"
    except Exception as e:
        return False, str(e)
