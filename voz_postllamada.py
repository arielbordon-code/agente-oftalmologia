"""
Leads del agente de voz de Valentina (ElevenLabs).

Al terminar cada llamada, ElevenLabs manda un webhook "post_call_transcription" con los datos
que extrajo (nombre, WhatsApp, negocio, rubro, qué quiere resolver, horario). Si el prospecto
dejó nombre y WhatsApp, se registra en el mismo Sheet que los leads de WhatsApp y se avisa
por Telegram, igual que hace agent.py.
"""

import hashlib
import hmac
import json
import os
import time
from collections import deque
from typing import Optional

from sheets import registrar_lead
from telegram_service import notify_lead

WEBHOOK_SECRET = os.getenv("ELEVENLABS_WEBHOOK_SECRET", "")
AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID", "")
TOLERANCIA_SEGUNDOS = 30 * 60

# ElevenLabs puede reintentar el mismo webhook: no registrar dos veces la misma llamada.
_conversaciones_procesadas = deque(maxlen=200)


def firma_valida(cuerpo: str, header: str) -> bool:
    """Misma verificación que elevenlabs.webhooks.construct_event del SDK oficial:
    header 't=<timestamp>,v0=<hmac_sha256 de "timestamp.cuerpo">'."""
    if not WEBHOOK_SECRET or not header:
        return False
    partes = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    timestamp, firma = partes.get("t", ""), partes.get("v0", "")
    if not timestamp.isdigit() or not firma:
        return False
    if int(timestamp) < time.time() - TOLERANCIA_SEGUNDOS:
        return False
    esperada = hmac.new(WEBHOOK_SECRET.encode(), f"{timestamp}.{cuerpo}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(firma, esperada)


def normalizar_whatsapp_ar(numero: str) -> tuple[str, bool]:
    """Lleva un celular argentino dictado por voz a +549XXXXXXXXXX. Devuelve (número, es_válido).
    Si no tiene la forma esperada se devuelve tal cual, marcado como no válido, para que
    el lead igual se registre y se revise a mano."""
    d = "".join(c for c in numero if c.isdigit())
    if d.startswith("0"):
        d = d[1:]
    if len(d) == 10:
        d = "549" + d
    elif len(d) == 12 and d.startswith("54"):
        d = "549" + d[2:]
    if len(d) == 13 and d.startswith("549"):
        return "+" + d, True
    return d, False


def _valor(resultados: dict, clave: str) -> str:
    valor = (resultados.get(clave) or {}).get("value")
    return str(valor).strip() if valor not in (None, "None") else ""


def _transcripcion(transcript: list) -> str:
    lineas = []
    for t in transcript or []:
        if t.get("message"):
            quien = "Prospecto" if t.get("role") == "user" else "Valentina"
            lineas.append(f"{quien}: {t['message']}")
    return "\n".join(lineas)


def procesar(evento: dict) -> str:
    """Procesa un evento ya verificado. Devuelve un texto corto para el log."""
    if evento.get("type") != "post_call_transcription":
        return f"evento ignorado ({evento.get('type')})"
    data = evento.get("data") or {}
    if AGENT_ID and data.get("agent_id") != AGENT_ID:
        return f"agente ignorado ({data.get('agent_id')})"

    conversation_id = data.get("conversation_id", "")
    if conversation_id in _conversaciones_procesadas:
        return f"{conversation_id} duplicado, ignorado"
    _conversaciones_procesadas.append(conversation_id)

    resultados = (data.get("analysis") or {}).get("data_collection_results") or {}
    nombre = _valor(resultados, "nombre")
    whatsapp_dictado = _valor(resultados, "whatsapp")
    if not nombre or not whatsapp_dictado:
        return f"{conversation_id} sin nombre o WhatsApp, no es lead"

    telefono, numero_ok = normalizar_whatsapp_ar(whatsapp_dictado)
    negocio, rubro = _valor(resultados, "negocio"), _valor(resultados, "rubro")
    lead = {
        "telefono": telefono,
        "nombre": nombre,
        "tratamiento": _valor(resultados, "que_resolver"),
        "sucursal": " — ".join(x for x in (negocio, rubro) if x),
        "horario": _valor(resultados, "horario"),
    }
    nota = "Lead de llamada de voz"
    if not numero_ok:
        nota += f" — VERIFICAR NÚMERO: se dictó '{whatsapp_dictado}'"

    ok = registrar_lead(**lead, notas=nota)
    resumen = _valor(resultados, "resumen") or _transcripcion(data.get("transcript"))
    if not ok:
        # El Sheet falló: el aviso por Telegram lleva todos los datos para no perder el lead.
        resumen = "⚠️ NO SE PUDO GUARDAR EN EL SHEET — cargalo a mano.\n\n" + resumen
    if not numero_ok:
        resumen = f"⚠️ Revisar el número: se dictó '{whatsapp_dictado}'.\n\n" + resumen
    notify_lead(**lead, resumen=resumen, origen="llamada de voz")
    return f"{conversation_id} lead {nombre} {'registrado' if ok else 'NO registrado en Sheet'}"


def manejar(cuerpo: str, header_firma: Optional[str]) -> tuple[str, int]:
    """Punto de entrada del endpoint: verifica la firma y procesa. Devuelve (texto, status)."""
    if not firma_valida(cuerpo, header_firma or ""):
        print("[voz] firma inválida o ELEVENLABS_WEBHOOK_SECRET sin configurar")
        return "Unauthorized", 401
    try:
        evento = json.loads(cuerpo)
    except json.JSONDecodeError:
        return "Bad Request", 400
    print(f"[voz] {procesar(evento)}")
    return "OK", 200
