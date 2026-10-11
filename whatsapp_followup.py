"""Reenganche automático por WhatsApp (plantilla aprobada por Meta) para leads de Valentina
que no confirmaron después de unos días."""

import os
from twilio.rest import Client

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")  # ej: whatsapp:+5493804245540
FOLLOWUP_CONTENT_SID = os.getenv("FOLLOWUP_CONTENT_SID")


def send_followup_whatsapp(telefono: str) -> bool:
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM, FOLLOWUP_CONTENT_SID]):
        return False
    try:
        to = telefono.strip()
        to = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(from_=TWILIO_WHATSAPP_FROM, to=to, content_sid=FOLLOWUP_CONTENT_SID)
        print(f"[whatsapp] Seguimiento enviado a {to}")
        return True
    except Exception as e:
        print(f"[whatsapp] Error al mandar seguimiento (puede ser que la plantilla aún no esté aprobada): {e}")
        return False
