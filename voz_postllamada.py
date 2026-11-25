"""
Leads del agente de voz de Valentina (ElevenLabs).

Al terminar cada llamada, ElevenLabs manda un webhook "post_call_transcription" con los datos
que extrajo (nombre, WhatsApp, negocio, rubro, qué quiere resolver, horario). Si el prospecto
dejó nombre y WhatsApp, se registra en el mismo Sheet que los leads de WhatsApp y se avisa
por Telegram, igual que hace agent.py. Si no los dejó, igual llega un aviso corto para saber
quién probó la demo.

También cuida los créditos del plan: avisa por Telegram cuando quedan pocos y cuando la demo
llega al tope diario de llamadas configurado en el agente (agente-voz/crear_agente.py).
"""

import hashlib
import hmac
import json
import os
import re
import time
from collections import deque
from typing import Optional

import httpx

from sheets import registrar_lead
from telegram_service import notify_aviso, notify_lead

# .strip(): al pegar en Railway suele colarse un espacio o salto de línea al final.
WEBHOOK_SECRET = os.getenv("ELEVENLABS_WEBHOOK_SECRET", "").strip()
AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID", "").strip()
# Opcional: sin esta key no se revisan los créditos (el resto funciona igual).
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
# Tiene que coincidir con LIMITE_DIARIO de agente-voz/crear_agente.py.
LIMITE_DIARIO = int(os.getenv("VOZ_LIMITE_DIARIO", "4"))
TOLERANCIA_SEGUNDOS = 30 * 60
CREDITOS_POR_DEMO = 1200  # llamada completa de 3 minutos a ~400 créditos/min
UMBRALES_CREDITOS = (25, 10)  # % restante en que se avisa, una vez por umbral y por período

# ElevenLabs puede reintentar el mismo webhook: no registrar dos veces la misma llamada.
_conversaciones_procesadas = deque(maxlen=200)
_alertas_creditos_enviadas = set()  # (fecha de renovación, umbral)
_llamadas_del_dia = {"fecha": "", "cantidad": 0}


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


def _numero_en_transcripcion(transcript: list) -> str:
    """Último número de teléfono que dictó el prospecto (8 a 13 dígitos, con o sin espacios/guiones).
    Respaldo para cuando ElevenLabs no lo extrajo, p. ej. si la llamada se cortó antes de confirmarlo."""
    encontrado = ""
    for t in transcript or []:
        if t.get("role") != "user" or not t.get("message"):
            continue
        for bloque in re.findall(r"\d[\d .\-()]{6,}\d", t["message"]):
            digitos = re.sub(r"\D", "", bloque)
            if 8 <= len(digitos) <= 13:
                encontrado = digitos
    return encontrado


def _transcripcion(transcript: list) -> str:
    lineas = []
    for t in transcript or []:
        if t.get("message"):
            quien = "Prospecto" if t.get("role") == "user" else "Valentina"
            lineas.append(f"{quien}: {t['message']}")
    return "\n".join(lineas)


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def revisar_creditos() -> None:
    """Avisa por Telegram si los créditos de ElevenLabs bajan del 25% y del 10%."""
    if not ELEVENLABS_API_KEY:
        return
    try:
        resp = httpx.get("https://api.elevenlabs.io/v1/user/subscription",
                         headers={"xi-api-key": ELEVENLABS_API_KEY}, timeout=10)
        resp.raise_for_status()
        sub = resp.json()
    except Exception as e:
        print(f"[voz] no se pudieron revisar los créditos: {e}")
        return
    limite = sub.get("character_limit") or 0
    if not limite:
        return
    restantes = max(limite - (sub.get("character_count") or 0), 0)
    porcentaje = restantes * 100 / limite
    renovacion = sub.get("next_character_count_reset_unix") or 0

    superados = [u for u in UMBRALES_CREDITOS if porcentaje <= u]
    if not superados or (renovacion, min(superados)) in _alertas_creditos_enviadas:
        return
    _alertas_creditos_enviadas.update((renovacion, u) for u in superados)
    fecha = time.strftime("%d/%m", time.gmtime(renovacion - 3 * 3600)) if renovacion else "?"
    notify_aviso(
        f"⚠️ Créditos de ElevenLabs (agente de voz): quedan {_miles(restantes)} de {_miles(limite)} "
        f"({porcentaje:.0f}%). Alcanzan para unas {restantes // CREDITOS_POR_DEMO} demos completas. "
        f"Se renuevan el {fecha}. Si las demos están trayendo leads, es momento de evaluar subir de plan; "
        f"si no, se puede bajar el tope diario."
    )


