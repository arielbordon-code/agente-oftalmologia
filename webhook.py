"""
Servidor Flask que recibe mensajes de WhatsApp via Twilio
y los procesa con el agente de demostración.

Para conectar con Twilio:
1. Obtener un número de Twilio con WhatsApp habilitado
2. Configurar el webhook en Twilio Console → WhatsApp Sandbox:
   URL: https://TU_DOMINIO/webhook
   Método: POST
3. Para desarrollo local usar ngrok: ngrok http 5000
"""

import os
import httpx
from collections import deque
from datetime import datetime
from functools import wraps
from typing import Optional
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from dotenv import load_dotenv
from agent import OftalmologiaAgent as EsteticaAgent
from sheets import (
    listar_leads,
    actualizar_estado,
    actualizar_notas,
    ESTADO_A_TEXTO,
    obtener_estadisticas,
    obtener_leads_para_seguimiento,
    marcar_seguimiento_enviado,
)
from whatsapp_followup import send_followup_whatsapp

load_dotenv()


app = Flask(__name__)
agent = EsteticaAgent(api_key=os.getenv("ANTHROPIC_API_KEY"))

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")


def _run_followups():
    leads = obtener_leads_para_seguimiento(dias=3)
    for lead in leads:
        ok = send_followup_whatsapp(lead["telefono"])
        if ok:
            marcar_seguimiento_enviado(lead["fila"])


scheduler = BackgroundScheduler(timezone="America/Argentina/Buenos_Aires")
scheduler.add_job(_run_followups, CronTrigger(hour=10, minute=30))
scheduler.start()

DASHBOARD_API_TOKEN = os.getenv("DASHBOARD_API_TOKEN", "")
DASHBOARD_ORIGINS = [o.strip() for o in os.getenv("DASHBOARD_ORIGINS", "").split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": DASHBOARD_ORIGINS}})


def _token_valido() -> bool:
    token = request.args.get("token", "")
    return bool(DASHBOARD_API_TOKEN) and token == DASHBOARD_API_TOKEN

# Deduplicación: evita procesar el mismo mensaje dos veces si Twilio reintenta
_processed_sids = deque(maxlen=200)


# Firma de Twilio. off: no valida (comportamiento de siempre). observe: valida y loguea, pero
# nunca bloquea. enforce: rechaza lo que no venga firmado por Twilio.
TWILIO_VALIDATION = os.getenv("TWILIO_VALIDATION", "off").lower() if TWILIO_AUTH_TOKEN else "off"
_twilio_validator = RequestValidator(TWILIO_AUTH_TOKEN) if TWILIO_AUTH_TOKEN else None

# Tope de mensajes por número por día. 0 = sin tope (comportamiento de siempre).
MAX_MESSAGES_PER_DAY = int(os.getenv("MAX_MESSAGES_PER_DAY", "0") or 0)
_mensajes_por_dia: dict[str, tuple[str, int]] = {}
TZ_AR = ZoneInfo("America/Argentina/Buenos_Aires")


def _url_publica() -> str:
    # Railway termina HTTPS en su proxy: Flask ve http://, pero Twilio firmó la URL https://.
    url = request.url
    if request.headers.get("X-Forwarded-Proto") == "https" and url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    return url


def validate_twilio_request(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if TWILIO_VALIDATION != "off":
            firma = request.headers.get("X-Twilio-Signature", "")
            if not _twilio_validator.validate(_url_publica(), request.form, firma):
                print(
                    f"[twilio] firma inválida modo={TWILIO_VALIDATION} url={_url_publica()} "
                    f"from={request.form.get('From', '')}"
                )
                if TWILIO_VALIDATION == "enforce":
                    return Response("Forbidden", status=403)
        return f(*args, **kwargs)
    return decorated


def _descargar_media(media_url: str) -> Optional[bytes]:
    """Descarga un adjunto de WhatsApp. Las URLs de media de Twilio piden auth básica
    con el Account SID y el Auth Token, igual que cualquier otro recurso de su API.
    Twilio responde con un 307 hacia su CDN, por eso hay que seguir la redirección."""
    try:
        resp = httpx.get(
            media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN), timeout=10, follow_redirects=True
        )
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"[media] Error descargando adjunto: {e}")
        return None


def _contar_mensaje_del_dia(numero: str) -> int:
    hoy = datetime.now(TZ_AR).date().isoformat()
    fecha, cantidad = _mensajes_por_dia.get(numero, (hoy, 0))
    cantidad = cantidad + 1 if fecha == hoy else 1
    _mensajes_por_dia[numero] = (hoy, cantidad)
    return cantidad


