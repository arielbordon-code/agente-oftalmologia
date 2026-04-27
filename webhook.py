"""
Servidor Flask que recibe mensajes de WhatsApp via Twilio
y los procesa con el agente de estética.

Para conectar con Twilio:
1. Obtener un número de Twilio con WhatsApp habilitado
2. Configurar el webhook en Twilio Console → WhatsApp Sandbox:
   URL: https://TU_DOMINIO/webhook
   Método: POST
3. Para desarrollo local usar ngrok: ngrok http 5000
"""

import os
from collections import deque
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from dotenv import load_dotenv
from agent import OftalmologiaAgent as EsteticaAgent

load_dotenv()


app = Flask(__name__)
agent = EsteticaAgent(api_key=os.getenv("GEMINI_API_KEY"))

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")

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
        reply_text = "¡Hola nuevamente! 👋 Soy Valentina de Clínica Bella Forma. ¿En qué puedo ayudarte hoy?"
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
    return {"status": "ok", "agente": "Clínica Bella Forma - Estética Corporal"}


@app.route("/conversaciones", methods=["GET"])
def conversaciones():
    """Lista las conversaciones activas (solo para debugging)."""
    return {
        "conversaciones_activas": len(agent.conversations),
        "numeros": list(agent.conversations.keys())
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🌸 Agente Clínica Bella Forma iniciado en puerto {port}")
    print(f"   Webhook URL: http://localhost:{port}/webhook")
    app.run(debug=True, port=port)
