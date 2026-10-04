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
from collections import deque
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from dotenv import load_dotenv
from agent import OftalmologiaAgent as EsteticaAgent
from sheets import listar_leads, actualizar_estado, actualizar_notas, ESTADO_A_TEXTO, obtener_estadisticas

load_dotenv()


app = Flask(__name__)
agent = EsteticaAgent(api_key=os.getenv("ANTHROPIC_API_KEY"))

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")

DASHBOARD_API_TOKEN = os.getenv("DASHBOARD_API_TOKEN", "")
DASHBOARD_ORIGINS = [o.strip() for o in os.getenv("DASHBOARD_ORIGINS", "").split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": DASHBOARD_ORIGINS}})


def _token_valido() -> bool:
    token = request.args.get("token", "")
    return bool(DASHBOARD_API_TOKEN) and token == DASHBOARD_API_TOKEN

# Deduplicación: evita procesar el mismo mensaje dos veces si Twilio reintenta
_processed_sids = deque(maxlen=200)


def validate_twilio_request(f):
    """Decorador desactivado en modo sandbox/desarrollo."""
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated


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

    print(f"[{sender_number}] → {incoming_msg}")

    if not incoming_msg:
        return Response("OK", status=200)

    # Comandos especiales para gestión
    if incoming_msg.lower() in ["reiniciar", "restart", "nueva consulta"]:
        agent.reset_conversation(sender_number)
        reply_text = (
            "¡Hola de nuevo! 👋 Arranquemos la demo otra vez. Contame 3 cosas rápidas: "
            "¿cómo se llama tu negocio, a qué se dedica, y qué te gustaría resolver por "
            "WhatsApp (turnos, consultas, pedidos)?"
        )
    else:
        reply_text = agent.reply(sender_number, incoming_msg)

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
