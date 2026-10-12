"""
Transcripción de notas de voz de WhatsApp con Whisper en Cloudflare Workers AI.
Acepta el OGG/Opus de WhatsApp tal cual llega, sin convertir.
"""

import base64
import os
import time
from typing import Optional

import httpx

# off = Valentina avisa que todavía no escucha audios (comportamiento de siempre).
AUDIO_TRANSCRIPTION = os.getenv("AUDIO_TRANSCRIPTION", "off").lower()
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_AI_TOKEN = os.getenv("CLOUDFLARE_AI_TOKEN", "")
MODEL = "@cf/openai/whisper-large-v3-turbo"

# Twilio espera la respuesta ~15 s: descarga + transcripción + Claude tienen que entrar ahí.
# Una nota de voz de WhatsApp pesa ~1,4 KB por segundo, así que esto es ~1 minuto.
MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", "90000") or 90000)


def activa() -> bool:
    return AUDIO_TRANSCRIPTION == "on" and bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_AI_TOKEN)


def transcribir(data: bytes) -> Optional[str]:
    """Devuelve el texto del audio, o None si no se pudo transcribir."""
    inicio = time.time()
    try:
        resp = httpx.post(
            f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{MODEL}",
            headers={"Authorization": f"Bearer {CLOUDFLARE_AI_TOKEN}"},
            json={"audio": base64.b64encode(data).decode(), "language": "es"},
            timeout=9,
        )
        cuerpo = resp.json()
        texto = ((cuerpo.get("result") or {}).get("text") or "").strip()
        if not cuerpo.get("success") or not texto:
            print(f"[audio] Transcripción vacía o con error: HTTP {resp.status_code} {cuerpo.get('errors')}")
            return None
        print(f"[audio] Transcripto en {time.time() - inicio:.1f}s ({len(data)} bytes)")
        return texto
    except Exception as e:
        print(f"[audio] Error transcribiendo: {e}")
        return None
