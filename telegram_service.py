"""Aviso instantáneo por Telegram cuando Valentina captura un lead —
para poder sumarse a la conversación en persona mientras sigue en curso,
sobre todo cuando el prospecto pidió explícitamente hablar con alguien."""

import os
import httpx

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def _send(text: str, markdown: bool = True) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        return False
    payload = {"chat_id": CHAT_ID, "text": text}
    if markdown:
        payload["parse_mode"] = "Markdown"
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[telegram] Error al notificar: {e}")
        return False


def notify_lead(
    telefono: str,
    nombre: str,
    tratamiento: str,
    sucursal: str = "",
    horario: str = "",
    resumen: str = "",
    origen: str = "",
) -> bool:
    numero_limpio = telefono.replace("whatsapp:", "").strip()
    numero_wa = "".join(c for c in numero_limpio if c.isdigit())
    telefono_link = f"[{numero_limpio}](https://wa.me/{numero_wa})" if numero_wa else numero_limpio

    resumen = resumen.strip()
    if len(resumen) > 2500:
        resumen = resumen[:2500] + "… (resumen truncado)"
    bloque_resumen = f"📋 *Resumen de la conversación:*\n{resumen}\n\n" if resumen else ""

    text = (
        f"🎯 *Nuevo lead — Demo Valentina{f' ({origen})' if origen else ''}*\n\n"
        f"👤 {nombre}\n"
        f"📞 {telefono_link}\n"
        f"🏢 {sucursal or 'No especificado'}\n"
        f"💼 {tratamiento}\n"
        f"🕐 Horario para la llamada: {horario or 'No especificado'}\n\n"
        f"{bloque_resumen}"
        f"Tocá el número para abrirle la conversación directo en WhatsApp."
    )
    return _send(text)


def notify_aviso(texto: str) -> bool:
    """Aviso operativo en texto plano (sin Markdown: puede traer texto dictado por el prospecto)."""
    return _send(texto, markdown=False)