def _contar_llamada() -> None:
    """Cuenta las llamadas del día (UTC) y avisa cuando se llega al tope diario del agente."""
    hoy = time.strftime("%Y-%m-%d", time.gmtime())
    if _llamadas_del_dia["fecha"] != hoy:
        _llamadas_del_dia.update(fecha=hoy, cantidad=0)
    _llamadas_del_dia["cantidad"] += 1
    if _llamadas_del_dia["cantidad"] == LIMITE_DIARIO:
        notify_aviso(
            f"📵 La demo de voz llegó a {LIMITE_DIARIO} llamadas hoy, el tope diario. ElevenLabs no va a "
            f"atender más hasta que se reinicie el contador. Si hay demanda real, se puede subir el tope "
            f"(LIMITE_DIARIO en agente-voz/crear_agente.py)."
        )


def _avisar_llamada_sin_datos(data: dict, resultados: dict) -> None:
    """Quien probó la demo sin dejar nombre y WhatsApp: aviso corto, por si se puede recuperar."""
    if not any(t.get("role") == "user" and t.get("message") for t in data.get("transcript") or []):
        return  # abrió la llamada y no habló: no vale la pena avisar
    duracion = int((data.get("metadata") or {}).get("call_duration_secs") or 0)
    nombre = _valor(resultados, "nombre")
    negocio = " — ".join(x for x in (_valor(resultados, "negocio"), _valor(resultados, "rubro")) if x)
    resumen = _valor(resultados, "resumen") or "(sin resumen)"
    corte = " (se cortó por tiempo)" if duracion >= 175 else ""
    # Lo que dijo el prospecto, textual: si dictó un número que no quedó registrado, aparece acá.
    dichos = "\n".join(f"• {t['message']}" for t in data.get("transcript") or []
                       if t.get("role") == "user" and t.get("message"))
    if len(dichos) > 2000:
        dichos = "…" + dichos[-2000:]
    notify_aviso(
        f"📞 Llamada a la demo de voz sin datos de contacto — {duracion} s{corte}\n\n"
        f"👤 {nombre or 'Sin nombre'}\n"
        f"🏢 {negocio or 'No especificado'}\n\n"
        f"{resumen}\n\n"
        f"🗣 Lo que dijo el prospecto (por si dictó un número):\n{dichos}"
    )


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
    _contar_llamada()

    resultados = (data.get("analysis") or {}).get("data_collection_results") or {}
    nombre = _valor(resultados, "nombre")
    whatsapp_dictado = _valor(resultados, "whatsapp")
    tomado_de_transcripcion = False
    if not whatsapp_dictado:
        whatsapp_dictado = _numero_en_transcripcion(data.get("transcript"))
        tomado_de_transcripcion = bool(whatsapp_dictado)
    if not whatsapp_dictado:
        _avisar_llamada_sin_datos(data, resultados)
        return f"{conversation_id} sin WhatsApp, no es lead"
    nombre = nombre or "Sin nombre (llamada de voz)"

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
    if tomado_de_transcripcion:
        nota += " — número tomado de la transcripción, SIN CONFIRMAR"
    if not numero_ok:
        nota += f" — VERIFICAR NÚMERO: se dictó '{whatsapp_dictado}'"

    ok = registrar_lead(**lead, notas=nota)
    resumen = _valor(resultados, "resumen") or _transcripcion(data.get("transcript"))
    if not ok:
        # El Sheet falló: el aviso por Telegram lleva todos los datos para no perder el lead.
        resumen = "⚠️ NO SE PUDO GUARDAR EN EL SHEET — cargalo a mano.\n\n" + resumen
    if not numero_ok:
        resumen = f"⚠️ Revisar el número: se dictó '{whatsapp_dictado}'.\n\n" + resumen
    if tomado_de_transcripcion:
        resumen = "⚠️ La llamada terminó antes de confirmar el número: lo saqué de lo que dictó el prospecto.\n\n" + resumen
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
    revisar_creditos()
    return "OK", 200