@app.route("/webhook", methods=["POST"])
@validate_twilio_request
def webhook():
    """Endpoint principal que recibe mensajes de WhatsApp."""
    incoming_msg = request.form.get("Body", "").strip()
    sender_number = request.form.get("From", "")
    message_sid = request.form.get("MessageSid", "")

    # Ignorar reintentos de Twilio
    if message_sid and message_sid in _processed_sids:
        print(f"[{sender_number}] Mensaje duplicado ignorado: {message_sid}")
        return Response("OK", status=200)
    if message_sid:
        _processed_sids.append(message_sid)

    num_media = int(request.form.get("NumMedia", "0") or 0)
    media = []
    for i in range(num_media):
        media_url = request.form.get(f"MediaUrl{i}")
        content_type = request.form.get(f"MediaContentType{i}", "")
        if not media_url:
            continue
        data = _descargar_media(media_url)
        if data:
            media.append({"content_type": content_type, "data": data})

    print(f"[{sender_number}] → {incoming_msg}" + (f" (+{len(media)} adjunto/s)" if media else ""))

    if not incoming_msg and not media:
        return Response("OK", status=200)

    if MAX_MESSAGES_PER_DAY:
        cantidad = _contar_mensaje_del_dia(sender_number)
        if cantidad > MAX_MESSAGES_PER_DAY:
            resp = MessagingResponse()
            # Se avisa una sola vez; después se ignora en silencio para no gastar Twilio.
            if cantidad == MAX_MESSAGES_PER_DAY + 1:
                print(f"[limite] {sender_number} superó {MAX_MESSAGES_PER_DAY} mensajes hoy")
                resp.message(
                    "Por hoy llegamos al límite de mensajes de la demo 🙂 Mañana podés seguir "
                    "probándome. Si ya querés avanzar, el equipo de Kyrios te contacta desde "
                    "kyrioscomunicacion.com"
                )
            return Response(str(resp), status=200, mimetype="application/xml")

    # Comandos especiales para gestión
    if incoming_msg.lower() in ["reiniciar", "restart", "nueva consulta"]:
        agent.reset_conversation(sender_number)
        reply_text = (
            "¡Hola de nuevo! 👋 Arranquemos la demo otra vez. Contame 3 cosas rápidas: "
            "¿cómo se llama tu negocio, a qué se dedica, y qué te gustaría resolver por "
            "WhatsApp (turnos, consultas, pedidos)?"
        )
    else:
        reply_text = agent.reply(sender_number, incoming_msg, media=media)

    print(f"[{sender_number}] ← {reply_text}")

    # Respuesta en formato TwiML para Twilio
    resp = MessagingResponse()
    resp.message(reply_text)
    return Response(str(resp), status=200, mimetype="application/xml")


@app.route("/health", methods=["GET"])
def health():
    """Endpoint de salud para monitoreo."""
    return {"status": "ok", "agente": "Valentina - Demo Kyrios"}


@app.route("/api/leads", methods=["GET"])
def api_leads():
    """Leads reales registrados en Sheets, para el dashboard."""
    if not _token_valido():
        return jsonify({"error": "unauthorized"}), 401
    leads = listar_leads()
    return jsonify({"leads": leads, "total": len(leads)})


@app.route("/api/conversaciones", methods=["GET"])
def api_conversaciones():
    """Conversaciones en vivo (en memoria), para el dashboard."""
    if not _token_valido():
        return jsonify({"error": "unauthorized"}), 401
    conversaciones = agent.to_dashboard_list()
    return jsonify({"conversaciones": conversaciones, "total": len(conversaciones)})


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Estadísticas agregadas reales (KPIs y gráficos del dashboard)."""
    if not _token_valido():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(obtener_estadisticas())


@app.route("/api/leads/<int:fila>/estado", methods=["POST"])
def api_actualizar_estado(fila):
    """Persiste el estado (pending/confirmed/attended) de un lead en Sheets."""
    if not _token_valido():
        return jsonify({"error": "unauthorized"}), 401
    estado = (request.get_json(silent=True) or {}).get("estado", "")
    if estado not in ESTADO_A_TEXTO:
        return jsonify({"error": "estado inválido"}), 400
    ok = actualizar_estado(fila, estado)
    if not ok:
        return jsonify({"error": "no se pudo actualizar"}), 500
    return jsonify({"ok": True})


@app.route("/api/leads/<int:fila>/notas", methods=["POST"])
def api_actualizar_notas(fila):
    """Persiste la nota interna de un lead en Sheets."""
    if not _token_valido():
        return jsonify({"error": "unauthorized"}), 401
    notas = (request.get_json(silent=True) or {}).get("notas", "")
    ok = actualizar_notas(fila, notas)
    if not ok:
        return jsonify({"error": "no se pudo actualizar"}), 500
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"👋 Agente Valentina (demo comercial Kyrios) iniciado en puerto {port}")
    print(f"   Webhook URL: http://localhost:{port}/webhook")
    app.run(debug=True, port=port)
